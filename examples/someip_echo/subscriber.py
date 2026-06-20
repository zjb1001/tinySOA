"""SOME/IP Echo Subscriber — 独立进程，接收事件。

**运行**

    终端2（先起 publisher 的 SD Offer 收敛后再跑，或直接跑 ——
          subscriber 进入 SD Find 模式，等待 Offer 到达后自动订阅）:
    cd examples/someip_echo
    PYTHONPATH=../../src:../../third_party/pysomeip/src python subscriber.py

**SOME/IP 概念**

1. ``is_publisher=False``：本进程只做 **发现 + 订阅**，不对外通告服务。
   - 内部启动 SD supplicant，监听多播组 224.224.224.245:30490，
     等待 publisher 的 Offer 到达后发起 Subscribe。

2. ``subscribe()``：订阅一个 topic。
   - SomeIPEventBus 内部会触发 SD FindSubscribe 握手。
   - 有一个内置的 ~5s 交错延迟，避免订阅风暴。

3. 收到事件后，handler 被调用 —— 参数是 tinySOA 的 EventMessage。
   上层代码不需要知道 SOME/IP 细节。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 让当前目录下的 _common.py 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 同时需要 tinysoa + someip；如果没有设置 PYTHONPATH，自动补上
_repo = Path(__file__).resolve().parents[2]
for _p in (str(_repo / "src"), str(_repo / "third_party" / "pysomeip" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tinysoa.eventbus.message import EventMessage
from tinysoa.eventbus.someip import SomeIPEventBus
from _common import LOCAL_IP, MAPPING, SUBSCRIBER_PORT, TOPIC

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d | SUBSCRIBER | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SUBSCRIBER")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SOME/IP Echo Subscriber")
    p.add_argument("--want", type=int, default=3, help="events to receive before stopping")
    p.add_argument("--timeout", type=float, default=40.0, help="max seconds to wait")
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    want = args.want
    timeout = args.timeout

    logger.info("starting (svc=0x%04x, port=%d, want=%d, timeout=%.0fs)",
                MAPPING.service_id, SUBSCRIBER_PORT, want, timeout)

    # is_publisher=False → 不对外通告，只做 SD FindSubscribe
    bus = SomeIPEventBus(
        mappings={TOPIC: MAPPING},
        local_ip=LOCAL_IP,
        publisher_port=SUBSCRIBER_PORT,
        is_publisher=False,
    )
    await bus.start()
    logger.info("started — 进入 SD Find 模式，等待 publisher Offer ...")

    received: list[dict] = []
    done = asyncio.Event()

    async def on_event(msg: EventMessage) -> None:
        p = msg.payload if isinstance(msg.payload, dict) else {"raw": msg.payload}
        received.append(p)
        logger.info("RECEIVED seq=%s → %s", p.get("seq"), p)
        if len(received) >= want:
            done.set()

    bus.subscribe(TOPIC, on_event)

    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
        logger.info("✓ SUCCESS — received %d/%d events", len(received), want)
    except asyncio.TimeoutError:
        logger.warning("✗ TIMEOUT — received %d/%d events", len(received), want)
        logger.warning("  如果看到 'discarding subscribe for unknown service'，")
        logger.warning("  这是 pysomeip 在 WSL2 回环网上的已知竞态，不影响概念理解。")

    await bus.stop()
    logger.info("stopped after %d events", len(received))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
