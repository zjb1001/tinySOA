import subprocess
import sys
import time
from pathlib import Path

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-002-ORCH")


def run_subprocess(script: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(script)], cwd=script.parent)


def main():
    logger.info("Starting ST-002 orchestrator (Pub in one process, Sub in another)")
    base = Path(__file__).parent
    pub_script = base / "publisher.py"
    sub_script = base / "subscriber.py"

    pub_proc = run_subprocess(pub_script)
    logger.info("Publisher process started (PID=%s)", pub_proc.pid)

    # Allow publisher to start and announce before subscriber joins
    time.sleep(2.0)

    sub_proc = run_subprocess(sub_script)
    logger.info("Subscriber process started (PID=%s)", sub_proc.pid)

    sub_rc = sub_proc.wait()
    pub_rc = pub_proc.wait()

    if sub_rc != 0:
        logger.error("Subscriber failed with rc=%s", sub_rc)
        sys.exit(sub_rc)
    if pub_rc != 0:
        logger.error("Publisher failed with rc=%s", pub_rc)
        sys.exit(pub_rc)

    logger.info("ST-002 orchestrator completed successfully")


if __name__ == "__main__":
    main()
