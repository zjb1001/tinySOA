import subprocess
import sys
import time
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-005-ORCH")


def run_subprocess(script: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(script)], cwd=script.parent)


def main():
    logger.info("="*70)
    logger.info("Starting ST-005 orchestrator (High Frequency Stress Test)")
    logger.info("="*70)
    
    base = Path(__file__).parent
    sub_script = base / "subscriber.py"
    pub_script = base / "publisher.py"

    # Step 1: Start subscriber first
    sub_proc = run_subprocess(sub_script)
    logger.info("\n[STEP 1] Subscriber process started (PID=%s)", sub_proc.pid)
    logger.info("         Subscriber is ready and waiting for messages...")

    # Step 2: Wait for subscriber to be ready and register for SD
    time.sleep(2.0)

    # Step 3: Start publisher
    pub_proc = run_subprocess(pub_script)
    logger.info("\n[STEP 2] Publisher process started (PID=%s)", pub_proc.pid)
    logger.info("         Publisher will send 1000 messages at 20ms interval...")

    # Step 4: Wait for both processes to complete
    logger.info("\n[STEP 3] Running stress test...")
    logger.info("         This may take 25-35 seconds...")
    
    try:
        sub_rc = sub_proc.wait(timeout=50.0)
        logger.info("\nSubscriber completed with rc=%s", sub_rc)
    except subprocess.TimeoutExpired:
        logger.error("Subscriber timeout; terminating")
        sub_proc.terminate()
        try:
            sub_proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            sub_proc.kill()
        sub_rc = 1

    try:
        pub_rc = pub_proc.wait(timeout=10.0)
        logger.info("Publisher completed with rc=%s", pub_rc)
    except subprocess.TimeoutExpired:
        logger.error("Publisher timeout; terminating")
        pub_proc.terminate()
        try:
            pub_proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            pub_proc.kill()
        pub_rc = 1

    if sub_rc != 0 or pub_rc != 0:
        logger.error("\n" + "="*70)
        logger.error("FAILED: Subscriber rc=%s, Publisher rc=%s", sub_rc, pub_rc)
        logger.error("="*70)
        sys.exit(1)

    logger.info("\n" + "="*70)
    logger.info("ST-005 orchestrator completed successfully")
    logger.info("High frequency stress test verified!")
    logger.info("="*70)


if __name__ == "__main__":
    main()
