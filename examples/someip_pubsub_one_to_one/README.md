# SOME/IP pub/sub — 一对一

拓扑：`PEER`。一个 publisher 通过 SOME/IP SD 通告服务，一个 subscriber
发现并订阅；事件通过 unicast notification 投递。

## 目录

```text
someip_pubsub_one_to_one/
  _common.py      topic / SOME/IP ID / service binding
  publisher.py    SomeIPService + publisher.publish
  subscriber.py   SomeIPService + subscriber.on
  tmux.sh         左: Publisher / 右: Subscriber
  Makefile        start/stop/status/logs/smoke/tmux
```

应用侧只使用 `TOPIC`：

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

## 运行

在仓库根目录：

```bash
export PYTHONPATH="$PWD:$PWD/src:$PWD/third_party/pysomeip/src"

# 终端 1：publisher
python -m examples.someip_pubsub_one_to_one.publisher --count 30 --interval 1.0

# 终端 2：subscriber
python -m examples.someip_pubsub_one_to_one.subscriber --want 5 --local-port 30980
```

## Make 快捷方式

```bash
make tmux-someip-one-to-one      # tmux 双窗格
make smoke-someip-one-to-one     # 端到端冒烟
make start-someip-one-to-one
make stop-someip-one-to-one
make logs-someip-one-to-one
```

## 观察点

- publisher 的 SD Offer 被 subscriber 发现。
- subscriber 收到 unicast notification，日志出现 `RECEIVED seq=...`。
- subscriber 内部有约 5s 订阅延迟，publisher 需要运行足够久。
- 这是最小 SOME/IP 事件链路，适合对比 1vN / Nv1 案例。

> WSL2 回环上 SD 偶发投递竞态；失败时先确认没有遗留 SOME/IP 进程。
