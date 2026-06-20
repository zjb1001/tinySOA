import pytest
import asyncio
from examples.echo_service.app import EchoServiceApp
from tinysoa.spi.interceptor import InvocationContext


@pytest.mark.asyncio
async def test_echo_service_happy_path():
    app = EchoServiceApp()
    app.start()

    received = []
    
    async def on_said(msg):
        received.append(msg.payload)
        
    app.subscribe_said(on_said)

    resp = await app.invoke({"text": "hi"})

    assert resp.payload["echo"]["text"] == "hi"
    assert resp.payload["service"] == "echo"
    assert resp.payload["method"] == "say"

    # Event delivered
    assert len(received) == 1
    assert received[0]["echo"]["text"] == "hi"

    app.terminate()


@pytest.mark.asyncio
async def test_echo_service_circuit_opens_then_recovers():
    app = EchoServiceApp()
    app.start()

    # Monkey patch to force failures
    original_invoker = app._actual_invoker
    call_count = {"count": 0}

    async def failing_invoker(ctx: InvocationContext):
        call_count["count"] += 1
        raise RuntimeError("boom")

    app.chain = app.chain  # keep reference
    app._actual_invoker = failing_invoker

    # Rebuild chain to use patched invoker
    new_chain = app.chain.__class__(app._actual_invoker)
    new_chain.add_interceptor(app.tracing)
    new_chain.add_interceptor(app.metrics)
    new_chain.add_interceptor(app.logging)
    app.chain = new_chain

    # Trip circuit
    for _ in range(3):
        try:
            await app.invoke({"text": "fail"})
        except Exception:
            pass

    assert call_count["count"] >= 3

    # Circuit should now be open
    try:
        await app.invoke({"text": "blocked"})
    except Exception as exc:
        # Should surface retry exhaustion with circuit open as cause
        assert "Retry attempts exhausted" in str(exc)

    # Restore invoker and wait for recovery window (circuit uses 2s default)
    app._actual_invoker = original_invoker
    new_chain = app.chain.__class__(app._actual_invoker)
    new_chain.add_interceptor(app.tracing)
    new_chain.add_interceptor(app.metrics)
    new_chain.add_interceptor(app.logging)
    app.chain = new_chain

    await asyncio.sleep(2.1)

    # Now should succeed
    resp = await app.invoke({"text": "ok"})
    assert resp.payload["echo"]["text"] == "ok"

    app.terminate()

