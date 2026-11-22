# SOME/IP pub/sub echo

拓扑：`PEER`。publisher 通过 SOME/IP SD 通告服务，subscriber 动态发现并订阅；
事件通过 unicast notification 直接投递，没有中心 broker。

## 目录

```text
someip_pubsub_echo/
  _common.py      topic ↔ (service_id, instance_id, eventgroup_id) 映射
  publisher.py    SD Offer + publish
  subscriber.py   SD FindSubscribe + async handler
  tmux.sh         上: SD 监控 / 下左: publisher / 下右: subscriber
  Makefile        start/stop/status/logs/smoke/tmux
```

## 运行

在仓库根目录：

```bash
export PYTHONPATH="$PWD:$PWD/src:$PWD/third_party/pysomeip/src"

# 终端 1：publisher
python -m examples.someip_pubsub_echo.publisher --count 30 --interval 1.0

# 终端 2：subscriber
python -m examples.someip_pubsub_echo.subscriber --want 5
```

## Make 快捷方式

```bash
make tmux-echo-someip      # tmux 三窗格
make smoke-echo-someip     # bounded 冒烟
make start-echo-someip
make stop-echo-someip
make logs-echo-someip
```

> subscriber 内部有约 5s 的订阅交错延迟；冒烟时 publisher 需要运行足够久。
> WSL2 回环上 SD 偶发投递竞态，建议使用干净 loopback 或 Linux CI。

## 观察点

- SD 窗格出现 `offer`、`Subscribe`、`SubscribeAck`。
- subscriber 收到 `RECEIVED seq=...`。
- publisher 的 `SD Offer` 与 subscriber 的 `FindSubscribe` 是 peer-to-peer 发现。
