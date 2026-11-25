# 控制面与框架治理模型

> 本文定义 tinySOA 作为“服务运行时”的治理边界：数据面负责业务消息，控制面负责运行时状态；
> **控制面事件契约是框架的治理 API**。
>
> **实现状态 (2026-11-25)**: 事件契约、`InternalEventDispatcher`、
> `DependencyCoordinator` 与生命周期异步发布已落地；SD / 健康 / 配置发布者待接入。
> 可运行案例：[local_dependency_events](../examples/local_dependency_events/README.md)。

## 1. 为什么需要这一层

### 1.1 通信库 vs 服务运行时

如果框架只有 EventBus + RPC，它本质上是一个通信库：应用决定发什么、发给谁，框架只负责搬运。
一旦引入治理需求——生命周期、依赖、发现、健康、降级、配置、审计——框架的所有权就变了：

| 治理问题 | 通信库的回答 | 服务运行时的回答 |
|---|---|---|
| 服务何时可被调用？ | 应用自己保证 | 框架保证：依赖满足后才 `READY` |
| 依赖掉线怎么办？ | 应用自己处理 | 发布 `DEPENDENCY_LOST`，由策略决定降级/重连 |
| 远程实例何时可用？ | 应用自己发现 | SD 发布 `INSTANCE_DISCOVERED` |
| 服务不健康怎么办？ | 应用自己判断 | 健康检查发布 `SERVICE_UNHEALTHY` |
| 新治理需求怎么接？ | 改核心代码 | 订阅事件，不改发布方 |

因此治理需求对框架定义的影响是：

> **框架从“消息通道提供者”变成“服务状态的所有者”。**

控制面事件就是框架对外暴露“状态所有权”的方式。

### 1.2 治理需求带来的四项约束

1. **所有权边界**：框架拥有服务状态、依赖、发现、健康；应用拥有业务逻辑和业务数据。
2. **契约边界**：`Service` / `ServiceDependency` 声明“是什么”，控制面事件词汇表声明“框架承诺观察什么”。
3. **扩展模型**：新增治理能力通过订阅接入，而不是修改生命周期/发现/配置的发布方。
4. **保证语义**：`READY`、`DEGRADED`、`DEPENDENCY_LOST` 等状态必须有时序、超时和幂等语义。

## 2. 数据面 vs 控制面

| 维度 | 数据面（业务） | 控制面（治理） |
|---|---|---|
| 实现 | `EventBus` ABC + InMemory / TCP / SOME/IP | 具体 `InternalEventDispatcher` |
| 消息 | `EventMessage(topic, payload)` | `InternalEvent(event_type, details)` |
| 订阅键 | 业务 topic 字符串 | `InternalEventType` 枚举 |
| 范围 | 进程内或跨进程 | 仅进程内 |
| 编码 | 需要序列化 | 不需要序列化 |
| 语义 | 业务 pub/sub | 状态事实，at-most-once |
| 词汇表所有者 | 应用 | 框架 |
| 生命周期 | 可能有 `start/stop` | 无传输资源、无 `start/stop` |

### 2.1 边界规则

- 控制面事件**不承载业务 payload**；一旦承载，它就会变成第二个数据面。
- 业务事件**不用于治理状态**；业务 topic 的生命周期由应用负责。
- 两者不能共用同一个抽象：它们的**所有权不同**，词汇表也不同。

## 3. 事实、决策、机制

控制面层把治理拆成三个独立概念：

```text
事实（Fact）              决策（Policy）                机制（Mechanism）
SERVICE_READY       →    DependencyCoordinator     →   InternalEventDispatcher
DEPENDENCY_LOST     →    HealthMonitor             →   订阅 / 分发 / 历史
INSTANCE_LOST       →    DegradedMode / 重启策略
```

- **事实**：`InternalEventType` + `InternalEvent`，回答“发生了什么”，不回答“该怎么办”。
- **决策**：`DependencyCoordinator`、`HealthMonitor`、`DegradedMode`，订阅事实并做出治理决策。
- **机制**：`InternalEventDispatcher`，只负责把事实送到订阅者，不承载策略。

三者混在一起，框架就会退化成硬编码的 `if`；分开之后，治理才可组合。

### 3.1 事实不是命令

- “启动服务 X”是**命令**：有唯一拥有者、可能失败、需要确认。
- “服务 X 已就绪”是**事实**：可以广播、可以重复、可能错过，订阅者必须幂等。

`DependencyCoordinator` 的“先订阅、后快照”正是为此：

```text
1. 订阅 DEPENDENCY_SATISFIED / INSTANCE_DISCOVERED
2. 读取本地 Container 中已 RUNNING 的必需依赖（快照）
3. 等待 remaining 为空或超时
```

事件不保证订阅前发生的事情，所以必须用状态快照补齐。
把事实当命令用，就会写出“订阅前错过事件 → 永远等不到”的 bug。

## 4. 事件词汇表就是能力边界

`InternalEventType` 里有哪些值，框架就“承认”哪些治理状态：

| 事件类型 | 框架承诺观察/暴露的治理事实 |
|---|---|
| `SERVICE_READY` | 服务已可接受流量 |
| `SERVICE_STOPPED` | 服务已释放资源 |
| `DEPENDENCY_SATISFIED` | 某个依赖已满足 |
| `DEPENDENCY_LOST` | 某个依赖已失效 |
| `INSTANCE_DISCOVERED` | 远程实例可见 |
| `INSTANCE_LOST` | 远程实例不可见 |
| `SERVICE_DEGRADED` | 核心可用、部分能力降级 |
| `SERVICE_UNHEALTHY` | 服务异常 |
| `CONFIG_CHANGED` | 配置已变更 |

其中 `SERVICE_DEGRADED` / `SERVICE_UNHEALTHY` / `CONFIG_CHANGED` 目前已有契约，
发布者待接入。

新增一个事件类型，意味着框架要对该状态的语义、时序和幂等性负责；
删除一个事件类型，意味着框架无法再治理该关注点。

因此：

> **事件契约是架构，分发器只是实现。**

## 5. 所有权与扩展模型

### 5.1 没有控制面事件

所有治理都靠直接调用时，SD 发现远程服务后必须知道谁关心：

```text
SD Adapter → Dashboard
           → Analytics
           → Audit
           → HealthMonitor
           → ...
```

每新增一个治理关注点，都要改 SD Adapter；每新增一个服务依赖，都要改生命周期。
耦合矩阵是 **O(N×M)**。

### 5.2 有控制面事件

```text
SD Adapter → publish(INSTANCE_DISCOVERED)
                 ├── Dashboard 的 DependencyCoordinator
                 ├── Analytics 的 DependencyCoordinator
                 ├── Audit subscriber
                 └── HealthMonitor
```

SD Adapter **不知道任何订阅者**。新增订阅者是加法，不是修改。
这是架构层面的开闭原则：**对扩展开放，对修改关闭**。

`local_dependency_events` 案例是最小证明：

- 远程服务发现逻辑只发布 `INSTANCE_DISCOVERED`；
- 它不知道 `DashboardService` 存在；
- 如果未来新增一个也依赖 telemetry 的服务，发现逻辑一行都不用改。

## 6. 实现映射

| 关注点 | 当前实现 | 职责 |
|---|---|---|
| 依赖声明 | `Service.dependencies` / `ServiceDependency` | 声明“需要谁、是否必需、超时” |
| 状态机 | `LifecycleManager` | `INIT → REGISTERED → RUNNING → STOPPED → TERMINATED` |
| 事件发布 | `LifecycleManager.astart_service` / `astop_all` 等 | 状态转移后发布事实 |
| 事件契约 | `InternalEvent` / `InternalEventType` | 强类型、不可变、进程内 |
| 投递机制 | `InternalEventDispatcher` | 订阅、有序分发、异常隔离、有界历史 |
| 依赖策略 | `DependencyCoordinator` | 必需/可选、快照 + 事件、超时 |
| 远程发现 | SOME/IP SD 适配器（待接入） | 发布 `INSTANCE_DISCOVERED` / `INSTANCE_LOST` |

同步的 `start_all()` 保持原语义且不发布事件；需要控制面事实时使用 `astart_all()`。
这是刻意的：**事件发布是异步路径的职责**，不在同步状态机里做 fire-and-forget。

## 7. 非目标与适用边界

控制面事件**不是**：

- 消息队列；
- 跨进程控制面；
- 业务数据通道；
- 事件溯源/持久化存储。

当框架只有 1–2 个固定订阅者、没有运行期反应、也不需要诊断时间线时，
直接回调或 `asyncio.Event` 更简单。引入控制面事件层的触发点：

1. 第三个独立订阅者出现（审计、指标、健康、SD、配置……）；
2. 需要运行期反应（依赖掉线、实例丢失、健康变化）；
3. 需要框架保持可扩展（加治理能力不改核心）；
4. 需要一条可观测的状态时间线（排障、审计、SLO）。

## 8. 设计约束清单

- 事件对象不可变，`details` 只读；
- 发布者不知道订阅者，订阅者不知道发布者；
- 订阅者必须幂等，重要等待必须“事件 + 快照”；
- 分发器不承载治理策略；
- 控制面事件不承载业务 payload；
- 不做序列化、网络、持久化、重试；
- 单一实现不引入 ABC（见 ADR-005）；
- 事件枚举的任何扩展都视为框架治理能力的扩展，需要设计评审。
