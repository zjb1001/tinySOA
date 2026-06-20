import pytest

from tinysoa.core.model import Service, Method, Event, Endpoint, Protocol, Message, ServiceStatus
from tinysoa.core.errors import DuplicateError, NotFoundError
from tinysoa.api.service_api import ServiceRegistry, ServiceInvoker
from tinysoa.api.event_api import EventPublisher, EventSubscriber, Subscription


class InMemoryRegistry(ServiceRegistry):
    def __init__(self):
        self._by_id: dict[int, Service] = {}

    def register(self, service: Service) -> None:
        if service.id in self._by_id:
            raise DuplicateError("service id already registered")
        self._by_id[service.id] = service

    def deregister(self, service_id: int) -> None:
        self._by_id.pop(service_id, None)

    def find_by_id(self, service_id: int):
        return self._by_id.get(service_id)

    def find_by_name(self, name: str):
        return [s for s in self._by_id.values() if s.name == name]

    def list_services(self):
        return list(self._by_id.values())


class InMemoryInvoker(ServiceInvoker):
    def __init__(self, registry: InMemoryRegistry):
        self._registry = registry

    def _resolve_service(self, sel):
        if isinstance(sel, Service):
            return sel
        if isinstance(sel, int):
            svc = self._registry.find_by_id(sel)
            if not svc:
                raise NotFoundError("service id not found")
            return svc
        if isinstance(sel, str):
            found = self._registry.find_by_name(sel)
            if not found:
                raise NotFoundError("service name not found")
            if len(found) > 1:
                raise NotFoundError("multiple services match name; be specific")
            return found[0]
        raise TypeError("unsupported selector type")

    def _resolve_method(self, svc: Service, sel):
        if isinstance(sel, Method):
            return sel
        if isinstance(sel, int):
            for m in svc.methods:
                if m.id == sel:
                    return m
            raise NotFoundError("method id not found")
        if isinstance(sel, str):
            for m in svc.methods:
                if m.name == sel:
                    return m
            raise NotFoundError("method name not found")
        raise TypeError("unsupported selector type")

    async def invoke(self, service, method, payload, *, headers=None, timeout=None):
        svc = self._resolve_service(service)
        m = self._resolve_method(svc, method)
        # echo-like fake implementation
        if isinstance(payload, Message):
            req_msg = payload
            body = req_msg.payload
            hdrs = dict(req_msg.headers)
            if headers:
                hdrs.update(headers)
        else:
            body = payload
            hdrs = dict(headers or {})
        return Message(payload={"service": svc.name, "method": m.name, "echo": body}, headers=hdrs)


class InMemoryBus(EventPublisher, EventSubscriber):
    def __init__(self, registry: InMemoryRegistry):
        self._registry = registry
        self._handlers: dict[tuple[int, int], list] = {}

    def _resolve_service_id(self, sel) -> int:
        if isinstance(sel, Service):
            return sel.id
        if isinstance(sel, int):
            return sel
        if isinstance(sel, str):
            found = self._registry.find_by_name(sel)
            if not found:
                raise NotFoundError("service name not found")
            if len(found) > 1:
                raise NotFoundError("multiple services match name; be specific")
            return found[0].id
        raise TypeError("unsupported selector type")

    def _resolve_event_id(self, svc: Service, sel) -> int:
        if isinstance(sel, Event):
            return sel.id
        if isinstance(sel, int):
            return sel
        if isinstance(sel, str):
            for e in svc.events:
                if e.name == sel:
                    return e.id
            raise NotFoundError("event name not found")
        raise TypeError("unsupported selector type")

    async def publish(self, service, event, payload, *, headers=None) -> None:
        sid = self._resolve_service_id(service)
        svc = self._registry.find_by_id(sid)
        if not svc:
            raise NotFoundError("service id not found")
        eid = self._resolve_event_id(svc, event)
        key = (sid, eid)
        if isinstance(payload, Message):
            msg = payload
        else:
            msg = Message(payload=payload, headers=dict(headers or {}))
        for h in list(self._handlers.get(key, [])):
            await h(msg)

    def subscribe(self, service, event, handler):
        sid = self._resolve_service_id(service)
        svc = self._registry.find_by_id(sid)
        if not svc:
            raise NotFoundError("service id not found")
        eid = self._resolve_event_id(svc, event)
        key = (sid, eid)
        self._handlers.setdefault(key, []).append(handler)
        return Subscription.new(service_id=sid, event_id=eid)

    def unsubscribe(self, subscription: Subscription) -> None:
        key = (subscription.service_id, subscription.event_id)
        handlers = self._handlers.get(key)
        if not handlers:
            return
        # unsubscribe removes all handlers for simplicity in fake impl
        self._handlers.pop(key, None)


@pytest.fixture()
def sample_service():
    return Service(
        name="echo",
        id=1,
        version="1.0.0",
        methods=[Method("say", 1)],
        events=[Event("said", 1)],
        endpoints=[Endpoint("localhost", 9000, Protocol.TCP)],
    )


@pytest.mark.asyncio
async def test_registry_and_invoker_contract(sample_service):
    reg = InMemoryRegistry()
    reg.register(sample_service)

    assert reg.find_by_id(1) is not None
    assert any(s.name == "echo" for s in reg.find_by_name("echo"))
    assert len(list(reg.list_services())) == 1

    inv = InMemoryInvoker(reg)
    resp = await inv.invoke(1, 1, {"msg": "hi"})
    assert isinstance(resp, Message)
    assert resp.payload["method"] == "say"
    assert resp.payload["echo"]["msg"] == "hi"

    resp2 = await inv.invoke("echo", "say", {"msg": "hello"}, headers={"x": "1"})
    assert resp2.headers.get("x") == "1"

    with pytest.raises(DuplicateError):
        reg.register(sample_service)

    reg.deregister(1)
    assert reg.find_by_id(1) is None


@pytest.mark.asyncio
async def test_publish_subscribe_contract(sample_service):
    reg = InMemoryRegistry()
    reg.register(sample_service)

    bus = InMemoryBus(reg)

    received = []

    async def handler(m):
        received.append(m.payload)

    sub = bus.subscribe("echo", "said", handler)
    await bus.publish("echo", "said", {"text": "ok"})

    assert received and received[0]["text"] == "ok"
    assert isinstance(sub, Subscription)

    bus.unsubscribe(sub)
    received.clear()
    await bus.publish("echo", "said", {"text": "again"})

    assert received == []
