"""Topology matrix tests for the local pub/sub scenarios."""

from __future__ import annotations

from examples.local_pubsub_topologies.app import (
    run_many_to_one,
    run_one_to_many,
    run_one_to_one,
)


async def test_one_to_one_delivers_every_message() -> None:
    result = await run_one_to_one(count=4)
    assert result.published == 4
    assert result.delivered == {"sub-1": 4}


async def test_one_to_many_delivers_to_every_subscriber() -> None:
    result = await run_one_to_many(subscribers=3, count=5)
    assert result.published == 5
    assert result.delivered == {"sub-1": 5, "sub-2": 5, "sub-3": 5}


async def test_many_to_one_collects_all_sources() -> None:
    result = await run_many_to_one(publishers=3, count=2)
    assert result.published == 6
    assert result.delivered == {"sub-1": 6}
    assert result.sources == ("pub-1", "pub-2", "pub-3")
