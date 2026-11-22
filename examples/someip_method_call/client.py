#!/usr/bin/env python3
"""SOME/IP Calculator Client — 通过 SD 发现服务，发起 RPC 调用。

流程：
  1. 初始化 Service Discovery，监听多播 Offer
  2. 等待发现 service_id=0x4444 的服务
  3. 对每个 method 依次发送 REQUEST，等待 RESPONSE
  4. 打印结果，退出

运行（先起 Server，再起 Client）:

    cd tinySOA
    PYTHONPATH=src:third_party/pysomeip/src \\
      python examples/someip_method_call/client.py

退出码 0 正常；1 服务未发现或调用超时。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import socket
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

# 确保 tinysoa + someip 在 sys.path 中
_repo = Path(__file__).resolve().parents[2]
for _p in (str(_repo / "src"), str(_repo / "third_party" / "pysomeip" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import someip.header as hdr  # noqa: E402
from _common import (  # noqa: E402
    CLIENT_PORT,
    INSTANCE_ID,
    LOCAL_IP,
    MAJOR_VERSION,
    METHODS,
    SERVICE_ID,
)
from someip.config import Service as SomeIPServiceConfig  # noqa: E402
from someip.sd import (  # noqa: E402
    ClientServiceListener,
    DatagramProtocolAdapter,
    ServiceDiscoveryProtocol,
    SOMEIPDatagramProtocol,
)

logger = logging.getLogger("calc.client")


# ── RPC Client Protocol ──────────────────────────────────────────────
class CalculatorRpcClient(SOMEIPDatagramProtocol):
    """Minimal SOME/IP RPC client。

    职责：
      - 发送 REQUEST 到指定地址
      - 接收 RESPONSE，按 session_id 分派给等待的 Future
    """

    def __init__(self):
        super().__init__(logger="calc.rpc")
        # session_id → Future
        self._pending: dict[int, asyncio.Future[bytes]] = {}
        self._session_counter = 1

    async def call(
        self,
        addr: hdr._T_SOCKNAME,
        method_id: int,
        payload: bytes,
        timeout: float = 5.0,
    ) -> bytes:
        """发送 REQUEST 并等待 RESPONSE。

        Args:
            addr: 服务端的 (host, port)
            method_id: SOME/IP method ID
            payload: 请求体（bytes）
            timeout: 超时秒数

        Returns:
            RESPONSE payload（bytes）

        Raises:
            asyncio.TimeoutError: 超时未收到响应
        """
        session_id = self._session_counter
        self._session_counter = (self._session_counter + 1) & 0xFFFF

        request = hdr.SOMEIPHeader(
            service_id=SERVICE_ID,
            method_id=method_id,
            client_id=0x0001,
            session_id=session_id,
            interface_version=MAJOR_VERSION,
            message_type=hdr.SOMEIPMessageType.REQUEST,
            return_code=hdr.SOMEIPReturnCode.E_OK,
            payload=payload,
        )

        future: asyncio.Future[bytes] = asyncio.get_event_loop().create_future()
        self._pending[session_id] = future

        logger.debug(
            "SEND    method=0x%04x session=0x%04x → %r", method_id, session_id, addr
        )
        self.send(request.build(), addr)

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        finally:
            self._pending.pop(session_id, None)

    # ── message_received（SOMEIPDatagramProtocol 钩子） ──────────────
    def message_received(
        self,
        someip_message: hdr.SOMEIPHeader,
        addr: hdr._T_SOCKNAME,
        multicast: bool,
    ) -> None:
        """收到 RESPONSE 或 ERROR 报文时回调。"""
        if multicast:
            return

        sid = someip_message.session_id
        future = self._pending.get(sid)

        if future is None or future.done():
            logger.debug(
                "RECV unmatched session=0x%04x type=%s",
                sid,
                someip_message.message_type.name,
            )
            return

        if someip_message.message_type == hdr.SOMEIPMessageType.RESPONSE:
            logger.debug(
                "RECV   RESPONSE session=0x%04x payload=%r", sid, someip_message.payload
            )
            future.set_result(someip_message.payload)
        elif someip_message.message_type == hdr.SOMEIPMessageType.ERROR:
            rc = someip_message.return_code
            logger.warning("RECV   ERROR session=0x%04x return_code=%s", sid, rc.name)
            future.set_exception(RuntimeError(f"SOME/IP error: {rc.name}"))
        else:
            logger.debug(
                "RECV unexpected type=%s session=0x%04x",
                someip_message.message_type.name,
                sid,
            )


# ── Service Discovery Watcher ────────────────────────────────────────
class ServiceWatcher(ClientServiceListener):
    """监听 SD Offer 报文，等待目标服务出现。

    实现 ClientServiceListener 接口，通过 discovery.watch_all_services()
    接收所有 Offer 回调，匹配目标 service_id + instance_id 后提取 unicast 地址。
    """

    def __init__(self, sd_prot: ServiceDiscoveryProtocol):
        self.sd_prot = sd_prot
        self._found: Optional[tuple[str, int]] = None
        self._event = asyncio.Event()

    def service_offered(
        self, service: SomeIPServiceConfig, source: tuple[str, int]
    ) -> None:
        """ClientServiceListener 回调：收到 Offer 时调用。"""
        if self._found:
            return
        if service.service_id != SERVICE_ID or service.instance_id != INSTANCE_ID:
            return
        # 提取 endpoint
        for opt in service.options_1:
            if hasattr(opt, "port") and hasattr(opt, "address"):
                addr = (str(opt.address), opt.port)
                self._found = addr
                self._event.set()
                logger.info("Discovered service at %s:%d", *addr)
                return

    def service_stopped(
        self, service: SomeIPServiceConfig, source: tuple[str, int]
    ) -> None:
        """ClientServiceListener 回调：服务下线时调用。"""
        pass  # 本例不需要

    async def wait_for_service(self, timeout: float = 10.0) -> tuple[str, int]:
        """等待服务被发现。"""
        self.sd_prot.discovery.watch_all_services(self)
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"Service 0x{SERVICE_ID:04x} not discovered within {timeout}s"
            ) from None
        finally:
            self.sd_prot.discovery.stop_watch_all_services(self)
        assert self._found is not None
        return self._found


# ── CLI / Main ───────────────────────────────────────────────────────
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

TEST_CASES = [
    ("add", {"a": 10, "b": 7}, 17),
    ("subtract", {"a": 50, "b": 18}, 32),
    ("multiply", {"a": 6, "b": 8}, 48),
]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SOME/IP Calculator Client")
    parser.add_argument(
        "--host", default=LOCAL_IP, help=f"local bind address (default: {LOCAL_IP})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=CLIENT_PORT,
        help=f"local unicast port (default: {CLIENT_PORT})",
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=_LOG_LEVELS, help="logging verbosity"
    )
    return parser.parse_args(argv)


async def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info(
        "Calculator Client starting — looking for service 0x%04x via SD", SERVICE_ID
    )

    # 1. 创建 Service Discovery
    sd_trsp_u, sd_trsp_m, sd_prot = await ServiceDiscoveryProtocol.create_endpoints(
        family=socket.AF_INET,
        local_addr=args.host,
        multicast_addr="224.224.224.245",
    )
    sd_prot.start()
    logger.info("SD started — listening for Offer on multicast")

    # 2. 创建 RPC 客户端的 unicast endpoint
    loop = asyncio.get_event_loop()
    rpc = CalculatorRpcClient()
    trsp, _ = await loop.create_datagram_endpoint(
        lambda: DatagramProtocolAdapter(rpc, is_multicast=False),
        local_addr=(args.host, args.port),
    )
    rpc.transport = trsp
    logger.info("RPC client bound to %s:%d", args.host, args.port)

    # 3. 等待 SD 发现服务
    watcher = ServiceWatcher(sd_prot)
    try:
        srv_addr = await watcher.wait_for_service(timeout=10.0)
    except RuntimeError as exc:
        logger.error("Service discovery failed: %s", exc)
        return 1

    # 4. 发起 RPC 调用
    logger.info("=" * 50)
    logger.info("Starting RPC calls to %s:%d", *srv_addr)
    passed = 0
    failed = 0

    for method_name, operands, expected in TEST_CASES:
        method_id = METHODS[method_name]
        payload = json.dumps(operands).encode("utf-8")

        t0 = time.monotonic()
        try:
            resp_bytes = await rpc.call(srv_addr, method_id, payload, timeout=5.0)
            elapsed = time.monotonic() - t0
            resp = json.loads(resp_bytes.decode("utf-8"))
            actual = resp["result"]

            ok = abs(actual - expected) < 0.001
            status = "PASS" if ok else "FAIL"
            if ok:
                passed += 1
            else:
                failed += 1

            logger.info(
                "%s  %s(%s) = %s  (expected %s)  %.1fms",
                status,
                method_name,
                operands,
                actual,
                expected,
                elapsed * 1000,
            )
        except asyncio.TimeoutError:
            failed += 1
            logger.error("TIMEOUT  %s(%s) — no response", method_name, operands)
        except RuntimeError as exc:
            failed += 1
            logger.error("ERROR  %s(%s) — %s", method_name, operands, exc)

    logger.info("=" * 50)
    logger.info(
        "Results: %d passed, %d failed, %d total", passed, failed, passed + failed
    )

    # 5. 清理
    sd_prot.stop()
    for t in (sd_trsp_u, sd_trsp_m, trsp):
        try:
            t.close()
        except Exception:
            pass

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(1)
