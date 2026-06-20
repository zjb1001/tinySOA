"""SOME/IP Echo Publisher — 独立进程，发布事件。

**运行**

    终端1:
    cd examples/someip_echo
    PYTHONPATH=../../src:../../third_party/pysomeip/src python publisher.py

**SOME/IP 概念**

1. ``is_publisher=True``：本进程通过 SD（Service Discovery）通告自己的服务。
   - SD 周期性地向多播组 224.224.224.245:30490 发送 Offer 报文。
   - 其他进程通过监听该多播组可以发现本服务。

2. ``publish()``：把 tinySOA 的 EventMessage 编码为 SOME/IP event notification，
   通过 unicast 推送给所有订阅了对应 eventgroup 的 subscriber。

3. 端口分配：``publisher_port=30900`` 是本文进程的 unicast 端口基址。
   SomeIPEventBus 内部会根据 service_id 计算出具体端口。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
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
from _common import LOCAL_IP, MAPPING, PUBLISHER_PORT, TOPIC

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d | PUBLISHER | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("PUBLISHER")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SOME/IP Echo Publisher")
    p.add_argument("--count", type=int, default=5, help="messages to publish")
    p.add_argument("--interval", type=float, default=1.0, help="seconds between messages")
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    count = args.count
    interval = args.interval

    logger.info("starting (svc=0x%04x, port=%d, %d msgs @ %.1fs)",
                MAPPING.service_id, PUBLISHER_PORT, count, interval)

    # is_publisher=True → SD Offer 通告
    bus = SomeIPEventBus(
        mappings={TOPIC: MAPPING},
        local_ip=LOCAL_IP,
        publisher_port=PUBLISHER_PORT,
    )
    await bus.start()
    logger.info("started — SD Offer 已通告，等待 subscriber 发现 ...")
    await asyncio.sleep(2.0)  # 给 subscriber 时间做 SD FindSubscribe

    for i in range(count):
        payload = {"seq": i, "msg": f"hello-{i}", "ts": datetime.now().isoformat()}
        msg = EventMessage(topic=TOPIC, payload=payload)
        await bus.publish(msg)
        logger.info("published seq=%d", i)
        await asyncio.sleep(interval)

    await asyncio.sleep(1.0)  # 让最后一条在途消息落地
    await bus.stop()
    logger.info("stopped after %d messages", count)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
