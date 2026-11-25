# Implementation Gap Analysis

> 设计→实现映射的唯一信息源。设计文档本身保持独立，仅描述目标架构（What & Why）。本文档描述当前代码实现了什么、如何逐步收敛到设计目标、以及架构决策记录。

**最后更新**: 2026-11-25

## 0. 近期进展 (2026-11)

- **总线拥有注册生命周期**：`bus.register/unregister` 成为唯一控制面动作，
  `TopicPublisher` / `TopicSubscriber` 退化为携带 topic/handler 的句柄
  （未注册调用 `publish()` 抛 `StateError`）。
- **SOME/IP 应用门面**：`SomeIPService` 让 event / method 共享同一个
  `SomeIPEndpoint` 与服务实例（Phase 3.5）。
- **依赖管理落地（Phase 2）**：`Service.dependencies` + `DependencyResolver`
  （拓扑排序 / 分层 / 环检测 / strict 缺失依赖校验）+
  `LifecycleManager` 按依赖顺序启停。
- **客户端代理落地（Phase 2）**：`ServiceProxy` 组合 `ServiceInvoker` +
  `InterceptorChain` + Retry/Timeout/CircuitBreaker，统一客户端调用语义。
- **控制面事件落地**：强类型 `InternalEvent` / `InternalEventType` + 具体
  `InternalEventDispatcher`（无 ABC、无序列化）+ `DependencyCoordinator`
  快照/事件/超时等待；`LifecycleManager` 新增 `a*` 异步方法发布
  READY / STOPPED / DEPENDENCY_* 事件。
- **治理模型文档化**：新增
  [10-control-plane-governance.md](10-control-plane-governance.md)，明确
  数据面/控制面、事实/命令、事件词汇即能力边界（见 ADR-006）。
- **公共包门面修复**：`tinysoa.runtime` / `tinysoa.api` / `tinysoa.core` 可直接
  导入文档中的名字；`tinysoa.spi` / `tinysoa.obs` 改用惰性导出避免循环导入。

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

### ADR-005: 控制面事件用具体分发器，不引入第二个 EventBus ABC

**设计目标**: `InternalEventBus` 作为框架内部事件总线。
**当前实现**: `InternalEvent` / `InternalEventType` 强类型契约 + 具体
`InternalEventDispatcher`；无 ABC、无 `start/stop`、无序列化、无多传输实现。
**决策**: 内部事件只有“进程内”一种传输，没有第二个实现，ABC 只会复制业务
`EventBus` 的问题。共享内存消除了传输抽象，但不消除发布/订阅的解耦需求。
**影响**: 后续 SD / 健康检查 / 配置订阅方直接 `subscribe`；若未来真的需要跨进程
控制面事件，再引入接口。

### ADR-006: 控制面事件契约是框架的治理 API

**背景**: 生命周期、依赖、发现、健康、配置、审计等治理需求需要一个统一的状态通知面。
**决策**: 明确区分数据面 `EventBus` 与控制面 `InternalEventDispatcher`；
`InternalEventType` 是框架对治理能力的声明，只承载状态事实，不承载业务 payload；
分发器是具体机制，不引入 ABC（ADR-005）。
**理由**: 共享内存消除了传输抽象，但不消除知识边界；治理要求发布者不知道订阅者、
订阅者不知道发布者。没有控制面契约，框架只是通信库；有了它，框架才拥有服务状态。
**影响**: 新治理能力通过订阅接入；事件枚举扩展需设计评审；SD / 健康 / 配置发布者
逐步接入。

---

## 2. 组件实现映射

### 2.1 核心模型 (core/)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `ServiceStatus` FSM | ✅ 5 状态 + `transition()` 守卫 | 设计中还有 `DEGRADED`/`STARTING`/`STOPPING` | Phase 3 扩展 FSM（新增状态，非破坏性） |
| `Service` / `Method` / `Event` | ✅ dataclass；`Service` 已含 `dependencies` | 设计中 Service 还有 `instance_id`、tags | Phase 2 添加字段 |
| `Endpoint` / `Protocol` | ✅ | 匹配 | — |
| `Message` | ✅ (core/model.py) + `EventMessage` (eventbus/message.py) | 两个 Message 类型并存 | Phase 2 统一 |

### 2.2 运行时 (runtime/)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `Container` | ✅ | 设计中的 `ServiceRegistry` 描述的是分布式注册表 | Phase 2: Container → 本地视图；SD 集成 → 分布式发现 |
| `LifecycleManager` | ✅ Hook 系统 + 依赖感知启停 (`start_all` / `stop_all` / `terminate_all`) | 设计中是 InternalEventBus 驱动 | Phase 2: 保留 Hook 机制，增加 InternalEventBus 作为通知层 |
| `DependencyResolver` | ✅ `startup_order` / `startup_layers` / `shutdown_order` + 环检测 + strict 缺失依赖校验 | 远程依赖等待（SD 事件驱动）未接入 | Phase 3 |
| `HealthChecker` | ✅ ABC + DefaultHealthChecker | 设计中有更丰富的健康探针 | Phase 2 扩展 |

### 2.3 通信 (eventbus/)

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `EventBus` ABC | ✅ 4 抽象方法 + `topology` | — | — |
| `ManagedEventBus` | ✅ `async start()/stop()` | — | — |
| `TopicPublisher` / `TopicSubscriber` | ✅ 应用层门面，封装 topic / `EventMessage` | TCP/SOME-IP 共用 | — |
| `SomeIPService` | ✅ 应用层门面：publisher/subscriber/method/invoke，共享一个 endpoint | field 待接入 | Phase 4 |
| `EventBusBroker` ABC | ✅ `start()/stop()` | 目前只有 TCP 实现 | 后续 broker 拓扑（如 MQTT 客户端对接外部 broker）复用 |
| `BrokerEventBus` | ✅ 通用 broker 客户端，注入 `MessageStream` | — | 新 transport 只需实现 `MessageStream` |
| `InMemoryEventBus` | ✅ `topology=LOCAL` | — | — |
| `SomeIPEndpoint` | ✅ 共享 SD/transport/service instance，供 event/method/field 复用 | field 尚未接入 | Phase 4 接入 `SomeIPField` |
| `SomeIPServiceInstance` | ✅ 一个 `(service_id, instance_id)` 对应一个 `SimpleService`；eventgroup + method 共享端点/Offer | — | — |
| `SomeIPEventBus` | ✅ `topology=PEER` + SD/eventgroup 映射；委托 `SomeIPEndpoint` | WSL2 loopback 偶发不稳定 | CI 环境（Linux clean loopback）验证 |
| `SomeIPMethodInvoker` | ✅ `ServiceInvoker` 实现：SD 发现 + REQUEST/RESPONSE + JSON | 无 field/E2E/TP | Phase 4+ 扩展 |
| `SomeIPMethodDispatcher` | ✅ server-side method 注册 + RESPONSE/ERROR；复用 `SomeIPServiceInstance` | field 尚未接入 | Phase 4 字段门面 |
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
| `ServiceInvoker` ABC | ✅ ABC + `SomeIPMethodInvoker` | 仅 SOME/IP 实现 | Phase 2: 本地/EventBus 实现 |
| `EventPublisher` / `EventSubscriber` ABC | ✅ ABC 已定义 | 无网络实现 | Phase 2 |
| `@Service` / `@rpc` 装饰器 | ❌ | — | Phase 2 |
| `ServiceProxy` | ✅ 组合 `ServiceInvoker` + `InterceptorChain` + Retry/Timeout/CircuitBreaker | 无负载均衡/多实例故障转移 | Phase 3 |
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

### 2.9 内部事件

| 设计组件 | 实现状态 | 差距 | 收敛路径 |
|---------|---------|------|---------|
| `InternalEvent` / 12 事件类型 | ✅ 强类型、不可变契约 | 部分类型尚无发布者 | 后续按 SD / 健康 / 配置接入 |
| `InternalEventDispatcher` | ✅ 具体进程内分发器：有序分发、异常隔离、有界历史；无 ABC / 无序列化 / 无 start-stop | — | 见 ADR-005 |
| `InternalEventBus` ABC | — (不做) | 内部事件只有内存一种实现，ABC 无第二个实现 | 需要跨进程控制面时再引入接口 |
| `DependencyCoordinator` | ✅ 订阅先行 + 本地快照 + `timeout_s` 超时 | 运行期掉线监控未实现 | Phase 3: 长驻 HealthMonitor |
| `HealthMonitor` | ❌ | 当前用 LifecycleManager.check_health() 替代 | Phase 3 |

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
  ✅ InternalEventDispatcher → 驱动生命周期与依赖通知 (2026-11)
  → @Service 装饰器 → Container 的命令式封装
  ✅ ServiceProxy → 基于 ServiceInvoker + 拦截器 + 重试/超时/熔断 (2026-11)
  → SOME/IP SD 集成 → 分布式服务发现
  → Config schema 扩展 → 匹配设计 YAML 结构
  ✅ DependencyResolver → 拓扑排序 + 分层 + 环检测 (2026-11)
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
| [03-api-design](03-api-design.md) | @Service 声明式 API、ServiceProxy 接口 | ServiceProxy 已实现；@Service 声明式 API 未实现，当前为命令式 Container API (见 ADR-004) |
| [04-lifecycle](04-lifecycle.md) | FSM (含 DEGRADED)、InternalEventBus 驱动、DependencyResolver | 基础 FSM + DependencyResolver 已实现；InternalEventBus 缺失 |
| [05-interceptors-plugins](05-interceptors-plugins.md) | 三方法接口、8 个内置拦截器、执行流程图 | 中间件接口先行 (见 ADR-002); 3/8 拦截器实现 |
| [06-configuration](06-configuration.md) | 配置结构、版本管理、灰度部署、原子性边界 | ConfigLoader 实现基础加载；版本/灰度未实现 |
| [07-monitoring-tracing](07-monitoring-tracing.md) | TraceContextHeader、SLO 拓扑分类、Prometheus 告警 | 进程内指标+追踪；分布式追踪缺失 |
| [08-best-practices](08-best-practices.md) | 项目结构、开发流程、代码示例 | 示例 API (@Service/@rpc/Proxy) 为设计目标而非当前可用 |
| [09-internal-event-model](09-internal-event-model.md) | InternalEventBus、12 事件类型、事件驱动模式 | 契约 + 具体分发器 + Lifecycle/Dependency 接入已实现；SD/健康/配置发布者未接入；不引入 ABC (ADR-005) |
| [10-control-plane-governance](10-control-plane-governance.md) | 数据面/控制面、事实/命令、治理边界 | 已文档化；SD/健康/配置发布者待接入 |
| [testing-framework](../TESTING.md) | 测试分层、pytest 配置、CI 形状 | 已移出 design/；131 tests 可运行 |
