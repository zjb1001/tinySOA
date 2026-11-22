# TCP pub/sub — 多发一收

拓扑：`BROKER`。复用 `tcp_pubsub_one_to_many` 的 broker 与 subscriber，
本案例只提供带 `publisher_id` 的 publisher，用来区分同一 topic 上的多个来源。

## 目录

```text
tcp_pubsub_many_to_one/
  publisher_with_id.py   在 payload/header 中带 publisher_id
  tmux.sh                四窗格可视化
  Makefile               start/stop/status/logs/smoke/tmux
```

复用模块：

```text
examples.tcp_pubsub_one_to_many.server
examples.tcp_pubsub_one_to_many.subscriber
```

## 运行

在仓库根目录：

```bash
export PYTHONPATH="$PWD:$PWD/src:$PWD/third_party/pysomeip/src"

# 终端 1：broker（默认 8766，避免和 one-to-many 冲突）
python -m examples.tcp_pubsub_one_to_many.server --port 8766

# 终端 2：单 subscriber
python -m examples.tcp_pubsub_one_to_many.subscriber collector --topic demo.topic --port 8766

# 终端 3/4：两个 publisher
python -m examples.tcp_pubsub_many_to_one.publisher_with_id pub-A --topic demo.topic --count 5 --interval 0.5 --port 8766
python -m examples.tcp_pubsub_many_to_one.publisher_with_id pub-B --topic demo.topic --count 5 --interval 0.7 --port 8766
```

## Make 快捷方式

```bash
make tmux-pubsub-many      # tmux 四窗格（broker | sub / pub-A | pub-B）
make smoke-pubsub-many     # 端到端冒烟
make start-pubsub-many     # 后台常驻
make stop-pubsub-many
make logs-pubsub-many
```

## 观察点

- subscriber 日志会同时出现 `from=pub-A` 与 `from=pub-B`。
- `publisher_with_id.py` 同时把来源写进 payload 与 `x-publisher-id` header。
- 单 subscriber 不区分来源，需要在应用层按 id 聚合或去重。
