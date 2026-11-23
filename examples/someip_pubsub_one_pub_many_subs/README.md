# SOME/IP pub/sub — 1 publisher → N subscribers

拓扑：`PEER`。一个 publisher 通过 SOME/IP SD 通告服务，多个独立 subscriber
进程分别订阅同一个 eventgroup；事件通过 unicast notification 投递。

## 目录

```text
someip_pubsub_one_pub_many_subs/
  service_contract.py  publisher/subscriber 共享的 topic + SOME/IP ID
  publisher.py         SD Offer + service.register(publisher)
  subscriber.py        SD FindSubscribe + service.register(subscriber)
  tmux.sh              左: publisher / 右上: sub-1 / 右下: sub-2
  Makefile             start/stop/status/logs/smoke/tmux
```

`service_contract.py` 是 publisher 和多个 subscriber 的共同契约；两端分别通过
`publisher_config()` / `subscriber_config()` 获取符合自己角色的 endpoint 配置。

```python
# Publisher 进程
config = publisher_config(PUBLISHER_PORT)
service = SomeIPService(config, event_mappings=EVENT_MAPPINGS, is_publisher=True)
publisher = service.publisher(TOPIC)

await service.start()                  # 创建 endpoint / 绑定端口 / 启动 SD
await service.register(publisher)      # SD Offer
await publisher.publish({"value": 21.5})


# 每个 Subscriber 进程独立注册
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
python -m examples.someip_pubsub_one_pub_many_subs.publisher --count 30 --interval 1.0

# 终端 2：subscriber 1
python -m examples.someip_pubsub_one_pub_many_subs.subscriber sub-1 --want 5 --local-port 30930

# 终端 3：subscriber 2
python -m examples.someip_pubsub_one_pub_many_subs.subscriber sub-2 --want 5 --local-port 30940
```

## Make 快捷方式

```bash
make tmux-someip-one-pub-many-subs      # tmux 三窗格
make smoke-someip-one-pub-many-subs     # 两个 subscriber 各至少收到 --want 条
make start-someip-one-pub-many-subs
make stop-someip-one-pub-many-subs
make logs-someip-one-pub-many-subs
```

## 观察点

- publisher 的 SD Offer 被两个 subscriber 分别发现。
- 两个 subscriber 都收到同一条 notification 的独立 unicast 副本。
- 每个 subscriber 有自己的接收端口（由 SD 协商，日志里可见）。
- subscriber 内部有约 5s 的订阅交错延迟，publisher 需要运行足够久。

> WSL2 回环上 SD 偶发投递竞态；失败时先确认没有遗留 SOME/IP 进程。
