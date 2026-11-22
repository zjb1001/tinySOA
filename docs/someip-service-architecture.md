# SOME/IP 服务架构

目标：**应用只写业务名（topic / method / field），SOME/IP 的 ID、编解码、发现、E2E、TP 全部由框架和协议栈处理。**

## 当前状态

已落地 Phase 1（事件子集）：

- `EventBusConfig` / `TopicBinding` / `create_event_bus`
- 应用不再直接 import `SomeIPTopicMapping`
- `SomeIPEventBus` 仍只覆盖 event/notification

已落地 Phase 2（共享端点）：

- `SomeIPEndpoint` 统一持有 SD、transports、publisher 缓存和 subscriber；
- `SomeIPEventBus` 只保留 topic 解析、订阅表和序列化，SD/transport 全部委托给 endpoint；
- 后续 method/field adapter 可以复用同一个 `SomeIPEndpoint`。

已落地 Phase 3（方法调用）：

- `SomeIPServiceBinding`：逻辑服务名 / method 名 → SOME/IP ID；
- `SomeIPMethodInvoker`：实现 `ServiceInvoker`，负责 SD 发现、REQUEST/RESPONSE、
  session 匹配、JSON 编解码和超时；
- `SomeIPMethodDispatcher`：服务端注册 async handler，自动处理 RESPONSE/ERROR；
- Calculator 示例已切到框架 API。

已落地 Phase 3.5（统一服务实例）：

- `SomeIPServiceInstance`：一个 `(service_id, instance_id)` 对应一个
  pysomeip `SimpleService`；
- eventgroup 和 method 注册在同一个实例上，共享一个 unicast endpoint 和一个
  SD Offer；
- `SomeIPEndpoint.get_or_create_service_instance()` 负责缓存；
- `SomeIPEventBus` / `SomeIPMethodDispatcher` / `SomeIPMethodInvoker`
  都支持注入同一个 `SomeIPEndpoint`。

field、E2E、TP 是后续阶段，本文档描述目标架构。

## 1. 应用侧

推荐使用应用层门面：

```python
from tinysoa.eventbus import SomeIPService

service = SomeIPService(binding, event_mappings=EVENT_MAPPINGS)
publisher = service.publisher("sensor.temperature")
subscriber = service.subscriber("sensor.temperature")

await service.start()
await publisher.publish({"value": 21.5})
# subscriber.on(handler) 注册事件处理
await service.stop()
```

通用总线也提供 topic 门面：

```python
publisher = bus.publisher("sensor.temperature")
subscriber = bus.subscriber("sensor.temperature")
await publisher.publish({"value": 21.5})
```

低层 `bus.publish(EventMessage(...))` 保留给框架内部、测试和高级用法。
应用不需要知道 `service_id`、`instance_id`、`eventgroup_id`、端口或传输类型。

## 2. 绑定/配置层

### EventBusConfig / TopicBinding

```python
from tinysoa.config import EventBusConfig, EventBusKind, TopicBinding

config = EventBusConfig(
    kind=EventBusKind.SOMEIP,
    service="temperature",
    bindings=(
        TopicBinding(
            "sensor.temperature",
            {
                "service_id": 0x1001,
                "instance_id": 0x0001,
                "eventgroup_id": 0x0001,
                "event_id": 0x0001,
                "major_version": 1,
            },
        ),
    ),
    options={
        "local_ip": "127.0.0.1",
        "publisher_port": 30500,
        "is_publisher": True,
    },
)
```

- `kind` 决定工厂创建哪种总线：`inmemory` / `tcp` / `someip`。
- `bindings` 只描述 topic 到协议身份的映射。
- `options` 描述本进程的端点参数（本地 IP、端口、publisher/subscriber 角色）。
- 工厂会校验重复 topic、缺失 ID、ID 范围、L4 协议。

### YAML（目标形态）

```yaml
someip:
  local_ip: 127.0.0.1
  services:
    temperature:
      service_id: 0x1001
      instance_id: 0x0001
      major: 1
      minor: 0
      eventgroups:
        measurements:
          id: 1
          events:
            reading:
              id: 1
              topic: sensor.temperature
              codec: json
```

YAML loader 负责把上述结构转换成 `EventBusConfig`。

## 3. 目标分层

```text
应用层
  topic / method / field 名称
        │
        ▼
绑定/配置层
  EventBusConfig / TopicBinding / SomeIPServiceConfig
        │
        ▼
SOME/IP 运行时
  SomeIPEndpoint (共享 SD + transport)
    ├─ SomeIPEventBus       事件
    ├─ SomeIPMethodInvoker  方法（ServiceInvoker）
    ├─ SomeIPField          getter/setter/notifier 组合
    ├─ Codec                序列化
    ├─ E2E                  端到端保护
    └─ TP                   分段/重组
```

### 共享 SomeIPEndpoint

完整服务必须让 event / method / field 共享一个 SOME/IP participant：

- 一份 SD Offer/Find；
- 一套 unicast 端点；
- 一套生命周期；
- 避免多 adapter 各自绑定端口、重复 Offer。

```python
class SomeIPEndpoint(ManagedResource):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def send_request(self, binding, payload, timeout) -> Awaitable[bytes]: ...
```

### 方法

- `SomeIPMethodInvoker` 实现现有 `ServiceInvoker` ABC；
- pysomeip 已提供 `register_method` / REQUEST-RESPONSE；
- 服务端用 `SomeIPMethodDispatcher` 把 method_id 映射到业务 handler。

### 字段

SOME/IP field = getter method + setter method + notifier event：

```python
class SomeIPField:
    async def get(self) -> Any: ...
    async def set(self, value: Any) -> None: ...
    def subscribe(self, handler) -> Subscription: ...
```

不要为 field 增加新的 `EventBus` 方法或线缆类型。

### Codec / E2E / TP

```text
发送：payload → codec.encode → E2E.protect → SOME/IP message → TP.segment → transport
接收：transport → TP.reassemble → SOME/IP message → E2E.check → codec.decode → app
```

- `Codec`：默认 JSON；需要标准互操作时替换为 typed codec。
- `E2E`：按 profile 和 binding 维护独立状态；pysomeip 目前不提供，需要自行实现。
- `TP`：按 `segment_size` 分段，接收侧做带超时的重组。

## 4. 模块布局（目标）

```text
src/tinysoa/
  config/
    bindings.py          # EventBusConfig / TopicBinding（已实现）
    factory.py           # create_event_bus（已实现）
  someip/
    config.py            # SomeIPServiceConfig / EventGroup / Method / Field
    endpoint.py          # 共享 SD + transport
    events.py            # SomeIPEventBus
    methods.py           # SomeIPMethodInvoker + Dispatcher
    fields.py            # SomeIPField 门面
    codec.py             # Codec
    e2e.py               # E2EProfile
    tp.py                # Segmenter / Reassembler
  eventbus/
    someip.py            # 兼容 shim
```

迁移时保持 `eventbus/someip.py` 的旧导入可用。

## 5. 分阶段路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| 1 | `EventBusConfig` / `TopicBinding` / `create_event_bus`，应用只写 topic | ✅ |
| 2 | 抽 `SomeIPEndpoint`，event 共享端点 | ✅ |
| 3 | `SomeIPMethodInvoker` + `ServiceInvoker` | ✅ |
| 3.5 | 统一 `SomeIPServiceInstance`（event + method 同服务实例） | ✅ |
| 4 | `SomeIPField` 门面 | 待做 |
| 5 | `Codec` 抽象 | 待做 |
| 6 | E2E 单 profile | 待做 |
| 7 | TP 分段/重组 | 待做 |
| 8 | YAML service config + 端到端测试 | 待做 |

## 6. 反模式

- 不要把 `invoke_method` / `get_field` 加到 `EventBus` ABC。
- 不要让 event/method/field 各自创建 SD 参与者。
- 不要把 E2E/TP 写进业务 handler；它们是管线 transform。
- 不要让应用 import `SomeIPTopicMapping`；它属于配置层。
- 不要假设 pysomeip 已支持 E2E/TP；它目前只提供 SD/service/method 基础能力。
