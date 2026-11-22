"""SOME/IP Calculator RPC — 共享配置。

Server 和 Client 两个独立进程通过同一份配置找到彼此：
  - Server 通过 SD Offer 通告 service_id=0x4444，包含 3 个 method
  - Client 通过 SD Find 发现服务，发起 REQUEST 并等待 RESPONSE
"""

from __future__ import annotations

LOCAL_IP = "127.0.0.1"
SERVER_PORT = 30950
CLIENT_PORT = 30960

# SOME/IP 服务标识
SERVICE_ID = 0x4444
INSTANCE_ID = 0x0001
MAJOR_VERSION = 1
MINOR_VERSION = 0

# Method ID 映射表（Server 和 Client 必须一致）
METHODS = {
    "add": 0x0001,
    "subtract": 0x0002,
    "multiply": 0x0003,
}
