#!/usr/bin/env python3
"""Local Dependency Events — 控制面事件与依赖协调案例。

场景：

  DatabaseService        本地数据库，无依赖
  SensorGatewayService   依赖 DatabaseService
  DashboardService       依赖 SensorGatewayService + 远程 RemoteTelemetryService
  RemoteTelemetryService 不在本地 Container 中，通过模拟 SOME/IP SD 的
                         INSTANCE_DISCOVERED 事件变为可用

工程要点：

  - Container + Service.dependencies 声明依赖
  - LifecycleManager 异步方法按拓扑序启动并发布控制面事件
  - InternalEventDispatcher 强类型、进程内、无 ABC 的事件分发
  - DependencyCoordinator 先订阅事件、再用本地快照补齐，等待远程依赖
  - 优雅关闭：SERVICE_STOPPED / DEPENDENCY_LOST 事件

运行（从 tinySOA 目录）:

    PYTHONPATH=.:src:third_party/pysomeip/src \\
        python -m examples.local_dependency_events.app

退出码 0 表示完整流程成功。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import textwrap
from typing import Dict, List, Mapping, Optional, Sequence

from tinysoa.core.errors import DependencyError
from tinysoa.core.model import Event, Method, Service, ServiceDependency
from tinysoa.runtime import (
    Container,
    DependencyCoordinator,
    InternalEvent,
    InternalEventDispatcher,
    InternalEventType,
    LifecycleManager,
)

logger = logging.getLogger("tinysoa.example.dependency_events")

SVC_DATABASE_ID = 0x5000
SVC_SENSOR_GATEWAY_ID = 0x5100
SVC_DASHBOARD_ID = 0x5200
SVC_OPTIONAL_ANALYTICS_ID = 0x5300
SVC_REMOTE_TELEMETRY_ID = 0x6000

SERVICE_NAMES: Mapping[int, str] = {
    SVC_DATABASE_ID: "DatabaseService",
    SVC_SENSOR_GATEWAY_ID: "SensorGatewayService",
    SVC_DASHBOARD_ID: "DashboardService",
    SVC_OPTIONAL_ANALYTICS_ID: "AnalyticsService",
    SVC_REMOTE_TELEMETRY_ID: "RemoteTelemetryService",
}

REMOTE_INSTANCE_ID = 0x0001


def _label(service_id: int) -> str:
    return f"{SERVICE_NAMES.get(service_id, 'Service')}({service_id:#06x})"


def _build_services() -> Dict[int, Service]:
    database = Service(
        name="DatabaseService",
        id=SVC_DATABASE_ID,
        version="1.0.0",
        methods=[Method("get", 1), Method("put", 2)],
        events=[Event("record_written", 1)],
    )
    sensor_gateway = Service(
        name="SensorGatewayService",
        id=SVC_SENSOR_GATEWAY_ID,
        version="1.0.0",
        methods=[Method("read_sensor", 1)],
        events=[Event("reading", 1)],
        dependencies=[ServiceDependency(SVC_DATABASE_ID, timeout_s=2.0)],
    )
    dashboard = Service(
        name="DashboardService",
        id=SVC_DASHBOARD_ID,
        version="1.0.0",
        methods=[Method("render", 1)],
        events=[Event("display_updated", 1)],
        dependencies=[
            ServiceDependency(SVC_SENSOR_GATEWAY_ID, timeout_s=2.0),
            ServiceDependency(SVC_REMOTE_TELEMETRY_ID, timeout_s=2.0),
            # 可选依赖：缺失时不应阻塞启动
            ServiceDependency(SVC_OPTIONAL_ANALYTICS_ID, required=False, timeout_s=0.5),
        ],
    )
    return {service.id: service for service in (database, sensor_gateway, dashboard)}


class DependencyEventsDemo:
    """Single-process control-plane demo."""

    def __init__(self) -> None:
        self.container = Container()
        self.dispatcher = InternalEventDispatcher()
        self.lifecycle = LifecycleManager(
            self.container, internal_events=self.dispatcher
        )
        self.services = _build_services()
        for service in self.services.values():
            self.container.add_service(service)

        self.events: List[InternalEvent] = []
        self._remote_discovered = False
        self._subscribe_audit()

    # ------------------------------------------------------------------ plan

    def log_plan(self) -> None:
        """Print the dependency graph and local startup order."""
        resolver = self.lifecycle.dependency_resolver
        order = " -> ".join(
            self.services[service_id].name for service_id in resolver.startup_order()
        )
        logger.info("local startup order: %s", order)
        for service in self.services.values():
            if not service.dependencies:
                logger.info("  %s depends on: none", service.name)
                continue
            parts = []
            for dependency in service.dependencies:
                kind = "required" if dependency.required else "optional"
                parts.append(
                    f"{_label(dependency.service_id)}"
                    f" [{kind}, timeout={dependency.timeout_s}s]"
                )
            logger.info("  %s depends on: %s", service.name, ", ".join(parts))
        logger.info(
            "remote dependency: %s — simulated via INSTANCE_DISCOVERED",
            _label(SVC_REMOTE_TELEMETRY_ID),
        )

    # --------------------------------------------------------------- runtime

    async def run(
        self,
        *,
        duration: float = 2.0,
        discovery_delay: float = 0.3,
        wait_timeout: float = 2.0,
    ) -> int:
        logger.info("=== Phase 1: dependency plan ===")
        self.log_plan()
        try:
            await self._startup(discovery_delay, wait_timeout)
            logger.info("=== Phase 3: steady state ===")
            await self._steady(duration)
            return 0
        finally:
            logger.info("=== Phase 4: graceful shutdown ===")
            await self._shutdown()

    async def _startup(self, discovery_delay: float, wait_timeout: float) -> None:
        logger.info("=== Phase 2: ordered startup + dependency wait ===")

        await self.lifecycle.astart_service(SVC_DATABASE_ID)
        await self.lifecycle.astart_service(SVC_SENSOR_GATEWAY_ID)

        dashboard = self.services[SVC_DASHBOARD_ID]
        coordinator = DependencyCoordinator(dashboard, self.container, self.dispatcher)
        logger.info(
            "dashboard waits for %s (local) + %s (remote SD event)",
            _label(SVC_SENSOR_GATEWAY_ID),
            _label(SVC_REMOTE_TELEMETRY_ID),
        )
        waiter = asyncio.create_task(
            coordinator.wait_for_dependencies(timeout=wait_timeout)
        )
        try:
            # Let the coordinator subscribe before discovery is published.
            await asyncio.sleep(0.05)
            logger.info("simulating SD discovery in %.2fs ...", discovery_delay)
            await asyncio.sleep(discovery_delay)
            self._remote_discovered = True
            await self.dispatcher.publish(
                InternalEvent.instance_discovered(
                    SVC_REMOTE_TELEMETRY_ID,
                    REMOTE_INSTANCE_ID,
                    endpoint=("127.0.0.1", 30500),
                    version=(1, 0),
                    discovery_method="sd_protocol",
                )
            )
            try:
                await waiter
            except DependencyError as exc:
                logger.error("dependency wait failed: %s", exc)
                raise
        finally:
            if not waiter.done():
                waiter.cancel()
                try:
                    await waiter
                except asyncio.CancelledError:
                    pass

        logger.info("all required dependencies satisfied")
        await self.lifecycle.astart_service(SVC_DASHBOARD_ID)
        self._verify_ordering()

    async def _steady(self, duration: float) -> None:
        if duration <= 0:
            return
        logger.info("steady state for %.1fs (Ctrl+C to stop early)", duration)
        await asyncio.sleep(duration)

    async def _shutdown(self) -> None:
        await self.lifecycle.astop_all()
        if self._remote_discovered:
            await self.dispatcher.publish(
                InternalEvent.instance_lost(
                    SVC_REMOTE_TELEMETRY_ID,
                    REMOTE_INSTANCE_ID,
                    reason="explicit_stop",
                )
            )
        counts: Dict[str, int] = {}
        for event in self.events:
            counts[event.event_type.value] = counts.get(event.event_type.value, 0) + 1
        summary = ", ".join(
            f"{event_type}={count}" for event_type, count in sorted(counts.items())
        )
        logger.info("event summary: %s", summary)

    # ---------------------------------------------------------------- audit

    def _subscribe_audit(self) -> None:
        for event_type in (
            InternalEventType.SERVICE_READY,
            InternalEventType.SERVICE_STOPPED,
            InternalEventType.DEPENDENCY_SATISFIED,
            InternalEventType.DEPENDENCY_LOST,
            InternalEventType.INSTANCE_DISCOVERED,
            InternalEventType.INSTANCE_LOST,
        ):
            self.dispatcher.subscribe(event_type, self._record_event)

    async def _record_event(self, event: InternalEvent) -> None:
        self.events.append(event)
        source = _label(event.source_service_id)
        if event.related_instance_id is not None:
            source += f"#{event.related_instance_id}"
        target = ""
        if (
            event.related_service_id is not None
            and event.related_service_id != event.source_service_id
        ):
            target = f" -> {_label(event.related_service_id)}"
        logger.info(
            "[event] %-22s %s%s",
            event.event_type.value,
            source,
            target,
        )

    # --------------------------------------------------------------- checks

    def _event_index(self, predicate) -> int:
        for index, event in enumerate(self.events):
            if predicate(event):
                return index
        return -1

    def _verify_ordering(self) -> None:
        discovery_index = self._event_index(
            lambda event: event.event_type is InternalEventType.INSTANCE_DISCOVERED
            and event.related_service_id == SVC_REMOTE_TELEMETRY_ID
        )
        dashboard_index = self._event_index(
            lambda event: event.event_type is InternalEventType.SERVICE_READY
            and event.source_service_id == SVC_DASHBOARD_ID
        )
        if discovery_index < 0 or dashboard_index < 0:
            raise RuntimeError(
                "expected discovery and dashboard-ready events were not observed"
            )
        if discovery_index > dashboard_index:
            raise RuntimeError(
                "dashboard started before remote telemetry was discovered"
            )
        logger.info("check: remote telemetry discovered before dashboard READY ✓")


# --------------------------------------------------------------------- CLI


_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local dependency events demo (control-plane events + coordinator)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              %(prog)s
              %(prog)s --discovery-delay 1.0 --duration 3.0
              %(prog)s --dry-run                  # 只打印依赖计划
            """),
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=2.0,
        help="steady-state duration in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--discovery-delay",
        type=float,
        default=0.3,
        help="simulated SD discovery delay in seconds (default: 0.3)",
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=2.0,
        help="dependency wait timeout in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=_LOG_LEVELS,
        help="log level (default: INFO)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the dependency plan only",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    demo = DependencyEventsDemo()
    if args.dry_run:
        demo.log_plan()
        return 0

    loop = asyncio.new_event_loop()
    main_task: Optional[asyncio.Task] = None

    def _graceful_shutdown() -> None:
        logger.info("received signal, shutting down...")
        if main_task is not None and not main_task.done():
            main_task.cancel()

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _graceful_shutdown)
    except NotImplementedError:
        pass

    try:
        main_task = loop.create_task(
            demo.run(
                duration=args.duration,
                discovery_delay=args.discovery_delay,
                wait_timeout=args.wait_timeout,
            )
        )
        loop.run_until_complete(main_task)
        return 0
    except asyncio.CancelledError:
        return 0
    except Exception as exc:
        logger.error("demo failed: %s", exc, exc_info=True)
        return 1
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()


if __name__ == "__main__":
    sys.exit(main())
