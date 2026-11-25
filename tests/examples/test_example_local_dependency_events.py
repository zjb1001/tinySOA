"""Event-order tests for the local dependency events example."""

from __future__ import annotations

from examples.local_dependency_events.app import (
    SVC_DASHBOARD_ID,
    SVC_DATABASE_ID,
    SVC_REMOTE_TELEMETRY_ID,
    SVC_SENSOR_GATEWAY_ID,
    DependencyEventsDemo,
    main,
)
from tinysoa.runtime import InternalEventType


async def test_demo_orders_discovery_before_dashboard_ready() -> None:
    demo = DependencyEventsDemo()

    exit_code = await demo.run(duration=0, discovery_delay=0, wait_timeout=0.5)

    assert exit_code == 0
    ready = [
        event.source_service_id
        for event in demo.events
        if event.event_type is InternalEventType.SERVICE_READY
    ]
    assert ready == [
        SVC_DATABASE_ID,
        SVC_SENSOR_GATEWAY_ID,
        SVC_DASHBOARD_ID,
    ]

    discovery_index = next(
        index
        for index, event in enumerate(demo.events)
        if event.event_type is InternalEventType.INSTANCE_DISCOVERED
        and event.related_service_id == SVC_REMOTE_TELEMETRY_ID
    )
    dashboard_index = next(
        index
        for index, event in enumerate(demo.events)
        if event.event_type is InternalEventType.SERVICE_READY
        and event.source_service_id == SVC_DASHBOARD_ID
    )
    assert discovery_index < dashboard_index

    lost = {
        (event.source_service_id, event.related_service_id)
        for event in demo.events
        if event.event_type is InternalEventType.DEPENDENCY_LOST
    }
    assert (SVC_DASHBOARD_ID, SVC_SENSOR_GATEWAY_ID) in lost
    assert (SVC_SENSOR_GATEWAY_ID, SVC_DATABASE_ID) in lost


def test_dry_run_returns_zero() -> None:
    assert main(["--dry-run", "--log-level", "ERROR"]) == 0
