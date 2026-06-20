import json
import subprocess
import sys
import time
from pathlib import Path
from statistics import median

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-009-ORCH")

BASE = Path(__file__).parent
PUB = BASE / "publisher.py"
SUB = BASE / "subscriber.py"
RESULTS_DIR = BASE / "results"


def run_proc(script: Path, env: dict) -> subprocess.Popen:
    new_env = {**os_environ_clean(), **env}
    return subprocess.Popen([sys.executable, str(script)], cwd=script.parent, env=new_env)


def os_environ_clean():
    import os
    # Avoid leaking virtualenv variables that could break networking
    env = dict(os.environ)
    return env


def percentile(values, p):
    if not values:
        return 0.0
    vals = sorted(values)
    k = max(0, min(len(vals) - 1, int(round((p / 100.0) * (len(vals) - 1)))))
    return vals[k]


def aggregate_results(files):
    lat_all = []
    start_min = None
    end_max = None
    total_msgs = 0
    for fp in files:
        data = json.loads(Path(fp).read_text())
        lat_all.extend(data.get("latencies", []))
        total_msgs += sum(data.get("counts", {}).values())
        st = data.get("start_time", 0)
        et = data.get("end_time", 0)
        if st:
            start_min = st if start_min is None else min(start_min, st)
        if et:
            end_max = et if end_max is None else max(end_max, et)
    duration = max(0.0, (end_max or 0) - (start_min or 0))
    thr = total_msgs / duration if duration > 0 else 0.0
    return {
        "total_messages": total_msgs,
        "duration_s": duration,
        "throughput_msg_per_s": thr,
        "p50_ms": percentile(lat_all, 50) * 1000.0,
        "p95_ms": percentile(lat_all, 95) * 1000.0,
        "p99_ms": percentile(lat_all, 99) * 1000.0,
    }


def scenario_1_pub_1_sub(messages=1000):
    logger.info("Scenario: 1 Pub -> 1 Sub")
    RESULTS_DIR.mkdir(exist_ok=True)

    sub_env = {
        "PERF_SUB_ID": "0",
        "PERF_TOPICS": "perf.topic.shared",
        "PERF_EXPECTED_PER_TOPIC": str(messages),
        "PERF_RESULTS_FILE": str(RESULTS_DIR / "1x1_sub.json"),
    }
    sub_proc = run_proc(SUB, sub_env)
    time.sleep(2.0)

    pub_env = {
        "PERF_PUB_ID": "0",
        "PERF_TOPICS": "perf.topic.shared",
        "PERF_MESSAGES_PER_TOPIC": str(messages),
        "PERF_INTERVAL_S": "0.0005",  # 0.5ms interval for stable delivery
    }
    pub_proc = run_proc(PUB, pub_env)

    sub_rc = sub_proc.wait(timeout=60.0)
    pub_rc = pub_proc.wait(timeout=60.0)

    assert sub_rc == 0 and pub_rc == 0, f"Processes failed: sub={sub_rc} pub={pub_rc}"

    agg = aggregate_results([RESULTS_DIR / "1x1_sub.json"])
    logger.info("1x1: msgs=%s, thr=%.1f msg/s, p95=%.2fms, p99=%.2fms", agg["total_messages"], agg["throughput_msg_per_s"], agg["p95_ms"], agg["p99_ms"])
    return agg


def scenario_1_pub_10_subs(messages=500):
    logger.info("Scenario: 1 Pub -> 10 Subs")
    RESULTS_DIR.mkdir(exist_ok=True)
    subs = []
    for sid in range(10):
        env = {
            "PERF_SUB_ID": str(sid),
            "PERF_TOPICS": "perf.topic.shared",
            "PERF_EXPECTED_PER_TOPIC": str(messages),
            "PERF_RESULTS_FILE": str(RESULTS_DIR / f"1x10_sub_{sid}.json"),
        }
        subs.append(run_proc(SUB, env))
    time.sleep(2.0)

    pub_env = {
        "PERF_PUB_ID": "0",
        "PERF_TOPICS": "perf.topic.shared",
        "PERF_MESSAGES_PER_TOPIC": str(messages),
        "PERF_INTERVAL_S": "0.001",  # 1ms interval for 10 subscribers
    }
    pub_proc = run_proc(PUB, pub_env)

    for p in subs:
        assert p.wait(timeout=90.0) == 0
    assert pub_proc.wait(timeout=60.0) == 0

    files = [RESULTS_DIR / f"1x10_sub_{sid}.json" for sid in range(10)]
    agg = aggregate_results(files)
    logger.info("1x10: msgs=%s, thr=%.1f msg/s, p95=%.2fms, p99=%.2fms", agg["total_messages"], agg["throughput_msg_per_s"], agg["p95_ms"], agg["p99_ms"])
    return agg


def scenario_10_pub_1_sub(messages_per_pub=100):
    logger.info("Scenario: 10 Pubs -> 1 Sub")
    RESULTS_DIR.mkdir(exist_ok=True)

    topics = ",".join([f"perf.topic.{i}" for i in range(10)])
    sub_env = {
        "PERF_SUB_ID": "0",
        "PERF_TOPICS": topics,
        "PERF_EXPECTED_PER_TOPIC": str(messages_per_pub),
        "PERF_RESULTS_FILE": str(RESULTS_DIR / "10x1_sub.json"),
    }
    sub_proc = run_proc(SUB, sub_env)
    time.sleep(2.0)

    pubs = []
    for pid in range(10):
        env = {
            "PERF_PUB_ID": str(pid),
            "PERF_TOPICS": f"perf.topic.{pid}",
            "PERF_MESSAGES_PER_TOPIC": str(messages_per_pub),
            "PERF_INTERVAL_S": "0.01",  # Add 10ms interval to reduce burst load
        }
        pubs.append(run_proc(PUB, env))
        time.sleep(0.1)  # Stagger publisher startup by 100ms each

    assert sub_proc.wait(timeout=120.0) == 0
    for p in pubs:
        assert p.wait(timeout=90.0) == 0

    agg = aggregate_results([RESULTS_DIR / "10x1_sub.json"])
    logger.info("10x1: msgs=%s, thr=%.1f msg/s, p95=%.2fms, p99=%.2fms", agg["total_messages"], agg["throughput_msg_per_s"], agg["p95_ms"], agg["p99_ms"])
    return agg


def scenario_10_pub_10_subs(messages_per_pub=100):
    logger.info("Scenario: 10 Pubs -> 10 Subs (paired)")
    RESULTS_DIR.mkdir(exist_ok=True)

    subs = []
    pubs = []
    for i in range(10):
        topic = f"perf.topic.{i}"
        s_env = {
            "PERF_SUB_ID": str(i),
            "PERF_TOPICS": topic,
            "PERF_EXPECTED_PER_TOPIC": str(messages_per_pub),
            "PERF_RESULTS_FILE": str(RESULTS_DIR / f"10x10_sub_{i}.json"),
        }
        subs.append(run_proc(SUB, s_env))
    time.sleep(2.0)
    for i in range(10):
        p_env = {
            "PERF_PUB_ID": str(i),
            "PERF_TOPICS": f"perf.topic.{i}",
            "PERF_MESSAGES_PER_TOPIC": str(messages_per_pub),
            "PERF_INTERVAL_S": "0.01",  # 10ms interval for stability
        }
        pubs.append(run_proc(PUB, p_env))

    for p in subs:
        assert p.wait(timeout=120.0) == 0
    for p in pubs:
        assert p.wait(timeout=90.0) == 0

    files = [RESULTS_DIR / f"10x10_sub_{i}.json" for i in range(10)]
    agg = aggregate_results(files)
    logger.info("10x10: msgs=%s, thr=%.1f msg/s, p95=%.2fms, p99=%.2fms", agg["total_messages"], agg["throughput_msg_per_s"], agg["p95_ms"], agg["p99_ms"])
    return agg


def main():
    logger.info("=" * 70)
    logger.info("Starting ST-009 orchestrator (Performance Benchmark Test)")
    logger.info("=" * 70)

    RESULTS_DIR.mkdir(exist_ok=True)

    results = {}
    try:
        results["1x1"] = scenario_1_pub_1_sub(messages=2000)
        results["1x10"] = scenario_1_pub_10_subs(messages=1000)
        results["10x1"] = scenario_10_pub_1_sub(messages_per_pub=500)
        results["10x10"] = scenario_10_pub_10_subs(messages_per_pub=300)
    except AssertionError as e:
        logger.error("Scenario failed: %s", e)
        sys.exit(1)

    # Print final summary
    logger.info("\n" + "-" * 50)
    logger.info("ST-009 Summary:")
    for name, r in results.items():
        logger.info("%s: thr=%.1f msg/s, p95=%.2fms, p99=%.2fms", name, r["throughput_msg_per_s"], r["p95_ms"], r["p99_ms"])
    logger.info("-" * 50)

    # Basic expectations per plan
    ok = True
    for name, r in results.items():
        if r["throughput_msg_per_s"] < 1000.0:
            logger.error("%s: Throughput below expectation (%.1f msg/s)", name, r["throughput_msg_per_s"])
            ok = False
        if r["p99_ms"] > 100.0:
            logger.error("%s: P99 latency above expectation (%.2fms)", name, r["p99_ms"])
            ok = False

    if not ok:
        logger.error("ST-009 did not meet expected performance targets")
        sys.exit(1)

    logger.info("ST-009 completed successfully")


if __name__ == "__main__":
    main()
