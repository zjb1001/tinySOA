# SOME/IP Multi-Publisher, Single Subscriber Example

This example demonstrates how multiple SOME/IP service publishers communicate with a single centralized subscriber.

## Architecture

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Temperature    │      │   Humidity      │      │   Pressure      │
│   Publisher 1   │      │   Publisher 2   │      │   Publisher 3   │
│                 │      │                 │      │                 │
│ Service 0x1001  │      │ Service 0x1002  │      │ Service 0x1003  │
│ Instance 0x0001 │      │ Instance 0x0001 │      │ Instance 0x0001 │
└────────┬────────┘      └────────┬────────┘      └────────┬────────┘
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │                            │
                    │   SOME/IP Network (SD)    │
                    │   224.224.224.245:30490   │
                    │                            │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  Centralized Subscriber    │
                    │  (Single tinySOA Bus)      │
                    │                            │
                    │  Listens to 3 topics:     │
                    │  - sensor.temperature     │
                    │  - sensor.humidity        │
                    │  - sensor.pressure        │
                    └────────────────────────────┘
```

## Components

### 1. Publisher 1: Temperature Sensor
- **Service ID**: 0x1001
- **Instance ID**: 0x0001
- **EventGroup ID**: 0x0001
- **Topic**: `sensor.temperature`
- **Payload**: `{"value": float, "unit": "celsius"}`

### 2. Publisher 2: Humidity Sensor
- **Service ID**: 0x1002
- **Instance ID**: 0x0001
- **EventGroup ID**: 0x0001
- **Topic**: `sensor.humidity`
- **Payload**: `{"value": float, "unit": "percent"}`

### 3. Publisher 3: Pressure Sensor
- **Service ID**: 0x1003
- **Instance ID**: 0x0001
- **EventGroup ID**: 0x0001
- **Topic**: `sensor.pressure`
- **Payload**: `{"value": float, "unit": "hPa"}`

### 4. Subscriber: Data Aggregator
- Listens on all three topics
- Receives data from all publishers simultaneously
- Aggregates and logs sensor readings

## Prerequisites

`tinysoa` and `someip` (pysomeip) resolve from source — set `PYTHONPATH` to both
source roots before running any script:

```bash
export PYTHONPATH=$REPO/src:$REPO/tinySOA/src
```

Every script accepts `--log-level {DEBUG,INFO,WARNING,ERROR}` and `--count N`
(bounded run, 0 = forever). Exit code 0 on clean shutdown.

## Usage

### Terminal 1: Start Publisher 1 (Temperature)
```bash
python publisher1_temperature.py
```

### Terminal 2: Start Publisher 2 (Humidity)
```bash
python publisher2_humidity.py
```

### Terminal 3: Start Publisher 3 (Pressure)
```bash
python publisher3_pressure.py
```

### Terminal 4: Start Subscriber (Aggregator)
```bash
python subscriber_aggregator.py
```

## Running All at Once

```bash
# Terminal setup (run these in separate terminals or in background)
python publisher1_temperature.py &
python publisher2_humidity.py &
python publisher3_pressure.py &
python subscriber_aggregator.py
```

## Expected Output

### Publishers (each in its own terminal):
```
2025-01-15 10:30:45.123 | Temperature Publisher | Temperature=22.5°C
2025-01-15 10:30:46.234 | Temperature Publisher | Temperature=22.6°C
2025-01-15 10:30:47.345 | Temperature Publisher | Temperature=22.5°C
```

### Subscriber (aggregator):
```
2025-01-15 10:30:45.500 | SENSOR DATA AGGREGATOR |
  ✓ Temperature: 22.5°C (from Service 0x1001)
  ✓ Humidity: 65%      (from Service 0x1002)
  ✓ Pressure: 1013.25 hPa (from Service 0x1003)

2025-01-15 10:30:46.600 | SENSOR DATA AGGREGATOR |
  ✓ Temperature: 22.6°C (from Service 0x1001)
  ✓ Humidity: 64%      (from Service 0x1002)
  ✓ Pressure: 1013.20 hPa (from Service 0x1003)
```

## Key Concepts Demonstrated

1. **Multiple Publishers**: Each runs on its own SOME/IP service
2. **Service Discovery**: Subscriber automatically discovers all publishers
3. **Concurrent Publishing**: All publishers can publish simultaneously
4. **Message Aggregation**: Subscriber collects data from all sources
5. **Protocol Isolation**: Each service is independent via SOME/IP
6. **Real Network Protocol**: Uses actual pysomeip/SOME/IP stack

## Learning Outcomes

- How to create multiple SOME/IP services
- How to subscribe to multiple topics
- Service discovery and dynamic discovery
- Message serialization/deserialization
- Async/await patterns
- Error handling in distributed systems

## Configuration

You can modify the local IP address in the scripts:
```python
LOCAL_IP = "127.0.0.1"  # Change to your network interface
```

## Requirements

- Python 3.10+
- pysomeip
- tinySOA

## Notes

- Publishers must be started before the subscriber for immediate discovery
- Subscriber will wait for publishers to appear via SD
- All components can run on the same machine or different machines
- Change IP addresses for cross-machine deployment
