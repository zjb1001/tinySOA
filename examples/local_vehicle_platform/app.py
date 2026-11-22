#!/usr/bin/env python3
"""Vehicle Data Platform — tinySOA 工程实践案例。

模拟车载系统中四个服务的完整生命周期：

  EngineService        — 发动机：发布 RPM / 温度事件
  TransmissionService  — 变速箱：依赖 RPM 事件，发布档位
  DashboardService     — 仪表盘：聚合显示，依赖 Engine + Transmission
  DiagnosticsService   — 诊断仪：独立运行，周期健康检查

工程要点：
  - Container 注册 / 去重 / 查找
  - LifecycleManager 依赖启停 + hooks（审计日志）
  - 自定义 HealthChecker（不只检查 status，还验证端点和事件定义）
  - InMemoryEventBus 服务间通信
  - argparse CLI + 结构化日志 + 优雅关闭 (SIGINT/SIGTERM)

运行（从 tinySOA 目录）:

    PYTHONPATH=.:src:third_party/pysomeip/src python -m examples.local_vehicle_platform.app \\
        --duration 10 --health-interval 2.0

退出码 0 表示正常退出，1 表示参数错误或启动失败。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Set

from tinysoa.core.errors import StateError
from tinysoa.core.model import Endpoint, Event, Method, Protocol, Service, ServiceStatus
from tinysoa.eventbus import EventMessage, InMemoryEventBus, Subscription
from tinysoa.runtime.container import Container
from tinysoa.runtime.lifecycle import (
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    LifecycleManager,
)

logger = logging.getLogger("tinysoa.example.vdp")

# ──────────────────────────────────────────────────────────────────
# 领域常量
# ──────────────────────────────────────────────────────────────────
SVC_ENGINE_ID = 0x1000
SVC_TRANSMISSION_ID = 0x2000
SVC_DASHBOARD_ID = 0x3000
SVC_DIAGNOSTICS_ID = 0x4000

# 依赖声明：key 依赖 values 全部 RUNNING 后才能启动
DEPENDENCY_GRAPH: Dict[int, List[int]] = {
    SVC_ENGINE_ID: [],  # 无依赖，最先启动
    SVC_TRANSMISSION_ID: [SVC_ENGINE_ID],  # 需要发动机 RPM
    SVC_DASHBOARD_ID: [SVC_ENGINE_ID, SVC_TRANSMISSION_ID],  # 聚合两者
    SVC_DIAGNOSTICS_ID: [],  # 独立运行
}

# 反向依赖 (用于 shutdown ordering)
REVERSE_DEPENDENCIES: Dict[int, List[int]] = {
    SVC_ENGINE_ID: [SVC_TRANSMISSION_ID, SVC_DASHBOARD_ID],
    SVC_TRANSMISSION_ID: [SVC_DASHBOARD_ID],
    SVC_DASHBOARD_ID: [],
    SVC_DIAGNOSTICS_ID: [],
}


# ──────────────────────────────────────────────────────────────────
# 自定义 HealthChecker
# ──────────────────────────────────────────────────────────────────
class VehicleHealthChecker(HealthChecker):
    """车辆服务健康检查器。

    除了检查 ServiceStatus，还验证：
    - 服务是否定义了至少一个 endpoint
    - 服务是否定义了至少一个 method 或 event
    """

    def check(self, service: Service) -> HealthCheckResult:
        """对单个服务执行健康检查。"""
        issues: List[str] = []

        if service.status != ServiceStatus.RUNNING:
            issues.append(f"status is {service.status.value} (expected running)")

        if not service.endpoints:
            issues.append("no endpoints defined")

        if not service.methods and not service.events:
            issues.append("no methods or events defined")

        if issues:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="; ".join(issues),
                checked_at=datetime.now(timezone.utc),
            )
        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="All checks passed",
            checked_at=datetime.now(timezone.utc),
        )


# ──────────────────────────────────────────────────────────────────
# 车辆数据平台应用
# ──────────────────────────────────────────────────────────────────
@dataclass
class VehicleDataPlatform:
    """车辆数据平台 — 组合 Container / Lifecycle / EventBus / 业务逻辑。

    职责：
      - 构建 4 个 Service 领域对象并注册到 Container
      - 用 LifecycleManager 按依赖顺序启停
      - 用 InMemoryEventBus 做服务间事件通信
      - 执行健康检查循环
    """

    container: Container = field(default_factory=Container)
    lifecycle: LifecycleManager = field(
        default_factory=lambda: LifecycleManager(Container(), VehicleHealthChecker())
    )
    event_bus: InMemoryEventBus = field(default_factory=InMemoryEventBus)
    services: Dict[int, Service] = field(default_factory=dict)
    _subscriptions: List[Subscription] = field(default_factory=list)
    _running: bool = False

    def __post_init__(self) -> None:
        """在 __init__ 后完成框架对象创建，避免 dataclass 默认值共享问题。"""
        self.container = Container()
        self.lifecycle = LifecycleManager(self.container, VehicleHealthChecker())
        self._register_services()
        self._register_hooks()

    # ──────────────────────────────────────────────────────────────
    # 服务构造
    # ──────────────────────────────────────────────────────────────
    def _register_services(self) -> None:
        """构造 4 个 Service 并注册到 Container。"""
        engine = Service(
            name="EngineService",
            id=SVC_ENGINE_ID,
            version="1.0.0",
            methods=[Method("get_rpm", 1), Method("get_temperature", 2)],
            events=[Event("rpm_changed", 1), Event("temperature_changed", 2)],
            endpoints=[Endpoint("127.0.0.1", 30100, Protocol.UDP)],
        )

        transmission = Service(
            name="TransmissionService",
            id=SVC_TRANSMISSION_ID,
            version="1.0.0",
            methods=[Method("get_gear", 1)],
            events=[Event("gear_changed", 1)],
            endpoints=[Endpoint("127.0.0.1", 30101, Protocol.UDP)],
        )

        dashboard = Service(
            name="DashboardService",
            id=SVC_DASHBOARD_ID,
            version="1.0.0",
            methods=[Method("get_display", 1)],
            events=[Event("display_updated", 1)],
            endpoints=[Endpoint("127.0.0.1", 30102, Protocol.TCP)],
        )

        diagnostics = Service(
            name="DiagnosticsService",
            id=SVC_DIAGNOSTICS_ID,
            version="1.0.0",
            methods=[Method("run_diagnostics", 1), Method("get_report", 2)],
            events=[],
            endpoints=[Endpoint("127.0.0.1", 30103, Protocol.TCP)],
        )

        for svc in (engine, transmission, dashboard, diagnostics):
            self.container.add_service(svc)
            self.services[svc.id] = svc

        logger.info("Registered %d services in Container", len(self.services))

    # ──────────────────────────────────────────────────────────────
    # 生命周期 Hooks
    # ──────────────────────────────────────────────────────────────
    def _register_hooks(self) -> None:
        """注册生命周期钩子：启停时记录审计日志。"""

        def on_start(svc: Service) -> None:
            logger.info(
                "[AUDIT] Service started: name=%s id=%s version=%s endpoints=%d",
                svc.name,
                hex(svc.id),
                svc.version,
                len(svc.endpoints),
            )

        def on_stop(svc: Service) -> None:
            logger.info(
                "[AUDIT] Service stopped: name=%s id=%s status=%s",
                svc.name,
                hex(svc.id),
                svc.status.value,
            )

        def on_terminate(svc: Service) -> None:
            logger.info(
                "[AUDIT] Service terminated: name=%s id=%s",
                svc.name,
                hex(svc.id),
            )

        self.lifecycle.add_on_start_hook(on_start)
        self.lifecycle.add_on_stop_hook(on_stop)
        self.lifecycle.add_on_terminate_hook(on_terminate)

    # ──────────────────────────────────────────────────────────────
    # 依赖感知的启动 / 停止
    # ──────────────────────────────────────────────────────────────
    def _topological_order(self) -> List[int]:
        """返回依赖拓扑顺序 (启动顺序)。无依赖的在前。"""
        visited: Set[int] = set()
        order: List[int] = []

        def visit(svc_id: int) -> None:
            if svc_id in visited:
                return
            visited.add(svc_id)
            for dep_id in DEPENDENCY_GRAPH.get(svc_id, []):
                visit(dep_id)
            order.append(svc_id)

        for sid in self.services:
            visit(sid)
        return order

    def startup_ordered(self) -> None:
        """按依赖顺序启动所有服务。"""
        order = self._topological_order()
        logger.info(
            "Startup order: %s",
            " → ".join(self.services[sid].name for sid in order),
        )
        for sid in order:
            try:
                self.lifecycle.start_service(sid)
            except StateError as exc:
                logger.error("Cannot start %s: %s", self.services[sid].name, exc)
                raise

    def shutdown_ordered(self) -> None:
        """按依赖反序停止所有服务。"""
        order = list(reversed(self._topological_order()))
        logger.info(
            "Shutdown order: %s",
            " → ".join(self.services[sid].name for sid in order),
        )
        for sid in order:
            svc = self.services[sid]
            if svc.status == ServiceStatus.RUNNING:
                try:
                    self.lifecycle.stop_service(sid)
                except StateError as exc:
                    logger.warning("Cannot stop %s: %s", svc.name, exc)
        for sid in order:
            svc = self.services[sid]
            if svc.status != ServiceStatus.TERMINATED:
                try:
                    self.lifecycle.terminate_service(sid)
                except StateError as exc:
                    logger.warning("Cannot terminate %s: %s", svc.name, exc)

    # ──────────────────────────────────────────────────────────────
    # 业务模拟
    # ──────────────────────────────────────────────────────────────
    async def simulate_engine(self, stop_event: asyncio.Event) -> None:
        """模拟发动机：每秒发布 RPM 和温度事件。"""
        svc = self.services[SVC_ENGINE_ID]
        rpm = 800  # 怠速
        temp = 85.0

        logger.info(
            "[Engine] started — publishing rpm_changed + temperature_changed every second"
        )
        while not stop_event.is_set():
            rpm = max(600, min(7000, rpm + (50 if rpm < 2000 else -30)))
            temp = max(70.0, min(110.0, temp + (0.5 if temp < 95 else -0.3)))

            rpm_message = EventMessage(
                topic=f"vehicle.{svc.name}.rpm_changed",
                payload={"rpm": rpm, "unit": "rpm"},
            )
            await self.event_bus.publish(rpm_message)

            temperature_message = EventMessage(
                topic=f"vehicle.{svc.name}.temperature_changed",
                payload={"temperature": round(temp, 1), "unit": "celsius"},
            )
            await self.event_bus.publish(temperature_message)
            await asyncio.sleep(1.0)

    async def simulate_transmission(self, stop_event: asyncio.Event) -> None:
        """模拟变速箱：订阅 RPM 事件，计算档位并发布。"""
        svc = self.services[SVC_TRANSMISSION_ID]
        current_gear = 0  # 停车

        async def on_rpm(msg: EventMessage) -> None:
            nonlocal current_gear
            rpm = msg.payload.get("rpm", 0)
            # 简化的自动换挡逻辑
            if rpm < 1000:
                new_gear = 1
            elif rpm < 2000:
                new_gear = 2
            elif rpm < 3000:
                new_gear = 3
            elif rpm < 4000:
                new_gear = 4
            else:
                new_gear = 5
            if new_gear != current_gear:
                current_gear = new_gear
                gear_message = EventMessage(
                    topic=f"vehicle.{svc.name}.gear_changed",
                    payload={"gear": current_gear, "rpm": rpm},
                )
                await self.event_bus.publish(gear_message)
                logger.debug("[Transmission] gear=%d @ rpm=%d", current_gear, rpm)

        sub = self.event_bus.subscribe("vehicle.EngineService.rpm_changed", on_rpm)
        self._subscriptions.append(sub)

        logger.info(
            "[Transmission] subscribed to EngineService.rpm_changed, computing gear"
        )
        await stop_event.wait()

    async def simulate_dashboard(self, stop_event: asyncio.Event) -> None:
        """模拟仪表盘：订阅发动机和变速箱事件，聚合显示。"""
        state: Dict[str, object] = {"rpm": 0, "temp": 0.0, "gear": 0}

        async def on_rpm(msg: EventMessage) -> None:
            state["rpm"] = msg.payload.get("rpm", 0)
            await self._update_display(state)

        async def on_temp(msg: EventMessage) -> None:
            state["temp"] = msg.payload.get("temperature", 0.0)
            await self._update_display(state)

        async def on_gear(msg: EventMessage) -> None:
            state["gear"] = msg.payload.get("gear", 0)
            await self._update_display(state)

        for topic, handler in [
            ("vehicle.EngineService.rpm_changed", on_rpm),
            ("vehicle.EngineService.temperature_changed", on_temp),
            ("vehicle.TransmissionService.gear_changed", on_gear),
        ]:
            sub = self.event_bus.subscribe(topic, handler)
            self._subscriptions.append(sub)

        logger.info("[Dashboard] subscribed to Engine + Transmission events")
        await stop_event.wait()

    async def _update_display(self, state: Dict[str, object]) -> None:
        """仪表盘显示更新（模拟 CAN 总线上的仪表盘帧）。"""
        payload = {
            "rpm": state["rpm"],
            "temperature": state["temp"],
            "gear": state["gear"],
            "warning": state.get("temp", 0) > 100,
        }
        message = EventMessage(
            topic="vehicle.DashboardService.display_updated",
            payload=payload,
        )
        await self.event_bus.publish(message)

    async def simulate_diagnostics(
        self, stop_event: asyncio.Event, interval: float
    ) -> None:
        """模拟诊断仪：定期检查所有服务健康状态。"""
        logger.info("[Diagnostics] started — health check every %.1fs", interval)

        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
            else:
                break  # stop_event was set

            report = self.lifecycle.check_all_health()
            healthy = sum(
                1 for r in report.values() if r.status == HealthStatus.HEALTHY
            )
            total = len(report)
            logger.info(
                "[Diagnostics] Health report: %d/%d healthy",
                healthy,
                total,
            )
            for sid, result in report.items():
                level = (
                    logging.INFO
                    if result.status == HealthStatus.HEALTHY
                    else logging.WARNING
                )
                logger.log(
                    level,
                    "  %s (0x%x): %s — %s",
                    self.services[sid].name,
                    sid,
                    result.status.value,
                    result.message,
                )

    # ──────────────────────────────────────────────────────────────
    # 主运行循环
    # ──────────────────────────────────────────────────────────────
    async def run(self, duration: float = 10.0, health_interval: float = 2.0) -> None:
        """运行车辆数据平台。"""
        logger.info("=" * 60)
        logger.info("Vehicle Data Platform — starting up")
        logger.info("=" * 60)

        # 1. 打印服务清单
        logger.info("Services in container:")
        for svc in self.container.list_services():
            logger.info(
                "  %s (0x%x) v%s | methods=%d events=%d endpoints=%d status=%s",
                svc.name,
                svc.id,
                svc.version,
                len(svc.methods),
                len(svc.events),
                len(svc.endpoints),
                svc.status.value,
            )

        # 2. 依赖感知启动
        logger.info("--- Phase 1: Ordered startup ---")
        self.startup_ordered()

        # 3. 验证运行状态
        running = self.container.get_running_services()
        logger.info("Running services: %d/%d", len(running), len(self.services))
        assert len(running) == len(
            self.services
        ), f"Expected all {len(self.services)} services running, got {len(running)}"

        # 4. 启动业务协程
        stop_event = asyncio.Event()
        self._running = True

        tasks = [
            asyncio.create_task(self.simulate_engine(stop_event)),
            asyncio.create_task(self.simulate_transmission(stop_event)),
            asyncio.create_task(self.simulate_dashboard(stop_event)),
            asyncio.create_task(self.simulate_diagnostics(stop_event, health_interval)),
        ]

        logger.info("--- Phase 2: Running (%.0fs) ---", duration)
        try:
            await asyncio.sleep(duration)
        except asyncio.CancelledError:
            logger.info("Run cancelled by signal")
        finally:
            logger.info("--- Phase 3: Ordered shutdown ---")
            stop_event.set()
            self._running = False

            # 等待业务协程结束
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

            # 5. 最终健康报告
            logger.info("Final health report before shutdown:")
            report = self.lifecycle.check_all_health()
            for sid, result in report.items():
                logger.info("  %s: %s", self.services[sid].name, result.status.value)

            # 6. 依赖反序停止
            self.shutdown_ordered()

            # 7. 验证全部终止
            for svc in self.container.list_services():
                assert (
                    svc.status == ServiceStatus.TERMINATED
                ), f"{svc.name} expected TERMINATED, got {svc.status.value}"

        logger.info("=" * 60)
        logger.info("Vehicle Data Platform — shutdown complete")
        logger.info("=" * 60)


# ──────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vehicle Data Platform — tinySOA 工程实践案例",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              %(prog)s --duration 10 --health-interval 2.0
              %(prog)s --duration 30 --health-interval 5.0 --log-level DEBUG
              %(prog)s --dry-run                   # 仅验证服务可注册，不运行
        """),
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="平台运行时长，单位秒 (default: 10.0)",
    )
    parser.add_argument(
        "--health-interval",
        type=float,
        default=2.0,
        help="诊断仪健康检查间隔，单位秒 (default: 2.0)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=_LOG_LEVELS,
        help="日志级别 (default: INFO)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅验证服务注册和拓扑排序，不实际运行",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    platform = VehicleDataPlatform()

    if args.dry_run:
        logger.info("Dry-run mode — validating service registration")
        svcs = platform.container.list_services()
        logger.info("Registered %d services:", len(svcs))
        for svc in svcs:
            deps = DEPENDENCY_GRAPH.get(svc.id, [])
            dep_names = [platform.services[d].name for d in deps] if deps else ["none"]
            logger.info(
                "  %s (0x%x) depends on: %s", svc.name, svc.id, ", ".join(dep_names)
            )

        order = platform._topological_order()
        logger.info(
            "Topological order: %s",
            " → ".join(platform.services[sid].name for sid in order),
        )
        logger.info(
            "Reverse shutdown order: %s",
            " → ".join(platform.services[sid].name for sid in reversed(order)),
        )
        return 0

    loop = asyncio.new_event_loop()
    main_task: Optional[asyncio.Task] = None

    def _graceful_shutdown() -> None:
        logger.info("Received signal, initiating graceful shutdown...")
        if main_task is not None and not main_task.done():
            main_task.cancel()

    try:
        # 注册信号处理（必须从主线程的事件循环中）
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _graceful_shutdown)
    except NotImplementedError:
        # Windows / 某些环境不支持 add_signal_handler
        pass

    try:
        main_task = loop.create_task(platform.run(args.duration, args.health_interval))
        loop.run_until_complete(main_task)
        return 0
    except asyncio.CancelledError:
        return 0
    except Exception as exc:
        logger.error("Platform failed: %s", exc, exc_info=True)
        return 1
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()


if __name__ == "__main__":
    sys.exit(main())
