import subprocess
import sys
import time
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-M-009-ORCH")

def run_subprocess(script: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(script)], cwd=script.parent)

def main():
    logger.info("Starting ST-M-009 orchestrator (Fire-and-Forget One-Way Calls)")
    base = Path(__file__).parent
    
    server_script = base / "server.py"
    client_script = base / "client.py"
    
    # Start server
    server_proc = run_subprocess(server_script)
    logger.info("Server started (PID=%s, Port=39000)", server_proc.pid)
    time.sleep(2.0)
    
    # Start client
    client_proc = run_subprocess(client_script)
    logger.info("Client started (PID=%s)", client_proc.pid)
    
    # Wait for client to complete
    client_rc = client_proc.wait()
    
    # Terminate server
    logger.info("Terminating server...")
    server_proc.terminate()
    server_proc.wait()
    
    if client_rc != 0:
        logger.error("Test failed with rc=%s", client_rc)
        sys.exit(client_rc)
    
    logger.info("✅ ST-M-009 orchestrator completed successfully")

if __name__ == "__main__":
    main()
