"""Shared service contract for the SOME/IP Calculator RPC example.

Server and client are separate processes but use the same service identity and
method-id table, so discovery and REQUEST/RESPONSE matching stay consistent.
"""

from __future__ import annotations

from tinysoa.eventbus import SomeIPServiceBinding

LOCAL_IP = "127.0.0.1"
SERVER_PORT = 30950
CLIENT_PORT = 30960

# SOME/IP service identity.
SERVICE_NAME = "calculator"
SERVICE_ID = 0x4444
INSTANCE_ID = 0x0001
MAJOR_VERSION = 1
MINOR_VERSION = 0

# Method ID map; server and client must agree.
METHODS = {
    "add": 0x0001,
    "subtract": 0x0002,
    "multiply": 0x0003,
}


def _config(
    *,
    local_port: int = 0,
    server_port: int = 0,
    timeout: float = 5.0,
) -> SomeIPServiceBinding:
    """Build a pure configuration object; no I/O or socket binding happens."""
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


def server_config(server_port: int) -> SomeIPServiceBinding:
    """Server endpoint: advertise the calculator service."""
    return _config(server_port=server_port)


def client_config(local_port: int, timeout: float = 5.0) -> SomeIPServiceBinding:
    """Client endpoint: discover and invoke the calculator service."""
    return _config(local_port=local_port, timeout=timeout)
