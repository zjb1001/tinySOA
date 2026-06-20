# ST-009 Performance Benchmark Test

Scenarios:
- 1 Publisher → 1 Subscriber
- 1 Publisher → 10 Subscribers
- 10 Publishers → 1 Subscriber
- 10 Publishers → 10 Subscribers

Metrics:
- Throughput (msg/sec)
- Latency percentiles (p50/p95/p99)

Usage:

```bash
python run_test.py
```

Artifacts:
- Results saved under `results/` as JSON per scenario.
