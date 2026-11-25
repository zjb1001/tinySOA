# Local vehicle data platform

拓扑：`LOCAL`（`InMemoryEventBus`，单进程）。
工程实践案例：`Container` 管理 4 个服务，验证依赖拓扑、生命周期和健康检查。

## 服务

| 服务 | ID | 依赖 |
|---|---|---|
| EngineService | `0x1000` | — |
| TransmissionService | `0x2000` | EngineService |
| DashboardService | `0x3000` | EngineService, TransmissionService |
| DiagnosticsService | `0x4000` | — |

依赖通过 `Service.dependencies` 声明，启动顺序由框架 `DependencyResolver` 计算；
`Container` 按拓扑序启动、按反序关闭，并执行 `on_start/on_stop/on_terminate` 钩子。
示例自身不再维护独立的依赖图。

## 目录

```text
local_vehicle_platform/
  app.py       服务定义 + Container 编排 + 健康检查
  tmux.sh      左: 平台运行 / 右: 架构说明
  Makefile     run/start/stop/status/logs/smoke/tmux
```

## 运行

```bash
make -C examples/local_vehicle_platform run
# 或
PYTHONPATH=$PWD:$PWD/src python -m examples.local_vehicle_platform.app --duration 15
```

常用参数：

```bash
python -m examples.local_vehicle_platform.app --dry-run          # 只验证注册与拓扑
python -m examples.local_vehicle_platform.app --duration 5 --health-interval 2.0
```

## 观察点

- 启动顺序：Engine → Transmission → Dashboard → Diagnostics。
- 关闭顺序完全相反。
- 健康检查 4/4 通过。
- 生命周期钩子写入 AUDIT 日志。
