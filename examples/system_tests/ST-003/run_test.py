import subprocess
import sys
import time
from pathlib import Path

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-003-ORCH")


def run_subprocess(script: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(script)], cwd=script.parent)


def main():
    logger.info("Starting ST-003 orchestrator (Sub First, Pub joins later)")
    base = Path(__file__).parent
    sub_script = base / "subscriber.py"
    pub_script = base / "publisher.py"

    # Start subscriber FIRST (sends SD Find)
    sub_proc = run_subprocess(sub_script)
    logger.info("Subscriber process started first (PID=%s)", sub_proc.pid)

    # Wait for subscriber to send SD Find and be ready
    time.sleep(2.0)

    # Then start publisher (sends SD Offer in response to Find)
    pub_proc = run_subprocess(pub_script)
    logger.info("Publisher process started after delay (PID=%s)", pub_proc.pid)

    # Wait for both to complete
    sub_rc = sub_proc.wait()
    pub_rc = pub_proc.wait()

    if sub_rc != 0:
        logger.error("Subscriber failed with rc=%s", sub_rc)
        sys.exit(sub_rc)
    if pub_rc != 0:
        logger.error("Publisher failed with rc=%s", pub_rc)
        sys.exit(pub_rc)

    logger.info("ST-003 orchestrator completed successfully")


if __name__ == "__main__":
    main()
