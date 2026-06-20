#!/usr/bin/env python3
"""SOME/IP Calculator Server — 提供 add / subtract / multiply 三个 RPC method。

基于 pysomeip 的 SimpleService，通过 SD（Service Discovery）通告自身。
Client 发来 REQUEST（含 JSON 操作数），Server 计算后返回 RESPONSE。

运行（先起 Server，再起 Client）:

    cd tinySOA
    PYTHONPATH=src:third_party/pysomeip/src \\
      python examples/someip_method_call/server.py

退出码 0 正常；1 端口占用或其它错误。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import socket
import sys
from pathlib import Path
from typing import Optional, Sequence

# 确保 tinysoa + someip 在 sys.path 中
_repo = Path(__file__).resolve().parents[2]
for _p in (str(_repo / "src"), str(_repo / "third_party" / "pysomeip" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import someip.header as hdr
from someip.sd import (
    ServiceDiscoveryProtocol,
    SOMEIPDatagramProtocol,
    DatagramProtocolAdapter,
)

from _common import (
    LOCAL_IP,
    SERVER_PORT,
    SERVICE_ID,
    INSTANCE_ID,
    MAJOR_VERSION,
    MINOR_VERSION,
    METHODS,
)

logger = logging.getLogger("calc.server")


# ── Calculator Service ────────────────────────────────────────────────
class CalculatorService(SOMEIPDatagramProtocol):
    """SOME/IP Calculator 服务。

    继承 SOMEIPDatagramProtocol 以获得 send() 和 message_received() 能力。
    对每个支持的 method 注册一个 handler：
      - 入参：SOMEIPHeader（含 payload）
      - 出参：bytes（RESPONSE payload），或 None（REQUEST_NO_RETURN）
    """

    def __init__(self, instance_id: int):
        super().__init__(logger="calc.service")
        self.instance_id = instance_id
        self._handlers: dict[int, hdr._T_METHOD_HANDLER] = {}

        # 注册 method
        self._register(METHODS["add"], self._handle_add)
        self._register(METHODS["subtract"], self._handle_sub)
        self._register(METHODS["multiply"], self._handle_mul)

    def _register(self, method_id: int, handler: hdr._T_METHOD_HANDLER) -> None:
        self._handlers[method_id] = handler

    # ── message_received（SOMEIPDatagramProtocol 钩子） ──────────────
    def message_received(
        self,
        someip_message: hdr.SOMEIPHeader,
        addr: hdr._T_SOCKNAME,
        multicast: bool,
    ) -> None:
        """收到 UDP 报文时 pysomeip 回调此方法。"""
        if multicast:
            return  # Service 不应从多播收业务报文

        if someip_message.service_id != SERVICE_ID:
            self._send_error(someip_message, addr, hdr.SOMEIPReturnCode.E_UNKNOWN_SERVICE)
            return

        if someip_message.message_type not in (
            hdr.SOMEIPMessageType.REQUEST,
            hdr.SOMEIPMessageType.REQUEST_NO_RETURN,
        ):
            self._send_error(someip_message, addr, hdr.SOMEIPReturnCode.E_WRONG_MESSAGE_TYPE)
            return

        handler = self._handlers.get(someip_message.method_id)
        if handler is None:
            self._send_error(someip_message, addr, hdr.SOMEIPReturnCode.E_UNKNOWN_METHOD)
            return

        method_name = {v: k for k, v in METHODS.items()}.get(someip_message.method_id, "?")
        logger.info(
            "REQUEST  method=%s (0x%04x) session=0x%04x payload=%r",
            method_name,
            someip_message.method_id,
            someip_message.session_id,
            someip_message.payload,
        )

        try:
            response_payload = handler(someip_message, addr)
        except Exception:
            self._send_error(someip_message, addr, hdr.SOMEIPReturnCode.E_MALFORMED_MESSAGE)
            return

        if (
            response_payload is not None
            and someip_message.message_type == hdr.SOMEIPMessageType.REQUEST
        ):
            self._send_response(someip_message, addr, response_payload)

    def _send_error(
        self,
        msg: hdr.SOMEIPHeader,
        addr: hdr._T_SOCKNAME,
        return_code: hdr.SOMEIPReturnCode,
    ) -> None:
        import dataclasses
        resp = dataclasses.replace(
            msg,
            message_type=hdr.SOMEIPMessageType.ERROR,
            return_code=return_code,
            payload=b"",
        )
        self.send(resp.build(), addr)

    def _send_response(
        self,
        msg: hdr.SOMEIPHeader,
        addr: hdr._T_SOCKNAME,
        payload: bytes,
    ) -> None:
        import dataclasses
        resp = dataclasses.replace(
            msg, message_type=hdr.SOMEIPMessageType.RESPONSE, payload=payload
        )
        self.send(resp.build(), addr)
        logger.info("RESPONSE session=0x%04x payload=%r", msg.session_id, payload)

    # ── Arithmetic handlers ────────────────────────────────────────
    @staticmethod
    def _parse_operands(payload: bytes) -> tuple[float, float]:
        data = json.loads(payload.decode("utf-8"))
        return float(data["a"]), float(data["b"])

    def _handle_add(self, msg: hdr.SOMEIPHeader, _addr) -> bytes:
        a, b = self._parse_operands(msg.payload)
        return json.dumps({"result": a + b}).encode("utf-8")

    def _handle_sub(self, msg: hdr.SOMEIPHeader, _addr) -> bytes:
        a, b = self._parse_operands(msg.payload)
        return json.dumps({"result": a - b}).encode("utf-8")

    def _handle_mul(self, msg: hdr.SOMEIPHeader, _addr) -> bytes:
        a, b = self._parse_operands(msg.payload)
        return json.dumps({"result": a * b}).encode("utf-8")


# ── CLI / Main ─────────────────────────────────────────────────────
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SOME/IP Calculator Server")
    parser.add_argument("--host", default=LOCAL_IP, help=f"bind address (default: {LOCAL_IP})")
    parser.add_argument("--port", type=int, default=SERVER_PORT, help=f"listen port (default: {SERVER_PORT})")
    parser.add_argument("--log-level", default="INFO", choices=_LOG_LEVELS, help="logging verbosity")
    return parser.parse_args(argv)


async def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info(
        "Calculator Server starting — service_id=0x%04x instance=0x%04x on %s:%d",
        SERVICE_ID, INSTANCE_ID, args.host, args.port,
    )

    # 1. 创建 Service Discovery
    sd_trsp_u, sd_trsp_m, sd_prot = await ServiceDiscoveryProtocol.create_endpoints(
        family=socket.AF_INET,
        local_addr=args.host,
        multicast_addr="224.224.224.245",
    )
    sd_prot.start()
    logger.info("SD started (unicast + multicast)")

    # 2. 创建 CalculatorService 的 UDP unicast 端点
    loop = asyncio.get_event_loop()
    calc_prot = CalculatorService(instance_id=INSTANCE_ID)
    trsp, _ = await loop.create_datagram_endpoint(
        lambda: DatagramProtocolAdapter(calc_prot, is_multicast=False),
        local_addr=(args.host, args.port),
    )
    calc_prot.transport = trsp
    logger.info("Calculator service bound to %s:%d", args.host, args.port)

    # 3. 通告服务（SD Offer）
    from someip.config import Eventgroup, Service as SomeIPServiceConfig
    from someip.header import L4Protocols

    sockname = trsp.get_extra_info("sockname")
    endpoint_opt = Eventgroup._sockaddr_to_endpoint(sockname, L4Protocols.UDP)

    svc_config = SomeIPServiceConfig(
        SERVICE_ID,
        INSTANCE_ID,
        MAJOR_VERSION,
        MINOR_VERSION,
        options_1=(endpoint_opt,),
        eventgroups=frozenset(),
    )
    from someip.sd import ServiceInstance
    si = ServiceInstance(svc_config, calc_prot, sd_prot.announcer, sd_prot.timings)
    sd_prot.announcer.announce_service(si)
    logger.info(
        "SD Offer: service=0x%04x instance=0x%04x methods=%s",
        SERVICE_ID, INSTANCE_ID, list(METHODS.keys()),
    )

    # 4. 等待 Client 请求（按 Ctrl+C 退出）
    logger.info("Ready — waiting for RPC requests (Ctrl+C to stop)")
    stop_event = asyncio.Event()

    def _shutdown() -> None:
        stop_event.set()

    try:
        loop.add_signal_handler(signal.SIGINT, _shutdown)
        loop.add_signal_handler(signal.SIGTERM, _shutdown)
    except NotImplementedError:
        pass

    await stop_event.wait()

    # 5. 优雅关闭
    logger.info("Shutting down...")
    sd_prot.announcer.stop_announce_service(si)
    sd_prot.stop()
    for t in (sd_trsp_u, sd_trsp_m, trsp):
        try:
            t.close()
        except Exception:
            pass
    logger.info("Calculator Server stopped")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
