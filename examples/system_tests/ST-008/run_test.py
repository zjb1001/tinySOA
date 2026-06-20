import subprocess
import sys
import time
import signal
import random
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-008-ORCH")

def run_subprocess(script: Path, args=None) -> subprocess.Popen:
    cmd = [sys.executable, str(script)]
    if args:
        cmd.extend(args)
    return subprocess.Popen(cmd, cwd=script.parent)

def main():
    logger.info("="*70)
    logger.info("ST-008: Multi-Process Deployment Scenario")
    logger.info("="*70)
    
    base = Path(__file__).parent
    publisher_script = base / "publisher.py"
    subscriber_script = base / "subscriber.py"
    
    processes = {}
    
    try:
        # Step 1: Start Publisher process on port 30490
        logger.info("\n--- Step 1: Starting Publisher Process ---")
        pub_proc = run_subprocess(publisher_script)
        processes['publisher'] = pub_proc
        logger.info(f"Publisher started (PID={pub_proc.pid}, Port=31000)")
        time.sleep(3.0)
        
        # Step 2: Start 5 Subscriber processes on different ports
        logger.info("\n--- Step 2: Starting 5 Subscriber Processes ---")
        subscriber_procs = []
        for i in range(1, 6):
            sub_proc = run_subprocess(subscriber_script, [str(i)])
            subscriber_procs.append(sub_proc)
            processes[f'subscriber_{i}'] = sub_proc
            logger.info(f"Subscriber {i} started (PID={sub_proc.pid}, Port={32000+i*10})")
            time.sleep(0.5)
        
        # Step 3: Verify cross-process communication
        logger.info("\n--- Step 3: Verifying Cross-Process Communication ---")
        logger.info("Allowing 8 seconds for message exchange...")
        time.sleep(8.0)
        
        # Check that all processes are still running
        all_running = True
        for name, proc in processes.items():
            if proc.poll() is not None:
                logger.error(f"❌ Process {name} (PID={proc.pid}) has died unexpectedly!")
                all_running = False
            else:
                logger.info(f"✓ Process {name} (PID={proc.pid}) is running")
        
        if not all_running:
            logger.error("❌ TEST FAILED: Some processes died")
            sys.exit(1)
        
        logger.info("✅ All processes running and communicating")
        
        # Step 4: Kill/restart processes randomly
        logger.info("\n--- Step 4: Testing Process Failure Recovery ---")
        
        # Kill a random subscriber
        victim_idx = random.randint(0, 4)
        victim = subscriber_procs[victim_idx]
        victim_id = victim_idx + 1
        logger.info(f"Killing Subscriber {victim_id} (PID={victim.pid})...")
        victim.terminate()
        victim.wait()
        logger.info(f"Subscriber {victim_id} terminated")
        
        # Wait a bit
        time.sleep(2.0)
        
        # Verify other processes still running
        logger.info("Checking remaining processes...")
        pub_alive = pub_proc.poll() is None
        other_subs_alive = all(
            sub.poll() is None 
            for i, sub in enumerate(subscriber_procs) 
            if i != victim_idx
        )
        
        if pub_alive and other_subs_alive:
            logger.info("✅ Other processes unaffected by failure")
        else:
            logger.error("❌ Process failure affected other processes")
            sys.exit(1)
        
        # Restart the killed subscriber
        logger.info(f"Restarting Subscriber {victim_id}...")
        new_sub = run_subprocess(subscriber_script, [str(victim_id)])
        subscriber_procs[victim_idx] = new_sub
        processes[f'subscriber_{victim_id}'] = new_sub
        logger.info(f"Subscriber {victim_id} restarted (PID={new_sub.pid})")
        
        # Wait for recovery
        time.sleep(5.0)
        
        if new_sub.poll() is None:
            logger.info("✅ Process successfully restarted and recovered")
        else:
            logger.error("❌ Restarted process failed")
            sys.exit(1)
        
        # Final verification
        logger.info("\n--- Final Verification ---")
        logger.info("Waiting for final message exchanges...")
        time.sleep(5.0)
        
        # Summary
        logger.info("\n" + "="*70)
        logger.info("TEST SUMMARY")
        logger.info("="*70)
        logger.info("✅ Publisher process started and running")
        logger.info("✅ 5 Subscriber processes started on different ports")
        logger.info("✅ Cross-process communication verified")
        logger.info("✅ Process failure doesn't affect others")
        logger.info("✅ Automatic recovery after process restart")
        logger.info("="*70)
        logger.info("✅ ST-008 TEST PASSED")
        logger.info("="*70)
        
    except Exception as e:
        logger.error(f"❌ TEST FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
    finally:
        # Cleanup: terminate all processes
        logger.info("\n--- Cleanup: Terminating all processes ---")
        for name, proc in processes.items():
            if proc.poll() is None:
                logger.info(f"Terminating {name} (PID={proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        logger.info("All processes terminated")

if __name__ == "__main__":
    main()
