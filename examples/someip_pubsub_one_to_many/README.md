# SOME/IP pub/sub — 一发多收

拓扑：`PEER`。一个 publisher 通过 SOME/IP SD 通告服务，多个独立 subscriber
进程分别订阅同一个 eventgroup；事件通过 unicast notification 投递。

## 目录

```text
someip_pubsub_one_to_many/
  _common.py      topic 与 SOME/IP ID / 本地端口配置
  publisher.py    SD Offer + publish
  subscriber.py   SD FindSubscribe + async handler
  tmux.sh         左: publisher / 右上: sub-1 / 右下: sub-2
  Makefile        start/stop/status/logs/smoke/tmux
```

应用侧通过 `SomeIPService` 门面使用，只写 `TOPIC`：

```python
service = SomeIPService(
    service_binding(server_port=PUBLISHER_PORT),
    event_mappings=EVENT_MAPPINGS,
    is_publisher=True,
)
publisher = service.publisher(TOPIC)
await service.start()
await publisher.publish({"value": 21.5})
```

SOME/IP ID 在 `_common.py` 的 `MAPPING` / `service_binding()` 中。

## 运行

在仓库根目录：

```bash
export PYTHONPATH="$PWD:$PWD/src:$PWD/third_party/pysomeip/src"

# 终端 1：publisher
python -m examples.someip_pubsub_one_to_many.publisher --count 30 --interval 1.0

# 终端 2：subscriber 1
python -m examples.someip_pubsub_one_to_many.subscriber sub-1 --want 5 --local-port 30930

# 终端 3：subscriber 2
python -m examples.someip_pubsub_one_to_many.subscriber sub-2 --want 5 --local-port 30940
```

## Make 快捷方式

```bash
make tmux-someip-one-to-many      # tmux 三窗格
make smoke-someip-one-to-many     # 两个 subscriber 各至少收到 --want 条
make start-someip-one-to-many
make stop-someip-one-to-many
make logs-someip-one-to-many
```

## 观察点

- publisher 的 SD Offer 被两个 subscriber 分别发现。
- 两个 subscriber 都收到同一条 notification 的独立 unicast 副本。
- 每个 subscriber 有自己的接收端口（由 SD 协商，日志里可见）。
- subscriber 内部有约 5s 的订阅交错延迟，publisher 需要运行足够久。

> WSL2 回环上 SD 偶发投递竞态；失败时先确认没有遗留 SOME/IP 进程。
