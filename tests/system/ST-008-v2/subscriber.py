#!/usr/bin/env python3
"""
ST-008 Multi-Process Subscriber (v2)
====================================
Calls the Publisher's simple_add RPC method
"""

import asyncio
import logging
import struct
import sys
import os
from concurrent.futures import ThreadPoolExecutor

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../src")))

from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping
from someip.header import SOMEIPHeader
from someip.client import SomeIPClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def install_quiet_exception_handler(loop):
    """Suppress noisy task exception logs."""
    def handle_exception(args):
        pass
    loop.set_exception_handler(handle_exception)


async def main():
    subscriber_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    logger = logging.getLogger(f"ST-008-Sub-{subscriber_id}-v2")
    
    logger.info(f"=== ST-008 Subscriber {subscriber_id} Process (v2) ===")
    logger.info(f"Process ID: {os.getpid()}")
    
    # Dummy mapping
    mappings = {
        "multiprocess.add": SomeIPTopicMapping(
            service_id=0x0800,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    
    loop = asyncio.get_running_loop()
    install_quiet_exception_handler(loop)
    
    # Subscriber mode - no announcer
    subscriber_port = 32000 + (subscriber_id * 10)
    bus = SomeIPEventBus(
        mappings=mappings,
        local_ip="127.0.0.1",
        publisher_port=subscriber_port,
        is_publisher=False
    )
    
    await bus.start()
    logger.info(f"EventBus started on port {subscriber_port}")
    
    # Make RPC calls to Publisher
    messages_received = 0
    
    try:
        # Use concurrent.futures to call async RPC from sync context
        with ThreadPoolExecutor(max_workers=1) as executor:
            def call_rpc():
                # Create an async loop in the thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                
                async def do_rpc_calls():
                    nonlocal messages_received
                    client = SomeIPClient("127.0.0.1", 31000)
                    
                    for i in range(10):
                        try:
                            # Call simple_add(i, i+1)
                            request = SOMEIPHeader(
                                service_id=0x0800,
                                method_id=0x0001,
                                instance_id=0x0001,
                                request_id=(1000 + i)
                            )
                            request.payload = struct.pack("!II", i, i+1)
                            
                            response = await client.send_method_call(request)
                            if response and len(response.payload) == 4:
                                result = struct.unpack("!I", response.payload)[0]
                                logger.info(f"RPC call {i}: simple_add({i}, {i+1}) = {result}")
                                messages_received += 1
                            
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.error(f"RPC call failed: {e}")
                    
                    await client.close()
                
                return new_loop.run_until_complete(do_rpc_calls())
            
            await loop.run_in_executor(executor, call_rpc)
    
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await bus.stop()
        
        if messages_received > 0:
            logger.info(f"✅ Subscriber {subscriber_id} received {messages_received} responses")
        else:
            logger.warning(f"⚠️  Subscriber {subscriber_id} WARNING: Received 0 responses")
        
        logger.info(f"Subscriber {subscriber_id} stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
