"""SOME/IP Calculator RPC — 共享配置。

Server 和 Client 两个独立进程通过同一份配置找到彼此：
  - Server 通过 SD Offer 通告 service_id=0x4444，包含 3 个 method
  - Client 通过 SD Find 发现服务，发起 REQUEST 并等待 RESPONSE
"""

from __future__ import annotations

from tinysoa.eventbus import SomeIPServiceBinding

LOCAL_IP = "127.0.0.1"
SERVER_PORT = 30950
CLIENT_PORT = 30960

# SOME/IP 服务标识
SERVICE_NAME = "calculator"
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


def binding(
    *,
    local_port: int = 0,
    server_port: int = 0,
    timeout: float = 5.0,
) -> SomeIPServiceBinding:
    """Build the shared SOME/IP service binding."""
    return SomeIPServiceBinding(
        name=SERVICE_NAME,
        service_id=SERVICE_ID,
        instance_id=INSTANCE_ID,
        methods=METHODS,
        major_version=MAJOR_VERSION,
        minor_version=MINOR_VERSION,
        local_ip=LOCAL_IP,
        local_port=local_port,
        server_port=server_port,
        timeout=timeout,
    )
