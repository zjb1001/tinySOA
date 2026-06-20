# Cross-Process SOME/IP Pub/Sub (via tinySOA EventBus)

This example proves the core tinySOA claim end-to-end: **two separate OS
processes** exchange events through the SOME/IP protocol stack, using only the
`EventBus` abstraction (`SomeIPEventBus`, built on pysomeip).

`someip` (pysomeip) is one of tinySOA's protocol stacks. Here a **publisher
process** owns a SOME/IP service and publishes events; a **subscriber process**
discovers it via SOME/IP Service Discovery and receives the events. The two
processes share no memory — they talk only over UDP SOME/IP on loopback.

## Layout

| File | Role |
|------|------|
| [`__init__.py`](__init__.py) | Shared topic ↔ SOME/IP mapping (`demo.cross_process` → service `0x2222:0x0001`, eventgroup `0x0001`) |
| [`publisher.py`](publisher.py) | **Process A** — announces a SOME/IP service and publishes events |
| [`subscriber.py`](subscriber.py) | **Process B** — discovers + subscribes, prints each received event, exits 0 on success |
| [`run_cross_process.py`](run_cross_process.py) | Stdlib-only orchestrator: spawns both as real subprocesses and asserts delivery (no deps) |

## No install needed

Both `someip` (pysomeip) and `tinysoa` resolve from source via `PYTHONPATH`:

```bash
cd tinySOA
export PYTHONPATH="$PWD/../src:$PWD/src"   # repo/src (someip) : tinySOA/src (tinysoa)
```

## Run it by hand (two terminals = two processes)

Terminal A (publisher):

```bash
PYTHONPATH=../src:src python -m examples.cross_process_someip.publisher 30 1.0
```

Terminal B (subscriber):

```bash
PYTHONPATH=../src:src python -m examples.cross_process_someip.subscriber 3 40
```

The subscriber prints `RECEIVED seq=N -> {...}` for each event and exits `0`
once it has collected the requested count (default 5), or `1` on timeout.

## Run the whole thing (one command)

```bash
python examples/cross_process_someip/run_cross_process.py
echo "exit: $?"   # 0 = PASS (cross-process delivery confirmed)
```

The orchestrator launches the publisher and subscriber as **separate
subprocesses**, waits for the subscriber to succeed, and tears both down.

## Manage with `make`

```bash
make run          # 前台跑一次编排器（完整跨进程测试）
make start        # 后台常驻启动 publisher + subscriber（记录真实 PID）
make stop         # 停止后台进程
make status       # 查看后台进程状态
make logs         # 实时 tail 后台日志
make pytest       # 跑 pytest（含真实网络慢测试）
make tmux         # tmux 三窗格可视化
make clean        # 停止并清理 .pid/.log
```

## Watch it live in tmux (recommended)

A three-pane tmux layout shows the whole interaction at once:

```
┌──────────────────────────────────────────────┐
│  上：SOME/IP SD 监控（eventbus 发现/订阅握手）  │  ← 先起，全宽
├────────────────────────┬─────────────────────┤
│  发布者 Publisher        │  订阅者 Subscriber   │
└────────────────────────┴─────────────────────┘
```

The top pane runs pysomeip's SD monitor — it surfaces the EventBus discovery
traffic (the publisher's `Offer` and the subscriber's `Find`/`Subscribe`/`Ack`)
that bridges the two processes below.

```bash
make tmux            # 或： ./tmux_demo.sh
# Ctrl+b d 分离（后台保留）；彻底关闭： make tmux-kill
```

Tunables via env: `SESSION`, `PUB_COUNT`, `PUB_INTERVAL`, `SUB_WANT`, `SUB_TIMEOUT`.

## Test it

```bash
PYTHONPATH=../src:src python -m pytest tests/test_cross_process_someip.py -q
```

## Notes on reliability

SOME/IP notifications are UDP and Service Discovery has built-in timing; with a
sensible publish cadence (≥ ~1s) the subscriber reliably collects events. The
default tuning (publish every 1.0s, subscriber wants 3, 40s timeout) is chosen
to be robust on loopback, including WSL2.
