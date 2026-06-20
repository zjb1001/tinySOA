# Multi-publishers, single-subscriber example

This example shows multiple independent publishers sending to the same topic,
consumed by a single subscriber process. You can reuse the TCP EventBus server
and subscriber from `examples/pubsub_multi`.

## Prerequisites

Set PYTHONPATH so `tinysoa` and `someip` resolve from source (run from the
`tinySOA` directory):

```bash
export PYTHONPATH=$PWD/../src:$PWD/src
```

Every script accepts `--log-level {DEBUG,INFO,WARNING,ERROR}` and returns
exit code `0` on success / `1` if the broker is unreachable.

## Steps

1) Start server (reuse existing):

```bash
PYTHONPATH=src python examples/pubsub_multi/server.py --host 127.0.0.1 --port 8767
```

2) Start a single subscriber (reuse existing):

```bash
PYTHONPATH=src python examples/pubsub_multi/subscriber.py sub-collector --topic demo.topic --host 127.0.0.1 --port 8767
```

3) Launch two publishers (in two terminals):

```bash
PYTHONPATH=src python examples/multi_publishers_single_sub/publisher_with_id.py pub-A --topic demo.topic --count 5 --interval 0.5 --host 127.0.0.1 --port 8767
```

```bash
PYTHONPATH=src python examples/multi_publishers_single_sub/publisher_with_id.py pub-B --topic demo.topic --count 5 --interval 0.7 --host 127.0.0.1 --port 8767
```

The single subscriber should receive and print all messages, including the publisher id.
