from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

import someip.header as hdr
from someip.config import Service as SomeIPServiceConfig
from someip.sd import (
    ClientServiceListener,
    DatagramProtocolAdapter,
    SOMEIPDatagramProtocol,
)

from tinysoa.api.service_api import MethodSelector, ServiceInvoker, ServiceSelector
from tinysoa.core.errors import NotFoundError, StateError, ValidationError
from tinysoa.core.model import Message, Method, Service

from .someip import SomeIPEndpoint, SomeIPPublisher

logger = logging.getLogger(__name__)

_MAX_ID = 0xFFFF
MethodHandler = Callable[[Any], Awaitable[Any]]


class SomeIPRemoteError(RuntimeError):
    """Raised when the remote SOME/IP service returns an ERROR response."""

    def __init__(self, return_code: str):
        super().__init__(f"SOME/IP error: {return_code}")
        self.return_code = return_code


@dataclass(frozen=True)
class SomeIPServiceBinding:
    """Configuration for one SOME/IP service with methods.

    Application code refers to logical ``name`` / method names; this binding is
    the only place that knows the SOME/IP service and method IDs.
    """

    name: str
    service_id: int
    instance_id: int
    methods: Mapping[str, int]
    major_version: int = 1
    minor_version: int = 0
    local_ip: str = "127.0.0.1"
    local_port: int = 0
    server_port: int = 0
    timeout: float = 5.0
    discovery_timeout: float = 10.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValidationError("SomeIPServiceBinding.name must be non-empty")
        _check_id("service_id", self.service_id)
        _check_id("instance_id", self.instance_id)
        _check_range("major_version", self.major_version, 0, 0xFF)
        _check_range("minor_version", self.minor_version, 0, 0xFFFFFFFF)
        _check_range("local_port", self.local_port, 0, 0xFFFF)
        _check_range("server_port", self.server_port, 0, 0xFFFF)
        if not isinstance(self.methods, Mapping) or not self.methods:
            raise ValidationError(
                "SomeIPServiceBinding.methods must be a non-empty mapping"
            )
        if self.timeout <= 0:
            raise ValidationError("SomeIPServiceBinding.timeout must be positive")
        if self.discovery_timeout <= 0:
            raise ValidationError(
                "SomeIPServiceBinding.discovery_timeout must be positive"
            )
        method_ids = list(self.methods.values())
        for method_id in method_ids:
            _check_id("method_id", method_id)
        if len(method_ids) != len(set(method_ids)):
            raise ValidationError("SomeIPServiceBinding has duplicate method ids")
        object.__setattr__(self, "methods", dict(self.methods))

    def method_id(self, method: MethodSelector) -> int:
        """Resolve a method name/id/Method to a SOME/IP method id."""
        if isinstance(method, Method):
            if method.name in self.methods:
                return self.methods[method.name]
            if method.id in self.methods.values():
                return method.id
            raise NotFoundError(
                f"method {method.name!r}/{method.id:#x} not in binding {self.name!r}"
            )
        if isinstance(method, str):
            try:
                return self.methods[method]
            except KeyError as exc:
                raise NotFoundError(
                    f"method {method!r} not in binding {self.name!r}"
                ) from exc
        if isinstance(method, int):
            if method in self.methods.values():
                return method
            raise NotFoundError(f"method id {method:#x} not in binding {self.name!r}")
        raise ValidationError(f"Unsupported method selector: {method!r}")

    def matches_service(self, service: ServiceSelector) -> bool:
        """Return whether a service selector refers to this binding."""
        if isinstance(service, Service):
            return service.id == self.service_id or service.name == self.name
        if isinstance(service, str):
            return service == self.name
        if isinstance(service, int):
            return service == self.service_id
        return False


def _check_id(name: str, value: int) -> None:
    _check_range(name, value, 0, _MAX_ID)


def _check_range(name: str, value: int, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"SomeIPServiceBinding.{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValidationError(
            f"SomeIPServiceBinding.{name} must be in {minimum}..{maximum}, got {value}"
        )


class _RpcClientProtocol(SOMEIPDatagramProtocol):
    """Minimal SOME/IP RPC client: send REQUEST, match RESPONSE by session id."""

    def __init__(self, service_id: int, client_id: int, major_version: int):
        super().__init__(logger="someip.rpc")
        self.service_id = service_id
        self.client_id = client_id
        self.major_version = major_version
        self._pending: Dict[int, asyncio.Future[bytes]] = {}
        self._session = 1

    async def call(
        self,
        addr: hdr._T_SOCKNAME,
        method_id: int,
        payload: bytes,
        timeout: float,
    ) -> bytes:
        session_id = self._session
        self._session = (self._session + 1) & _MAX_ID or 1

        request = hdr.SOMEIPHeader(
            service_id=self.service_id,
            method_id=method_id,
            client_id=self.client_id,
            session_id=session_id,
            interface_version=self.major_version,
            message_type=hdr.SOMEIPMessageType.REQUEST,
            return_code=hdr.SOMEIPReturnCode.E_OK,
            payload=payload,
        )

        future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        self._pending[session_id] = future
        self.log.debug(
            "SEND method=%#06x session=%#06x -> %r", method_id, session_id, addr
        )
        self.send(request.build(), addr)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(session_id, None)

    def message_received(
        self,
        someip_message: hdr.SOMEIPHeader,
        addr: hdr._T_SOCKNAME,
        multicast: bool,
    ) -> None:
        if multicast:
            return
        future = self._pending.get(someip_message.session_id)
        if future is None or future.done():
            return
        if someip_message.message_type == hdr.SOMEIPMessageType.RESPONSE:
            future.set_result(someip_message.payload)
        elif someip_message.message_type == hdr.SOMEIPMessageType.ERROR:
            future.set_exception(SomeIPRemoteError(someip_message.return_code.name))


class _ServiceWatcher(ClientServiceListener):
    """Wait for an SD Offer matching service/instance."""

    def __init__(self, service_id: int, instance_id: int):
        self.service_id = service_id
        self.instance_id = instance_id
        self._found: Optional[tuple[str, int]] = None
        self._event = asyncio.Event()

    def service_offered(
        self, service: SomeIPServiceConfig, source: tuple[str, int]
    ) -> None:
        if self._found is not None:
            return
        if (
            service.service_id != self.service_id
            or service.instance_id != self.instance_id
        ):
            return
        for option in service.options_1:
            if hasattr(option, "port") and hasattr(option, "address"):
                self._found = (str(option.address), option.port)
                self._event.set()
                return

    def service_stopped(
        self, service: SomeIPServiceConfig, source: tuple[str, int]
    ) -> None:
        return None

    async def wait(self, sd_protocol, timeout: float) -> tuple[str, int]:
        sd_protocol.discovery.watch_all_services(self)
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise NotFoundError(
                f"SOME/IP service {self.service_id:#06x}:{self.instance_id:#06x} "
                f"not discovered within {timeout}s"
            ) from None
        finally:
            sd_protocol.discovery.stop_watch_all_services(self)
        assert self._found is not None
        return self._found


class SomeIPMethodInvoker(ServiceInvoker):
    """Client-side ``ServiceInvoker`` over SOME/IP REQUEST/RESPONSE."""

    def __init__(
        self,
        binding: SomeIPServiceBinding,
        *,
        local_ip: Optional[str] = None,
        local_port: Optional[int] = None,
        client_id: int = 1,
    ):
        self.binding = binding
        self.local_ip = binding.local_ip if local_ip is None else local_ip
        self.local_port = binding.local_port if local_port is None else local_port
        self.client_id = client_id
        self._endpoint = SomeIPEndpoint(
            local_ip=self.local_ip,
            publisher_port=0,
            is_publisher=False,
        )
        self._rpc = _RpcClientProtocol(
            service_id=binding.service_id,
            client_id=client_id,
            major_version=binding.major_version,
        )
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._server_addr: Optional[tuple[str, int]] = None
        self._started = False

    async def start(self) -> None:
        """Start SD and the local RPC transport."""
        if self._started:
            return
        await self._endpoint.start()
        if self._endpoint.sd_protocol is None:
            raise StateError("SOME/IP SD initialization failed")
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: DatagramProtocolAdapter(self._rpc, is_multicast=False),
            local_addr=(self.local_ip, self.local_port),
        )
        self._rpc.transport = self._transport
        self._started = True

    async def stop(self) -> None:
        """Close the RPC transport and SD endpoints."""
        if not self._started:
            return
        self._started = False
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        await self._endpoint.stop()

    async def invoke(
        self,
        service: ServiceSelector,
        method: MethodSelector,
        payload: Any | Message,
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Message:
        """Invoke a SOME/IP method and return the decoded response."""
        if not self._started:
            raise StateError("SomeIPMethodInvoker is not started")
        if not self.binding.matches_service(service):
            raise NotFoundError(
                f"service {service!r} does not match binding {self.binding.name!r}"
            )
        method_id = self.binding.method_id(method)
        request_payload = _encode_payload(payload)
        wait_timeout = self.binding.timeout if timeout is None else timeout
        addr = await self._discover()
        response = await self._rpc.call(
            addr, method_id, request_payload, timeout=wait_timeout
        )
        return _decode_response(response)

    async def _discover(self) -> tuple[str, int]:
        if self._server_addr is not None:
            return self._server_addr
        sd_protocol = self._endpoint.sd_protocol
        if sd_protocol is None:
            raise StateError("SOME/IP SD initialization failed")
        watcher = _ServiceWatcher(self.binding.service_id, self.binding.instance_id)
        self._server_addr = await watcher.wait(
            sd_protocol, timeout=self.binding.discovery_timeout
        )
        return self._server_addr


class SomeIPMethodDispatcher:
    """Server-side SOME/IP method dispatcher.

    Business handlers are async and only see decoded payloads; the dispatcher
    owns the pysomeip service endpoint and RESPONSE encoding.
    """

    def __init__(
        self,
        binding: SomeIPServiceBinding,
        *,
        local_ip: Optional[str] = None,
        server_port: Optional[int] = None,
    ):
        self.binding = binding
        self.local_ip = binding.local_ip if local_ip is None else local_ip
        self.server_port = binding.server_port if server_port is None else server_port
        self._endpoint = SomeIPEndpoint(
            local_ip=self.local_ip,
            publisher_port=self.server_port,
            is_publisher=True,
        )
        self._publisher: Optional[SomeIPPublisher] = None
        self._handlers: Dict[str, MethodHandler] = {}
        self._started = False

    def register(self, name: str, handler: MethodHandler) -> None:
        """Register an async handler for a logical method name."""
        if name not in self.binding.methods:
            raise NotFoundError(f"method {name!r} not in binding {self.binding.name!r}")
        if name in self._handlers:
            raise ValidationError(f"method {name!r} already registered")
        self._handlers[name] = handler
        if self._publisher is not None:
            self._publisher.register_method(
                self.binding.methods[name], self._make_adapter(name, handler)
            )

    def method(self, name: str) -> Callable[[MethodHandler], MethodHandler]:
        """Decorator form of :meth:`register`."""

        def decorator(handler: MethodHandler) -> MethodHandler:
            self.register(name, handler)
            return handler

        return decorator

    async def start(self) -> None:
        """Create the service endpoint, register methods, and announce via SD."""
        if self._started:
            return
        if not self._handlers:
            raise StateError("No method handlers registered")
        await self._endpoint.start()
        publisher = SomeIPPublisher(
            service_id=self.binding.service_id,
            instance_id=self.binding.instance_id,
            major_version=self.binding.major_version,
            local_addr=self.local_ip,
            port=self.server_port,
        )
        for name, handler in self._handlers.items():
            publisher.register_method(
                self.binding.methods[name], self._make_adapter(name, handler)
            )
        await publisher.start(self._endpoint.announcer)
        self._publisher = publisher
        self._started = True

    async def stop(self) -> None:
        """Stop the service endpoint and SD participant."""
        if not self._started:
            return
        self._started = False
        if self._publisher is not None:
            self._publisher.stop()
            self._publisher = None
        await self._endpoint.stop()

    def _make_adapter(self, name: str, handler: MethodHandler) -> Callable:
        def adapter(msg: hdr.SOMEIPHeader, addr: hdr._T_SOCKNAME) -> None:
            asyncio.create_task(self._dispatch(name, handler, msg, addr))
            return None

        return adapter

    async def _dispatch(
        self,
        name: str,
        handler: MethodHandler,
        msg: hdr.SOMEIPHeader,
        addr: hdr._T_SOCKNAME,
    ) -> None:
        service = self._publisher.service if self._publisher else None
        if service is None:
            logger.error("SOME/IP service is not running")
            return
        try:
            payload = _decode_payload(msg.payload)
            result = await handler(payload)
            response = _encode_payload(result)
        except Exception:
            logger.exception("method %s failed", name)
            service.send_error_response(msg, addr, hdr.SOMEIPReturnCode.E_NOT_OK)
            return
        if msg.message_type == hdr.SOMEIPMessageType.REQUEST:
            service.send_positive_response(msg, addr, payload=response)


def _encode_payload(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, Message):
        value = value.payload
    if value is None:
        return b""
    return json.dumps(value).encode("utf-8")


def _decode_payload(data: bytes) -> Any:
    if not data:
        return None
    return json.loads(data.decode("utf-8"))


def _decode_response(data: bytes) -> Message:
    try:
        payload: Any = _decode_payload(data)
        content_type = "application/json"
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = data
        content_type = "application/octet-stream"
    return Message(payload=payload, content_type=content_type)
