# TCP pub/sub — 一发多收

拓扑：`BROKER`。所有客户端连接中心 `TCPEventBusBroker`，彼此不直连。
进程：1 个 broker + 1 个 publisher + N 个 subscriber。

## 目录

```text
tcp_pubsub_one_to_many/
  server.py       TCPEventBusBroker：监听 + 按 topic 扇出
  publisher.py    TCPEventBus：发布事件
  subscriber.py   TCPEventBus：订阅并打印事件
  tmux.sh         四窗格可视化
  Makefile        start/stop/status/logs/smoke/tmux
```

## 运行

在仓库根目录：

```bash
export PYTHONPATH="$PWD:$PWD/src:$PWD/third_party/pysomeip/src"

# 终端 1：broker
python -m examples.tcp_pubsub_one_to_many.server --host 127.0.0.1 --port 8765

# 终端 2/3：两个 subscriber
python -m examples.tcp_pubsub_one_to_many.subscriber sub-1 --topic demo.topic --port 8765
python -m examples.tcp_pubsub_one_to_many.subscriber sub-2 --topic demo.topic --port 8765

# 终端 4：publisher
python -m examples.tcp_pubsub_one_to_many.publisher --topic demo.topic --count 5 --interval 1.0 --port 8765
```

## Make 快捷方式

```bash
make tmux-pubsub      # tmux 四窗格（broker | sub1 / pub | sub2）
make smoke-pubsub     # 端到端冒烟
make start-pubsub     # 后台常驻
make stop-pubsub
make logs-pubsub
```

## 观察点

- broker 日志显示 `subscribed` / `unsubscribed` 与消息扇出。
- 两个 subscriber 都会收到同一条消息，证明 topic 多播语义。
- publisher 退出后，subscriber 仍保持连接，等待下一条事件。
