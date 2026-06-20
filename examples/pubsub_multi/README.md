# Pub/Sub (multi-process) example

This example demonstrates one publisher and multiple subscribers running as independent processes over a simple TCP EventBus.

## Prerequisites

`tinysoa` (and its `someip` dependency) resolve from source — set `PYTHONPATH`
to both source roots (run from the repo root):

```bash
export PYTHONPATH="$PWD/src:$PWD/tinySOA/src"
```

Every script also accepts `--log-level {DEBUG,INFO,WARNING,ERROR}` and returns
exit code `0` on success / clean shutdown (SIGINT/SIGTERM) and `1` if the broker
is unreachable or the port is taken.

## Quick start

Open three terminals and run:

1) Start the EventBus server:

```bash
python tinySOA/examples/pubsub_multi/server.py --host 127.0.0.1 --port 8765
```

2) Start two subscribers (in separate terminals):

```bash
python tinySOA/examples/pubsub_multi/subscriber.py sub-1 --topic demo.topic --host 127.0.0.1 --port 8765
```

```bash
python tinySOA/examples/pubsub_multi/subscriber.py sub-2 --topic demo.topic --host 127.0.0.1 --port 8765
```

3) Publish some messages:

```bash
python tinySOA/examples/pubsub_multi/publisher.py --topic demo.topic --count 5 --interval 1.0 --host 127.0.0.1 --port 8765
```

Each subscriber will receive all published messages for the topic.

> Note: This TCP EventBus is for development/demo only (no auth/persistence).