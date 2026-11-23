# tinySOA examples

所有案例都以 **包模块** 运行：

```bash
PYTHONPATH=$PWD:$PWD/src:$PWD/third_party/pysomeip/src \
  python -m examples.<name>.<module>
```

推荐从仓库根目录使用 Makefile（本地 CI 也用同一套命令）：

```bash
make -C examples help
make -C examples smoke-all
```

## 命名约定

| 前缀 | 拓扑 | 说明 |
|---|---|---|
| `local_*` | `LOCAL` | 进程内 `InMemoryEventBus`，无网络 |
| `tcp_*` | `BROKER` | 中心 `TCPEventBusBroker`，客户端 `TCPEventBus` |
| `someip_*` | `PEER` | SOME/IP SD 发现，无中心 broker |

拓扑后缀直接说明“谁多”：

| 后缀 | 含义 |
|---|---|
| `one_pub_one_sub` | 1 publisher → 1 subscriber |
| `one_pub_many_subs` | 1 publisher → N subscribers |
| `many_pubs_one_sub` | N publishers → 1 subscriber |

多进程案例共享的配置模块按领域命名，不使用 `_common.py`：

- `service_contract.py`：单服务 topic / SOME/IP ID / 角色相关的 endpoint 配置
- `sensor_contract.py`：多 sensor 服务的 identity / topic / port 契约
- `calculator_contract.py`：RPC 服务的 method ID 与 server/client 配置

## 案例目录

| 案例 | 拓扑 | 进程 | 入口 | 观察重点 |
|---|---|---|---|---|
| `local_echo_service` | LOCAL | 单进程 | `local_echo_service.app` | 方法调用 + 事件 |
| `local_interceptor_auth` | LOCAL | 单进程 | `local_interceptor_auth.app` | 拦截器排序 / Auth 短路 / 异常传播 |
| `local_vehicle_platform` | LOCAL | 单进程 | `local_vehicle_platform.app` | Container 依赖/生命周期/健康检查 |
| `local_pubsub_topologies` | LOCAL | 单进程 | `local_pubsub_topologies.app` | 1 pub→1 sub / 1 pub→N subs / N pubs→1 sub |
| `tcp_pubsub_one_pub_many_subs` | BROKER | 1 pub + N sub | `tcp_pubsub_one_pub_many_subs.{server,publisher,subscriber}` | 1 pub → N subs：TCP 中心 broker 扇出 |
| `someip_pubsub_one_pub_one_sub` | PEER | 1 pub + 1 sub | `someip_pubsub_one_pub_one_sub.{publisher,subscriber}` | 1 pub → 1 sub：最小 `SomeIPService` 事件链路 |
| `someip_pubsub_one_pub_many_subs` | PEER | 1 pub + N sub | `someip_pubsub_one_pub_many_subs.{publisher,subscriber}` | 1 pub → N subs：同一服务多订阅者 |
| `someip_pubsub_many_pubs_one_sub` | PEER | 3 pub + 1 agg | `someip_pubsub_many_pubs_one_sub.*` | N pubs → 1 sub：多服务发现、聚合仪表盘 |
| `someip_method_call` | PEER | server + client | `someip_method_call.{server,client}` | SOME/IP RPC（`SomeIPService` 门面） |

应用层推荐使用门面；注册状态属于 bus，句柄只携带 topic/handler：

```python
publisher = bus.publisher("demo.topic")
subscriber = bus.subscriber("demo.topic", handler)

await bus.register(publisher)
await bus.register(subscriber)
await publisher.publish({"value": 1})

# 或 SOME/IP
service = SomeIPService(binding, event_mappings=EVENT_MAPPINGS)
publisher = service.publisher("demo.topic")
subscriber = service.subscriber("demo.topic", handler)

await service.start()
await service.register(publisher)     # SD Offer
await service.register(subscriber)    # SD FindSubscribe + handler
await publisher.publish({"value": 1})
```

`publisher.publish()` 在未注册时抛 `StateError`；`bus.unregister(...)` 撤销注册。
低层 `bus.publish(EventMessage(...))` 保留给框架内部、测试和高级用法。

## 常用命令

```bash
# 本地单进程
make -C examples echo
make -C examples interceptors
make -C examples vdp
make -C examples topologies
make -C examples topologies SCENARIO=1vn SUBSCRIBERS=5

# TCP broker
make -C examples tmux-pubsub-one-pub-many-subs
make -C examples smoke-pubsub-one-pub-many-subs

# SOME/IP
make -C examples tmux-someip-one-pub-one-sub
make -C examples smoke-someip-one-pub-one-sub
make -C examples tmux-someip-one-pub-many-subs
make -C examples smoke-someip-one-pub-many-subs
make -C examples tmux-someip-many-pubs-one-sub
make -C examples smoke-calc

# 全局
make -C examples smoke-all
make -C examples clean-all
```

每个案例目录都有自己的 `Makefile` 和 `README.md`；单进程案例用 `make run`，
多进程案例用 `make start/stop/logs/smoke/tmux`。
