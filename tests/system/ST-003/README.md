# ST-003: Late Publisher Discovery (Sub First) - Dual Terminal

This test demonstrates a non-centralized SOME/IP Service Discovery scenario where the subscriber joins first and waits for a late publisher to appear. Each terminal represents an independent ECU maintaining its own local service table.

## Prerequisites

Activate the virtual environment in each terminal:
```bash
cd /home/page/GitPlayground/pysomeip
source .venv/bin/activate
```

## Running the Test

### Terminal 1: Start Subscriber
```bash
cd tinySOA/tests/system_tests/ST-003
python subscriber.py
```

Expected output:
```
Subscriber bus started (BEFORE publisher)
Subscribed (waiting for publisher to appear)
[Sub #0] Waiting 5.00s before SD find_subscribe for test.topic.a
```

The subscriber will send SD Find messages on the multicast address (224.224.224.245:30490) looking for service 0x1234:0x0001.

### Terminal 2: Start Publisher (after 2-3 seconds)
```bash
cd tinySOA/tests/system_tests/ST-003
python publisher.py
```

Expected output:
```
Publisher bus started (AFTER subscriber)
SOME/IP Service 0x1234:0x1 started on 127.0.0.22:33020
Test publish sent
```

The publisher will send SD Offer messages on the multicast address announcing service 0x1234:0x0001.

## Key SD Protocol Steps Visible in Logs

1. **Subscriber**: Sends SERVICE_FIND (around T+5s after startup)
2. **Publisher**: Receives FIND and responds with SERVICE_OFFERED
3. **Subscriber**: Receives OFFER, sends SUBSCRIBE_EVENTGROUP unicast to publisher
4. **Publisher**: Receives SUBSCRIBE, sends SUBSCRIBE_ACK
5. **Publisher**: Sends initial notification with test payload
6. **Subscriber**: Receives notification, verifies payload, test passes

## Non-Centralized Design Verification

- **No central registry**: Subscriber and Publisher communicate directly via SOME/IP SD multicast
- **Independent service tables**: Each ECU/process maintains its own view of discovered services
- **Late discovery**: Publisher can appear after subscriber; SD protocol handles this gracefully
- **Separate processes**: Each runs in isolation on different IP addresses (127.0.0.21 vs 127.0.0.22) and ports
