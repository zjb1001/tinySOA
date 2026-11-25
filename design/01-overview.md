# tinySOA 框架整体设计

## 1. 项目概述

### 1.1 项目背景
tinySOA 是一个协议无关的轻量级面向服务架构（SOA）框架：以 Service 模型和运行时治理为中心，通过可插拔 EventBus 接入 InMemory / TCP / SOME/IP 等传输。SOME/IP（pysomeip）是当前首个车载协议栈实现，但不是框架的唯一协议。框架的目标是简化分布式服务的开发和部署，并在服务生命周期、依赖、发现、健康等治理维度提供统一抽象。

### 1.2 设计目标
- **简单易用**: 提供直观的 API，降低 SOA 开发门槛
- **轻量高效**: 最小化资源占用，适合嵌入式和资源受限环境
- **可扩展性**: 支持灵活的服务扩展和自定义
- **可靠性**: 内置服务发现、健康检查、故障恢复机制
- **异步优先**: 基于 asyncio 的异步编程模型

### 1.3 核心特性
- 声明式服务定义
- 自动服务发现与注册
- 简化的 RPC 调用接口
- 事件驱动的发布/订阅模式
- 服务生命周期管理
- 控制面事件与运行期依赖协调
- 配置管理与热更新
- 服务监控与追踪
- 插件化架构

## 2. 架构设计

### 2.1 分层架构

```
┌─────────────────────────────────────────────────┐
│          Application Layer (应用层)              │
│   (Business Services, Service Consumers)        │
└─────────────────────────────────────────────────┘
                      ▲
                      │
┌─────────────────────────────────────────────────┐
│         tinySOA Framework Layer                 │
├─────────────────────────────────────────────────┤
│  Service Registry  │  Service Proxy             │
│  Event Bus         │  Lifecycle Manager         │
│  Service Discovery │  Configuration Manager     │
│  Interceptor Chain │  Monitoring & Metrics      │
└─────────────────────────────────────────────────┘
                      ▲
                      │
┌─────────────────────────────────────────────────┐
│      SOME/IP Protocol Layer (协议层)             │
├─────────────────────────────────────────────────┤
│  SimpleService    │  ServiceDiscoveryProtocol   │
│  SimpleEventgroup │  SOMEIPHeader               │
│  Session Storage  │  Message Parsing            │
└─────────────────────────────────────────────────┘
                      ▲
                      │
┌─────────────────────────────────────────────────┐
│       Transport Layer (传输层)                   │
│         (UDP/TCP, Asyncio)                      │
└─────────────────────────────────────────────────┘
```

> 图中 SOME/IP 是当前首个协议栈实现；EventBus ABC 同时支持 InMemory / TCP，
> 协议无关性是 ADR-003 的一级约束。控制面治理不在该数据面栈内，见 2.3。

### 2.2 核心模块

#### 2.2.1 Service Registry (服务注册中心)
- 本地服务注册表
- 服务元数据管理
- 服务实例管理
- 服务状态跟踪

#### 2.2.2 Service Discovery (服务发现)
- 基于 SD 协议的自动发现
- 服务订阅与通知
- 心跳检测
- 服务可用性管理

#### 2.2.3 Service Proxy (服务代理)
- 远程服务调用封装
- 自动序列化/反序列化
- 负载均衡
- 故障转移

#### 2.2.4 Event Bus (数据面事件总线)
- 发布/订阅模式
- 事件路由
- 事件过滤
- 事件持久化（按部署方式可选）

> 这是**业务数据面**：topic / payload 属于应用。运行时治理状态不走这里，
> 见 2.2.9 控制面治理与
> [控制面与框架治理模型](10-control-plane-governance.md)。

#### 2.2.5 Lifecycle Manager (生命周期管理器)
- 服务启动/停止
- 优雅关闭
- 资源清理
- 依赖管理

#### 2.2.6 Configuration Manager (配置管理器)
- 配置加载与解析
- 配置验证
- 动态配置更新
- 环境变量支持

#### 2.2.7 Interceptor Chain (拦截器链)
- 请求/响应拦截
- 日志记录
- 认证授权
- 限流熔断

#### 2.2.8 Monitoring & Metrics (监控与度量)
- 服务调用统计
- 性能指标收集
- 健康检查
- 告警机制

#### 2.2.9 Control Plane (控制面治理)
- 强类型内部事件契约（生命周期 / 依赖 / 发现 / 健康 / 配置）
- 服务状态事实的进程内发布与订阅
- 依赖协调策略（必需/可选、快照 + 事件、超时）
- 与数据面 EventBus 的所有权隔离

详见 [控制面与框架治理模型](10-control-plane-governance.md)。

### 2.3 数据面与控制面

tinySOA 的框架定义不是“消息通道提供者”，而是“服务状态的所有者”：

```text
业务数据面：
  Service A ──EventBus(topic, payload)──> Service B

治理控制面：
  LifecycleManager ──SERVICE_READY──┐
  SD Adapter ───────INSTANCE_*──────┼──> InternalEventDispatcher
  HealthChecker ────SERVICE_*───────┘          │
                                              ├──> DependencyCoordinator
                                              ├──> Audit / Metrics
                                              └──> HealthMonitor
```

- **数据面**：应用定义 topic 和 payload，可跨进程，需要序列化。
- **控制面**：框架定义事件词汇，仅进程内，不序列化，at-most-once。
- **治理 = 事实 + 决策 + 机制**：事件是事实，Coordinator/Monitor 是决策，
  Dispatcher 是机制。

`InternalEventType` 的取值就是框架对“哪些治理状态负责”的能力声明。
因此事件契约是架构，分发器只是实现。

## 3. 关键设计决策

### 3.1 编程模型
- **异步优先**: 使用 asyncio 作为核心异步运行时
- **装饰器风格**: 使用装饰器简化服务和方法的声明
- **类型注解**: 充分利用 Python 类型注解进行参数验证和文档生成

### 3.2 通信模式
- **Request/Response**: 同步请求-响应模式
- **Request/No-Response**: 异步请求模式
- **Publish/Subscribe**: 事件发布-订阅模式
- **Fire and Forget**: 单向通知模式

### 3.3 序列化方案
- 支持多种序列化格式（JSON, MessagePack, Protobuf）
- 可插拔的序列化器
- 自动类型转换

### 3.4 容错机制
- 自动重试
- 超时控制
- 熔断器模式
- 降级策略

### 3.5 数据面与控制面分离
- 业务事件走 `EventBus`（应用定义 topic / payload）
- 治理状态走 `InternalEventDispatcher`（框架定义事件词汇）
- 事件契约是框架的治理 API；分发器是具体实现，不引入第二个 ABC
- 发布者不知道订阅者；新增治理能力通过订阅接入
- 详见 [10-control-plane-governance.md](10-control-plane-governance.md)

## 4. 技术栈

### 4.1 核心依赖
- Python 3.8+
- asyncio (异步 I/O)
- pysomeip (SOME/IP 协议)

### 4.2 可选依赖
- pydantic (数据验证)
- msgpack (序列化)
- prometheus-client (监控)
- PyYAML (配置管理)

## 5. 开发路线图（MVP-驱动）

### Phase 1: 最小可用产品 MVP (v0.1 - 单机基础)
**目标**: 10行代码内实现一个可运行的服务  
**可交付物**: 可部署、可测试的独立服务

- [ ] 声明式服务定义 (@Service 装饰器)
- [ ] 本地服务注册表 (LocalRegistry - 内存存储)
- [ ] 基础RPC调用框架 (SimpleProxy - 单实例)
- [ ] 简单拦截器链基础设施
- [ ] 本地日志和基础指标
- [ ] 配置管理 (YAML/环境变量)

**交付标准**: 两个服务在同一进程通信成功

---

### Phase 2: 分布式发现与扩展 (v0.2 - 多进程)
**目标**: 支持多进程服务间通信，自动发现  
**可交付物**: 可在局域网内扩展的服务网格

- [ ] SOME/IP-SD 集成 (OfferService/FindService/Subscribe)
- [ ] 远程服务发现与缓存 (TTL管理)
- [ ] 多实例支持与负载均衡 (RoundRobin/Random/LatencyWeighted)
- [ ] 实例健康度评分与自适应选择
- [ ] 故障转移与自动重试
- [ ] 内部事件体系与治理契约 (ServiceDiscovered/ServiceLost/HealthChanged) — 见 [10-control-plane-governance.md](10-control-plane-governance.md)
- [ ] 配置版本控制与原子化更新

**交付标准**: 3个不同进程的服务互相调用成功，支持实例上下线

---

### Phase 3: 生产级特性 (v0.3 - 可观测性)
**目标**: 企业级可运维性、可观测性  
**可交付物**: 可在生产环境运行的完整服务框架

- [ ] 完整的拦截器链 (Retry/RateLimit/Auth/Validation/CircuitBreaker)
- [ ] Prometheus 指标导出与 SLO 监控
- [ ] 分布式追踪 (Trace Context 嵌入、OpenTelemetry 集成)
- [ ] 结构化日志与聚合
- [ ] 优雅启停与依赖管理
- [ ] 事件总线与事件组 (SOME/IP eventgroup 完整支持)
- [ ] 高级LB策略与一致性哈希

**交付标准**: 完整的链路追踪、实时监控、快速故障诊断

---

### Phase 4: 生态完善 (v1.0 - 工程效能)
**目标**: 完整的开发工具链和最佳实践  
**可交付物**: 企业级框架成熟度

- [ ] 插件系统与热加载
- [ ] 代码生成工具 (CLI: tinysoa-gen)
- [ ] 开发者文档与最佳实践指南
- [ ] 示例项目库与参考实现
- [ ] 性能优化与基准测试
- [ ] 安全加固 (TLS/认证/审计)

**交付标准**: 开箱即用、文档完整、工具链完善

## 6. 成功标准（分阶段）

### Phase 1 成功标准
- ✅ 10行代码内实现基本服务
- ✅ 清晰的错误提示和异常处理
- ✅ 完善的快速开始文档
- ✅ 本地单机 RPC 延迟 < 5ms
- ✅ 资源占用 < 50MB

### Phase 2 成功标准
- ✅ 网络RPC调用延迟 < 20ms (局域网)
- ✅ 支持 100+ 实例自动发现
- ✅ 99.5% 消息投递成功率 (局域网UDP)
- ✅ 故障转移时间 < 1秒
- ✅ 配置变更不中断服务 (热更新)

### Phase 3 成功标准
- ✅ P95 延迟 ≤ 25ms (含拦截器链)
- ✅ 99.9% 成功率 (含自动重试)
- ✅ 链路追踪覆盖率 ≥ 95%
- ✅ 故障自动诊断与上报
- ✅ 关键路径无内存泄漏

### Phase 4 成功标准
- ✅ 与现有运维工具链集成 (Prometheus/Jaeger/ELK)
- ✅ 性能对标业界水准 (对比 gRPC)
- ✅ 100% API 向后兼容性

## 7. 风险与挑战

### 7.1 技术风险
- **SOME/IP 协议复杂性**: 固定头格式导致追踪上下文传递困难
  - 应对: 通过payload首部可选扩展区实现追踪注入
  
- **设计-实现脱节**: 企业级设计需要完整实现
  - 应对: MVP驱动，每阶段必须可交付
  
- **异步编程学习曲线**: Python asyncio的正确性要求高
  - 应对: 提供完善的示例代码和最佳实践文档
  
- **分布式一致性**: SD协议的最终一致性可能导致视图不一致
  - 应对: 明确定义一致性边界和容错策略

### 7.2 应对策略
- 提供完善的示例代码与详细的最佳实践文档
- 建立明确的一致性模型与边界
- 阶段式交付，每个阶段必须可测试和部署
- 提供可视化工具辅助诊断分布式问题
- 持续性能测试和优化
- 活跃的社区支持

## 8. 下一步

参考以下详细设计文档：
- [核心组件设计](02-core-components.md)
- [API 设计](03-api-design.md)
- [生命周期管理](04-lifecycle.md)
- [拦截器与插件](05-interceptors-plugins.md)
- [配置管理](06-configuration.md)
- [监控与追踪](07-monitoring-tracing.md)
- [最佳实践](08-best-practices.md)
- [内部事件模型](09-internal-event-model.md)
- [控制面与框架治理模型](10-control-plane-governance.md)

> 实现状态与设计-代码差距分析见 **[implementation-gap.md](implementation-gap.md)**。
