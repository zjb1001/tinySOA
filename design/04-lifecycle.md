# 服务生命周期管理设计

## 1. 状态机

### 1.1 基础状态机 (Phase 1)

框架核心服务状态机确保服务经过规范的生命周期阶段：

```
INIT → REGISTERED → STARTING → RUNNING ↔ DEGRADED → STOPPING → STOPPED → TERMINATED
                        ▲                        │
                        └────────────────────────┘ (降级恢复)
```

**状态定义**:

| 状态 | 含义 |
|------|------|
| `INIT` | 服务对象构造完成，尚未注册 |
| `REGISTERED` | 已在容器中注册，未启动 |
| `STARTING` | 初始化资源、绑定端口、等待依赖——尚未接受流量 |
| `RUNNING` | 正常运行中，所有依赖健康 |
| `DEGRADED` | 核心功能可用，但部分非关键依赖不可用或性能下降 |
| `STOPPING` | 正在关闭，拒绝新请求，等待现有请求处理完毕 |
| `STOPPED` | 已停止，可重新启动 |
| `TERMINATED` | 终态，资源已释放，不可恢复 |

**状态转换守卫**：所有状态变更必须通过 `service.transition(to)` 方法。非法转换（如 `RUNNING → INIT`）抛出 `StateError`。禁止直接 `status=` 赋值。

### 1.2 健康状态

健康状态与生命周期状态正交，由 `HealthChecker` (ABC) 独立评估：

| 健康状态 | 含义 | 可能触发 |
|---------|------|---------|
| `HEALTHY` | 正常运行 | — |
| `UNHEALTHY` | 异常 | 从 `RUNNING` 转换到 `DEGRADED` 或触发重启 |
| `UNKNOWN` | 状态不明 | 启动初期、健康检查未完成 |

## 2. 启动流程

1. **加载配置**：解析文件与环境变量，构建运行时配置。
2. **初始化组件**：Registry、SD、拦截器、编解码器、日志、指标导出、内部事件总线。
3. **绑定传输**：创建传输层端点（SOME/IP datagram 或 TCP）。
4. **依赖检查**：通过 `InternalEventBus` 等待声明的依赖服务可用 (SD 发现)；超时则进入 `DEGRADED` 降级模式。
5. **服务注册**：在本地 Registry 登记，二阶段提交到 SD（见 02-core-components.md §1.5.2 一致性模型）。
6. **健康检查**：暴露健康探针。
7. **Ready**：触发 `SERVICE_READY` 内部事件，进入 `RUNNING`。

1. **加载配置**：ConfigLoader 解析文件与环境变量
2. **初始化组件**：Registry、SD、拦截器、编解码器、日志、指标
3. **绑定传输**：创建传输层（SOME/IP datagram or TCP endpoint）
4. **依赖检查**: 通过 InternalEventBus 等待声明的依赖服务可用 (SD 发现)；超时则进入 DEGRADED
5. **服务注册**：在本地 Container 登记，二阶段提交到 SD (见 02-core-components.md §1.5.2)
6. **健康检查**：暴露健康探针
7. **Ready**：触发 `SERVICE_READY` 内部事件，进入 `RUNNING`

## 3. 停止流程（优雅关闭）

1. **进入 `STOPPING`**：标记状态，拒绝新的 RPC 请求（返回特定错误码）；允许正在处理的请求继续执行（设置超时，如 5s）
2. **停止 SD Offer**：发送 SD StopOffer 消息，通知客户端服务下线
3. **取消订阅**：主动取消对其他服务的订阅，停止事件循环任务
4. **注销服务**：从本地 Registry 注销
5. **释放资源**：关闭传输连接、清理缓存、释放文件句柄
6. **进入 `STOPPED`** → 最终 `TERMINATED`

## 4. 依赖管理

### 4.1 依赖声明

```python
@Service(
    service_id=0x1234,
    instance_id=0x0001,
    version=(1, 0),
    depends_on=[
        # 绝对依赖 (启动前必须可用)
        ServiceDependency(
            service_id=0x5678,
            version=(1, 0),
            required=True,
            timeout_s=10
        ),
        # 可选依赖
        ServiceDependency(
            service_id=0x9999,
            required=False
        )
    ]
)
class MyService:
    pass
```

### 4.2 启动顺序管理

`DependencyResolver` 管理多个服务的启动顺序。算法：拓扑排序 + 并行启动。同层服务可并行启动，依赖的服务必须先完成初始化。循环依赖拒绝启动并告警。

### 4.3 故障转移与降级

`DegradedMode` 管理非关键依赖不可用时的降级策略。当所有必需依赖 (required=True) 可用但可选依赖部分不可用时，服务进入 `DEGRADED` 状态——核心功能继续提供，非关键功能降级或返回缓存结果。

### 4.4 内部事件与生命周期集成

`InternalEventBus` 驱动生命周期事件流（详见 [09-internal-event-model.md](09-internal-event-model.md)）：

| 事件 | 触发时机 |
|------|---------|
| `SERVICE_INITIALIZING` | 开始初始化 |
| `SERVICE_READY` | 就绪，可接受流量 |
| `SERVICE_DEGRADED` | 进入降级模式 |
| `SERVICE_STOPPING` | 正在停止 |
| `SERVICE_STOPPED` | 已停止 |
| `INSTANCE_DISCOVERED` | 发现新实例 |
| `INSTANCE_LOST` | 实例离线 |
| `DEPENDENCY_SATISFIED` | 依赖服务变为可用 |
| `DEPENDENCY_LOST` | 依赖服务变为不可用 |

## 5. 健康与就绪

- **Liveness (存活)**：进程是否存活，死锁或 Crash 则重启。
- **Readiness (就绪)**：是否准备好接收流量——由 `HealthChecker` (ABC) 评估。
- **健康检查钩子**：`check_health(service_id) → HealthCheckResult`，可注册自定义健康探针。
- **与 Registry/SD 集成**：健康变化触发内部事件，影响客户端端点选择与 SD 通告。

## 6. 故障与恢复

- **自动重启**：基于失败计数与时间窗口的可选策略。
- **会话恢复**：`SessionStorage` 管理的会话 ID 在重启后重建，消费者可继续订阅。
- **复位通知**：事件组广播 `reset`，消费者感知服务重启。
- **优雅降级**：非关键依赖不可用时，核心功能继续提供，非关键功能降级。
