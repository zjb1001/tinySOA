import subprocess
import sys
import time
from pathlib import Path
import signal
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-004-ORCH")


def run_subprocess(script: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(script)], cwd=script.parent)


def main():
    logger.info("="*70)
    logger.info("Starting ST-004 orchestrator (Service Restart Resilience)")
    logger.info("="*70)
    
    base = Path(__file__).parent
    sub_script = base / "subscriber.py"
    pub_script = base / "publisher.py"

    # Step 1: Start subscriber first
    sub_proc = run_subprocess(sub_script)
    logger.info("\n[STEP 1] Subscriber process started (PID=%s)", sub_proc.pid)
    logger.info("         Subscriber will wait for service discovery...")

    # Step 2: Wait for subscriber to be ready and register for SD Find
    time.sleep(2.0)

    # Step 3: Start publisher
    pub_proc = run_subprocess(pub_script)
    logger.info("\n[STEP 2] Publisher process started (PID=%s)", pub_proc.pid)
    logger.info("         Publisher will establish connection with subscriber...")

    # Step 4: Let them communicate for a bit (8s from publisher's sleep)
    time.sleep(3.0)

    # Step 5: Simulate publisher crash by terminating process
    logger.info("\n[STEP 3] Simulating publisher crash (SIGTERM)...")
    pub_proc.terminate()
    
    # Wait for process to terminate
    try:
        pub_proc.wait(timeout=3.0)
        logger.info("         Publisher terminated successfully")
    except subprocess.TimeoutExpired:
        logger.warning("         Publisher did not terminate; killing forcefully")
        pub_proc.kill()
        pub_proc.wait()

    # Step 6: Wait 1 second as per test plan
    logger.info("\n[STEP 4] Waiting 1 second before restart...")
    time.sleep(1.0)

    # Step 7: Restart publisher
    pub_proc = run_subprocess(pub_script)
    logger.info("\n[STEP 5] Publisher restarted (PID=%s)", pub_proc.pid)
    logger.info("         Publisher re-establishes service discovery...")

    # Step 8: Wait for both processes to complete
    logger.info("\n[STEP 6] Waiting for subscriber and publisher to complete...")
    
    try:
        sub_rc = sub_proc.wait(timeout=40.0)
        logger.info("\nSubscriber completed with rc=%s", sub_rc)
    except subprocess.TimeoutExpired:
        logger.error("Subscriber timeout; terminating")
        sub_proc.terminate()
        sub_rc = sub_proc.wait()

    try:
        pub_rc = pub_proc.wait(timeout=10.0)
        logger.info("Publisher completed with rc=%s", pub_rc)
    except subprocess.TimeoutExpired:
        logger.error("Publisher timeout; terminating")
        pub_proc.terminate()
        pub_rc = pub_proc.wait()

    if sub_rc != 0 or pub_rc != 0:
        logger.error("\n" + "="*70)
        logger.error("FAILED: Subscriber rc=%s, Publisher rc=%s", sub_rc, pub_rc)
        logger.error("="*70)
        sys.exit(1)

    logger.info("\n" + "="*70)
    logger.info("ST-004 orchestrator completed successfully")
    logger.info("Service restart resilience verified!")
    logger.info("="*70)


if __name__ == "__main__":
    main()
