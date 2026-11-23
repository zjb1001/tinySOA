# Local pub/sub — topology matrix (1p→1s, 1p→Ns, Np→1s)

拓扑：`LOCAL`（`InMemoryEventBus`，单进程、无网络）。
目的：**先观察应用代码效果**，再进入 SOME/IP method/field 阶段。

三个场景共享同一套应用 API：

```python
bus = create_event_bus(EventBusConfig(kind=EventBusKind.INMEMORY))
await bus.start()

publisher = bus.publisher(TOPIC)
subscriber = bus.subscriber(TOPIC, handler)

await bus.register(publisher)
await bus.register(subscriber)
await publisher.publish(...)
await bus.stop()
```

## 场景

| 场景 | 进程内结构 | 入口 |
|---|---|---|
| `1v1` | 1 publisher → 1 subscriber | `run_one_to_one` |
| `1vN` | 1 publisher → N subscribers | `run_one_to_many` |
| `Nv1` | N publishers → 1 subscriber | `run_many_to_one` |

`Nv1` 采用 round-robin 发布，subscriber 会看到来自 `pub-1`、`pub-2`、`pub-3` 的消息。

## 运行

```bash
make run
make run SCENARIO=1v1
make run SCENARIO=1vn SUBSCRIBERS=5
make run SCENARIO=nv1 PUBLISHERS=3
```

输出示例：

```text
1v1 published=3 delivered={'sub-1': 3} sources=() => PASS
1vN published=3 delivered={'sub-1': 3, 'sub-2': 3, 'sub-3': 3} sources=() => PASS
Nv1 published=9 delivered={'sub-1': 9} sources=('pub-1', 'pub-2', 'pub-3') => PASS
```

## 观察点

- 三个场景的业务代码几乎相同：只依赖 `EventMessage`、`topic`、async handler。
- 1vN 中每个 subscriber 都收到全部消息。
- Nv1 中 subscriber 收到所有 publisher 的消息，并能从 payload 区分来源。
- 换成 TCP / SOME/IP 时，应用代码不用改，只换 `EventBusConfig.kind` 和运行拓扑。
