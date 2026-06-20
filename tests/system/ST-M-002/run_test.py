import subprocess
import sys
import time
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-M-002-ORCH")

def run_subprocess(script: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(script)], cwd=script.parent)

def main():
    logger.info("Starting ST-M-002 orchestrator (Multi-Service RPC Chain)")
    logger.info("Architecture: Service A -> Service B -> Service C")
    base = Path(__file__).parent
    
    service_c_script = base / "service_c.py"
    service_b_script = base / "service_b.py"
    service_a_script = base / "service_a.py"
    
    # Start Service C (leaf service)
    service_c_proc = run_subprocess(service_c_script)
    logger.info("Service C started (PID=%s, Port=33000)", service_c_proc.pid)
    time.sleep(2.0)
    
    # Start Service B (middle service)
    service_b_proc = run_subprocess(service_b_script)
    logger.info("Service B started (PID=%s, Port=32000)", service_b_proc.pid)
    time.sleep(2.0)
    
    # Start Service A (client)
    service_a_proc = run_subprocess(service_a_script)
    logger.info("Service A started (PID=%s)", service_a_proc.pid)
    
    # Wait for Service A to complete
    service_a_rc = service_a_proc.wait()
    
    # Terminate services
    logger.info("Terminating services...")
    service_b_proc.terminate()
    service_c_proc.terminate()
    service_b_proc.wait()
    service_c_proc.wait()
    
    if service_a_rc != 0:
        logger.error("Test failed with rc=%s", service_a_rc)
        sys.exit(service_a_rc)
    
    logger.info("✅ ST-M-002 orchestrator completed successfully")

if __name__ == "__main__":
    main()
