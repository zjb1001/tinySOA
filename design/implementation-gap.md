# Implementation Gap Analysis

> 设计→实现映射的唯一信息源。设计文档本身保持独立，仅描述目标架构（What & Why）。本文档描述当前代码实现了什么、如何逐步收敛到设计目标、以及架构决策记录。

**最后更新**: 2026-06-20

---

## 1. 核心架构决策 (ADR)

### ADR-001: EventBus ABC 作为核心通信抽象

**设计目标**: ServiceProxy 为中心的 RPC 调用模型。
**当前实现**: EventBus ABC 为中心，InMemory/SomeIP/TCP 三种实现。
**决策**: EventBus ABC 是正确的核心抽象。pub/sub 是比 RPC 更基础的通信模式；RPC 可构建在 pub/sub 之上。ServiceProxy 作为 EventBus 上层的 RPC 层独立演进。

### ADR-002: 中间件风格拦截器先行

**设计目标**: 三方法接口 — `before_request()` / `after_response()` / `on_error()`。
**当前实现**: 单方法中间件 — `intercept(ctx, next_invoker)`。
**决策**: 中间件接口是合理的 Phase 1 简化。`try/finally` 可达 `on_error` 语义，`next_invoker` 前后的逻辑可达 `before`/`after` 语义。三方法接口作为 Phase 3 目标，提供更明确的阶段分离和类型安全。

### ADR-003: 协议无关性为一级约束

**设计目标**: SOME/IP 协议层硬编码在架构图中。
**当前实现**: EventBus ABC — 任何传输层实现 4 个方法即可接入。InMemory（`LOCAL`）、TCP（`BROKER`）、SomeIP（`PEER`）三种实现共存；`Topology` 只描述部署形态，不绑定具体协议。
**决策**: 协议无关性正确。新协议栈（如 ZeroMQ、DDS）只需实现 `publish`/`subscribe`/`unsubscribe`/`get_subscribers_count` 并声明 `topology`（DDS 归入 `PEER`，与 SOME/IP 同构）。

### ADR-004: @Service / @rpc 作为 Container 的高层封装

**设计目标**: `@Service` 装饰器声明式 API。
**当前实现**: `Container.add_service(Service(...))` 命令式 API。
**决策**: 命令式 API 是正确的底层基础。`@Service` 作为其语法糖在 Phase 2 实现——装饰器内部完成 Service 构建 + Container 注册 + 生命周期方法生成。

---

## 2. 组件实现映射

### 2.1 核心模型 (core/)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `ServiceStatus` FSM | ✅ 5 状态 + `transition()` 守卫 | 设计中还有 `DEGRADED`/`STARTING`/`STOPPING` | Phase 3 扩展 FSM（新增状态，非破坏性） |
| `Service` / `Method` / `Event` | ✅ frozen dataclass | 设计中 Service 有 `instance_id`、tags | Phase 2 添加字段 |
| `Endpoint` / `Protocol` | ✅ | 匹配 | — |
| `Message` | ✅ (core/model.py) + `EventMessage` (eventbus/message.py) | 两个 Message 类型并存 | Phase 2 统一 |

### 2.2 运行时 (runtime/)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `Container` | ✅ | 设计中的 `ServiceRegistry` 描述的是分布式注册表 | Phase 2: Container → 本地视图；SD 集成 → 分布式发现 |
| `LifecycleManager` | ✅ Hook 系统 (on_start/on_stop/on_terminate) | 设计中是 InternalEventBus 驱动 | Phase 2: 保留 Hook 机制，增加 InternalEventBus 作为通知层 |
| `DependencyResolver` | ❌ | 拓扑排序 + 依赖等待 | Phase 2 |
| `HealthChecker` | ✅ ABC + DefaultHealthChecker | 设计中有更丰富的健康探针 | Phase 2 扩展 |

### 2.3 通信 (eventbus/)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `EventBus` ABC | ✅ 4 抽象方法 + `topology` | — | — |
| `ManagedEventBus` | ✅ `async start()/stop()` | — | — |
| `EventBusBroker` ABC | ✅ `start()/stop()` | 目前只有 TCP 实现 | 后续 broker 拓扑（如 MQTT 客户端对接外部 broker）复用 |
| `BrokerEventBus` | ✅ 通用 broker 客户端，注入 `MessageStream` | — | 新 transport 只需实现 `MessageStream` |
| `InMemoryEventBus` | ✅ `topology=LOCAL` | — | — |
| `SomeIPEventBus` | ✅ `topology=PEER` + SD/eventgroup 映射 | WSL2 loopback 偶发不稳定 | CI 环境（Linux clean loopback）验证 |
| `TCPEventBus` + `TCPEventBusBroker` | ✅ `topology=BROKER`，`TCPEventBus` 是 `BrokerEventBus + TCPMessageStream` 的薄适配器 | 设计中无 TCP 设计文档 | 新增 `design/10-tcp-protocol.md` |
| `EventMessage` | ✅ | — | — |

### 2.4 拦截器 (spi/)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| 拦截器接口 | ✅ 中间件风格 (`intercept`) | 设计目标是三方法接口 | Phase 3: 新增三方法 ABC，中间件作为适配器 |
| `InterceptorChain` | ✅ priority 排序 + 递归构建 | 匹配设计 | — |
| `LoggingInterceptor` | ✅ | — | — |
| `MetricsInterceptor` | ✅ | — | — |
| `AuthInterceptor` | ✅ | — | — |
| Tracing/RateLimit/Retry/CB/Validation/Caching | ❌ | 独立模块存在但未继承 Interceptor ABC | Phase 3: 统一为 Interceptor 接口 |
| `Plugin` / `PluginManager` | ✅ | entry_points 自动发现缺失 | Phase 4 |

### 2.5 API (api/)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `ServiceRegistry` ABC | ✅ ABC 已定义 | 无网络实现 | Phase 2: SomeIPRegistry / TcpRegistry |
| `ServiceInvoker` ABC | ✅ ABC 已定义 | 无具体实现 | Phase 2: 基于 EventBus 实现 |
| `EventPublisher` / `EventSubscriber` ABC | ✅ ABC 已定义 | 无网络实现 | Phase 2 |
| `@Service` / `@rpc` 装饰器 | ❌ | — | Phase 2 |
| `ServiceProxy` | ❌ | — | Phase 2 (基于 EventBus + InterceptorChain) |
| `CallContext` / `ContextManager` | ❌ | — | Phase 2 |

### 2.6 配置 (config/)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `ConfigLoader` | ✅ 多源加载 + 合并 | 设计中的 YAML 结构不同 | Phase 2: 扩展 schema 以匹配设计结构 |
| `Config` schema | ✅ services/runtime/logging/observability | 设计中还有 network/client/interceptors/codec | Phase 2: 扩展字段 |
| `ConfigVersion` / `ConfigChange` | ❌ | — | Phase 3 |
| `CanaryConfigDeployment` | ❌ | — | Phase 3 |
| 配置热更新 | ⚠️ `reload()` 为桩代码 | — | Phase 3 |

### 2.7 可观测性 (obs/)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `MetricsCollector` | ✅ Counter/Gauge/Histogram | 无 Prometheus 导出 | Phase 3 |
| `TracingInterceptor` | ✅ Span + TracingContext | 非分布式（进程内） | Phase 3: TraceContext 注入 |
| `TraceContextHeader` (26B Payload) | ❌ | — | Phase 3 |
| SLO 定义 + 告警 | ❌ | — | Phase 3 |

### 2.8 策略 (policies/)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `RetryPolicy` | ✅ | — | Phase 2: 与 InterceptorChain 集成 |
| `TimeoutPolicy` | ✅ | — | Phase 2: 与 InterceptorChain 集成 |
| `CircuitBreaker` | ✅ | — | Phase 2: 与 InterceptorChain 集成 |
| `LoadBalancer` | ❌ | — | Phase 2 |

### 2.9 内部事件 (未实现)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `InternalEventBus` | ❌ (0%) | 完全缺失 | Phase 2: 作为 InMemoryEventBus 的子类 |
| `InternalEvent` / 12 事件类型 | ❌ | 完全缺失 | Phase 2 |
| `DependencyCoordinator` | ❌ | 完全缺失 | Phase 2 |
| `HealthMonitor` | ❌ | 当前用 LifecycleManager.check_health() 替代 | Phase 2 |

---

## 3. 收敛路线图

```
Phase 1 (v0.1 — 当前)
  ✅ EventBus ABC + 3 种实现
  ✅ Container + LifecycleManager + Hook 系统
  ✅ 中间件拦截器 (3 个内置)
  ✅ 独立的 Resilience 策略 (Retry/CB/Timeout)
  ✅ MetricsCollector + TracingInterceptor (进程内)
  ✅ ConfigLoader + Config schema
  ✅ ServiceRegistry/Invoker/Publisher/Subscriber ABC 定义

Phase 2 (v0.2 — 收敛目标)
  → InternalEventBus → 驱动生命周期、依赖、发现通知
  → @Service 装饰器 → Container 的命令式封装
  → ServiceProxy → EventBus 上的 RPC 层 (含 LB/重试)
  → SOME/IP SD 集成 → 分布式服务发现
  → Config schema 扩展 → 匹配设计 YAML 结构
  → DependencyResolver → 拓扑排序启动
  → 策略与 InterceptorChain 集成

Phase 3 (v0.3 — 生产级)
  → 三方法 Interceptor 接口 (before/after/on_error)
  → 完整 8 个内置拦截器
  → TraceContextHeader 注入 (26B Payload)
  → Prometheus / Jaeger 外部导出
  → ConfigVersion + CanaryConfigDeployment
  → SLO 监控 + 告警
  → ServiceStatus 扩展 (DEGRADED/STARTING/STOPPING)
  → ConnectionManager / 连接池

Phase 4 (v1.0 — 生态)
  → 插件自动发现 (entry_points)
  → 代码生成 CLI (tinysoa-gen)
  → TLS / 安全加固
  → 性能基准测试
```

---

## 4. 设计文档 vs 代码对照速查

| 设计文档 | 设计内容 | 主要 Gap |
|---------|---------|---------|
| [01-overview](01-overview.md) | 架构四层图、Phase 路线图、成功标准 | 架构图以 ServiceProxy 为中心；实际以 EventBus 为中心 (见 ADR-001) |
| [02-core-components](02-core-components.md) | ServiceRegistry、ConnectionManager、SD、ServiceProxy、LoadBalancer 设计 | 仅 EventBus 完全实现；ServiceProxy/LB/SD 为 Phase 2 |
| [03-api-design](03-api-design.md) | @Service 声明式 API、ServiceProxy 接口 | 当前为命令式 Container API (见 ADR-004) |
| [04-lifecycle](04-lifecycle.md) | FSM (含 DEGRADED)、InternalEventBus 驱动、DependencyResolver | 仅基础 FSM 实现 (见 §2.1); InternalEventBus 缺失 |
| [05-interceptors-plugins](05-interceptors-plugins.md) | 三方法接口、8 个内置拦截器、执行流程图 | 中间件接口先行 (见 ADR-002); 3/8 拦截器实现 |
| [06-configuration](06-configuration.md) | 配置结构、版本管理、灰度部署、原子性边界 | ConfigLoader 实现基础加载；版本/灰度未实现 |
| [07-monitoring-tracing](07-monitoring-tracing.md) | TraceContextHeader、SLO 拓扑分类、Prometheus 告警 | 进程内指标+追踪；分布式追踪缺失 |
| [08-best-practices](08-best-practices.md) | 项目结构、开发流程、代码示例 | 示例 API (@Service/@rpc/Proxy) 为设计目标而非当前可用 |
| [09-internal-event-model](09-internal-event-model.md) | InternalEventBus、12 事件类型、事件驱动模式 | 0% 实现 — Phase 2 最大优先级 |
| [testing-framework](../TESTING.md) | 测试分层、pytest 配置、CI 形状 | 已移出 design/；131 tests 可运行 |
