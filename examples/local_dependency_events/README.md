# local_dependency_events

拓扑：`LOCAL`（单进程、无网络）。

控制面事件与依赖协调案例：本地服务按拓扑序启动，远程依赖通过模拟
SOME/IP SD 的 `INSTANCE_DISCOVERED` 事件变为可用，`DependencyCoordinator`
在两类来源都满足后才允许 `DashboardService` 启动。

## 这个案例在治理模型中的位置

- **业务数据面**：服务之间的业务事件走 `EventBus`（本案例不涉及）。
- **治理控制面**：`LifecycleManager` 发布状态事实，`InternalEventDispatcher` 分发，
  `DependencyCoordinator` 订阅并做出决策。
- 这个案例展示的是框架作为“服务状态所有者”的一面：`DashboardService` 能否启动，
  不由代码调用顺序决定，而由“必需依赖事实是否满足”决定。

治理模型背景见 [design/10-control-plane-governance.md](../../design/10-control-plane-governance.md)。

## 服务

| 服务 | ID | 依赖 |
|---|---|---|
| DatabaseService | `0x5000` | — |
| SensorGatewayService | `0x5100` | DatabaseService (required) |
| DashboardService | `0x5200` | SensorGatewayService (required)、RemoteTelemetryService (required, remote)、AnalyticsService (optional) |
| RemoteTelemetryService | `0x6000` | 不在本地 Container；由事件模拟发现 |

## 事件流

```text
SERVICE_READY database
SERVICE_READY sensor_gateway
DEPENDENCY_SATISFIED sensor_gateway <- database
dashboard waits for sensor_gateway + remote_telemetry
INSTANCE_DISCOVERED remote_telemetry#1
SERVICE_READY dashboard
...
SERVICE_STOPPED dashboard
DEPENDENCY_LOST dashboard <- sensor_gateway
SERVICE_STOPPED sensor_gateway
DEPENDENCY_LOST sensor_gateway <- database
SERVICE_STOPPED database
INSTANCE_LOST remote_telemetry#1
```

## 目录

```text
local_dependency_events/
  app.py       服务定义 + 控制面事件 + 依赖等待 + 优雅关闭
  tmux.sh      左: 运行日志 / 右: 场景说明
  Makefile     run/start/stop/status/logs/smoke/tmux/clean
```

## 运行

```bash
make -C examples/local_dependency_events run
# 或
PYTHONPATH=$PWD:$PWD/src python -m examples.local_dependency_events.app
```

常用参数：

```bash
python -m examples.local_dependency_events.app --dry-run
python -m examples.local_dependency_events.app \
  --duration 5 --discovery-delay 1.0 --wait-timeout 2.0
```

- `--duration`：Dashboard 就绪后的稳态运行时间。
- `--discovery-delay`：模拟远程服务被发现前的延迟。
- `--wait-timeout`：`DependencyCoordinator` 等待全部必需依赖的超时。

## 观察点

- 启动顺序：Database → SensorGateway → Dashboard。
- `DashboardService` 的 `SERVICE_READY` 必须出现在 `INSTANCE_DISCOVERED` 之后。
- 可选依赖 `AnalyticsService` 缺失时不会阻塞。
- 关闭顺序：Dashboard → SensorGateway → Database，并发布 `DEPENDENCY_LOST`。
- 事件摘要会打印每类控制面事件的计数。

## 使用的框架 API

```python
dispatcher = InternalEventDispatcher()
lifecycle = LifecycleManager(container, internal_events=dispatcher)
await lifecycle.astart_service(service_id)   # 发布 SERVICE_READY / DEPENDENCY_*
await lifecycle.astop_all()                  # 反序停止并发布事件

coordinator = DependencyCoordinator(dashboard, container, dispatcher)
await coordinator.wait_for_dependencies(timeout=2.0)
```

`InternalEventDispatcher` 是具体的进程内分发器，不是与业务 `EventBus` 对称的
ABC：没有序列化、没有网络、没有 `start/stop`。
