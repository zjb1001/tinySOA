# SOME/IP pub/sub — 1 publisher → 1 subscriber

拓扑：`PEER`。一个 publisher 通过 SOME/IP SD 通告服务，一个 subscriber
发现并订阅；事件通过 unicast notification 投递。

## 目录

```text
someip_pubsub_one_pub_one_sub/
  service_contract.py  publisher/subscriber 共享的 topic + SOME/IP ID
  publisher.py         SD Offer + service.register(publisher)
  subscriber.py        SD FindSubscribe + service.register(subscriber)
  tmux.sh              左: Publisher / 右: Subscriber
  Makefile             start/stop/status/logs/smoke/tmux
```

`service_contract.py` 是 publisher 和 subscriber 的共同契约：topic、service_id、
instance_id、eventgroup_id 只定义一次，避免两端配置漂移；两端分别通过
`publisher_config()` / `subscriber_config()` 获取符合自己角色的 endpoint 配置。

```python
# publisher.py
config = publisher_config(PUBLISHER_PORT)
service = SomeIPService(config, event_mappings=EVENT_MAPPINGS, is_publisher=True)
publisher = service.publisher(TOPIC)

await service.start()                  # 创建 endpoint / 绑定端口 / 启动 SD
await service.register(publisher)      # SD Offer
await publisher.publish({"value": 21.5})


# subscriber.py
async def on_event(message: EventMessage) -> None:
    ...

config = subscriber_config(args.local_port)
service = SomeIPService(config, event_mappings=EVENT_MAPPINGS, is_publisher=False)
subscriber = service.subscriber(TOPIC, on_event)

await service.start()                  # 创建 endpoint / 绑定端口 / 启动 SD
await service.register(subscriber)     # SD FindSubscribe + handler
```

## 运行

在仓库根目录：

```bash
export PYTHONPATH="$PWD:$PWD/src:$PWD/third_party/pysomeip/src"

# 终端 1：publisher
python -m examples.someip_pubsub_one_pub_one_sub.publisher --count 30 --interval 1.0

# 终端 2：subscriber
python -m examples.someip_pubsub_one_pub_one_sub.subscriber --want 5 --local-port 30980
```

## Make 快捷方式

```bash
make tmux-someip-one-pub-one-sub      # tmux 双窗格
make smoke-someip-one-pub-one-sub     # 端到端冒烟
make start-someip-one-pub-one-sub
make stop-someip-one-pub-one-sub
make logs-someip-one-pub-one-sub
```

## 观察点

- publisher 的 SD Offer 被 subscriber 发现。
- subscriber 收到 unicast notification，日志出现 `RECEIVED seq=...`。
- subscriber 内部有约 5s 订阅延迟，publisher 需要运行足够久。
- 这是最小 SOME/IP 事件链路，适合对比 1vN / Nv1 案例。

> WSL2 回环上 SD 偶发投递竞态；失败时先确认没有遗留 SOME/IP 进程。
