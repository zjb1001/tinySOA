import pytest
from unittest.mock import Mock

from tinysoa.core.model import Service, Method, Message
from tinysoa.core.errors import DuplicateError, StateError
from tinysoa.spi.interceptor import (
    Interceptor,
    InterceptorChain,
    InvocationContext,
    LoggingInterceptor,
    MetricsInterceptor,
    AuthInterceptor,
)
from tinysoa.obs.metrics import MetricsCollector
from tinysoa.spi.plugin import (
    Plugin,
    PluginManager,
    PluginLifecycle,
    DummyPlugin,
    CachePlugin,
)


@pytest.fixture
def sample_service():
    return Service(name="echo", id=1, version="1.0.0", methods=[Method("say", 1)])


@pytest.fixture
def sample_context(sample_service):
    return InvocationContext(
        service=sample_service,
        method=sample_service.methods[0],
        request=Message(payload={"msg": "hello"}),
    )


def test_invocation_context_response(sample_context):
    assert sample_context.response is None
    assert sample_context.error is None
    
    resp = Message(payload={"result": "ok"})
    sample_context.set_response(resp)
    
    assert sample_context.response is resp
    assert sample_context.end_time is not None
    assert sample_context.duration_ms is not None
    assert sample_context.duration_ms >= 0


def test_invocation_context_error(sample_context):
    err = Exception("test error")
    sample_context.set_error(err)
    
    assert sample_context.error is err
    assert sample_context.end_time is not None
    assert sample_context.duration_ms is not None


@pytest.mark.asyncio
async def test_interceptor_chain_no_interceptors(sample_context):
    called = []
    
    async def actual_invoker(ctx):
        called.append("actual")
        ctx.set_response(Message(payload={"echo": ctx.request.payload}))
    
    chain = InterceptorChain(actual_invoker)
    await chain.invoke(sample_context)
    
    assert called == ["actual"]
    assert sample_context.response is not None


@pytest.mark.asyncio
async def test_interceptor_chain_with_interceptors(sample_context):
    execution_order = []
    
    class TestInterceptor(Interceptor):
        def __init__(self, name, priority):
            self.name = name
            self._priority = priority
        
        @property
        def priority(self):
            return self._priority
        
        async def intercept(self, context, next_invoker):
            execution_order.append(f"{self.name}-before")
            await next_invoker(context)
            execution_order.append(f"{self.name}-after")
    
    async def actual_invoker(ctx):
        execution_order.append("actual")
        ctx.set_response(Message(payload={"ok": True}))
    
    chain = InterceptorChain(actual_invoker)
    
    # Add in reverse priority order to test sorting
    chain.add_interceptor(TestInterceptor("B", 20))
    chain.add_interceptor(TestInterceptor("A", 10))
    chain.add_interceptor(TestInterceptor("C", 30))
    
    await chain.invoke(sample_context)
    
    # Should execute in priority order
    assert execution_order == [
        "A-before", "B-before", "C-before",
        "actual",
        "C-after", "B-after", "A-after"
    ]


@pytest.mark.asyncio
async def test_interceptor_short_circuit(sample_context):
    execution_order = []
    
    class ShortCircuitInterceptor(Interceptor):
        @property
        def priority(self):
            return 10
        
        async def intercept(self, context, next_invoker):
            # Don't call next_invoker, short-circuit
            context.set_response(Message(payload={"short": "circuit"}))
    
    async def actual_invoker(ctx):
        execution_order.append("actual")  # Should not be called
    
    chain = InterceptorChain(actual_invoker)
    chain.add_interceptor(ShortCircuitInterceptor())
    await chain.invoke(sample_context)
    
    assert execution_order == []
    assert sample_context.response.payload["short"] == "circuit"


@pytest.mark.asyncio
async def test_logging_interceptor(sample_context):
    logger = LoggingInterceptor()
    
    async def actual_invoker(ctx):
        ctx.set_response(Message(payload={"ok": True}))
    
    chain = InterceptorChain(actual_invoker)
    chain.add_interceptor(logger)
    await chain.invoke(sample_context)
    
    assert len(logger.logs) == 2
    assert "[LOG] Before:" in logger.logs[0]
    assert "[LOG] After:" in logger.logs[1]


@pytest.mark.asyncio
async def test_metrics_interceptor(sample_context):
    collector = MetricsCollector()
    metrics = MetricsInterceptor(collector=collector)
    
    async def actual_invoker(ctx):
        ctx.set_response(Message(payload={"ok": True}))
    
    chain = InterceptorChain(actual_invoker)
    chain.add_interceptor(metrics)
    
    await chain.invoke(sample_context)
    
    labels = {"service": "echo", "method": "say"}
    
    # Check metrics
    assert collector.counter("rpc_calls_total", labels).get() == 1
    assert collector.counter("rpc_errors_total", labels).get() == 0
    assert collector.histogram("rpc_duration_ms", labels).get_count() == 1
    
    # Second call with error
    ctx2 = InvocationContext(
        service=sample_context.service,
        method=sample_context.method,
        request=Message(payload={"msg": "hi"}),
    )
    
    async def error_invoker(ctx):
        ctx.set_error(Exception("fail"))
    
    chain2 = InterceptorChain(error_invoker)
    chain2.add_interceptor(metrics)
    await chain2.invoke(ctx2)
    
    assert collector.counter("rpc_calls_total", labels).get() == 2
    assert collector.counter("rpc_errors_total", labels).get() == 1


@pytest.mark.asyncio
async def test_auth_interceptor_success(sample_context):
    sample_context.request.headers["Authorization"] = "secret-token"
    
    auth = AuthInterceptor(required_token="secret-token")
    
    async def actual_invoker(ctx):
        ctx.set_response(Message(payload={"ok": True}))
    
    chain = InterceptorChain(actual_invoker)
    chain.add_interceptor(auth)
    await chain.invoke(sample_context)
    
    assert sample_context.error is None
    assert sample_context.response is not None


@pytest.mark.asyncio
async def test_auth_interceptor_failure(sample_context):
    sample_context.request.headers["Authorization"] = "wrong-token"
    
    auth = AuthInterceptor(required_token="secret-token")
    
    async def actual_invoker(ctx):
        ctx.set_response(Message(payload={"ok": True}))
    
    chain = InterceptorChain(actual_invoker)
    chain.add_interceptor(auth)
    await chain.invoke(sample_context)
    
    assert sample_context.error is not None
    assert "Unauthorized" in str(sample_context.error)
    assert sample_context.response is None


def test_plugin_lifecycle():
    plugin = DummyPlugin()
    
    assert plugin.state == PluginLifecycle.REGISTERED
    assert not plugin.initialized
    
    plugin.initialize()
    assert plugin.state == PluginLifecycle.INITIALIZED
    assert plugin.initialized
    
    plugin.start()
    assert plugin.state == PluginLifecycle.STARTED
    assert plugin.started
    
    plugin.stop()
    assert plugin.state == PluginLifecycle.STOPPED
    assert plugin.stopped
    
    plugin.terminate()
    assert plugin.state == PluginLifecycle.TERMINATED
    assert plugin.terminated


def test_plugin_lifecycle_constraints():
    plugin = DummyPlugin()
    
    # Can't start before initialize
    with pytest.raises(StateError):
        plugin.start()
    
    plugin.initialize()
    
    # Can't stop before start
    with pytest.raises(StateError):
        plugin.stop()
    
    plugin.start()
    plugin.stop()
    
    # Can't initialize again
    with pytest.raises(StateError):
        plugin.initialize()


def test_plugin_manager():
    manager = PluginManager()
    
    plugin1 = DummyPlugin("plugin1")
    plugin2 = DummyPlugin("plugin2")
    
    manager.register(plugin1)
    manager.register(plugin2)
    
    assert len(manager.list_plugins()) == 2
    assert manager.get("plugin1") is plugin1
    assert manager.get("plugin2") is plugin2
    
    with pytest.raises(DuplicateError):
        manager.register(DummyPlugin("plugin1"))


def test_plugin_manager_lifecycle():
    manager = PluginManager()
    
    plugin1 = DummyPlugin("p1")
    plugin2 = DummyPlugin("p2")
    
    manager.register(plugin1)
    manager.register(plugin2)
    
    manager.initialize_all()
    assert plugin1.initialized and plugin2.initialized
    
    manager.start_all()
    assert plugin1.started and plugin2.started
    
    manager.stop_all()
    assert plugin1.stopped and plugin2.stopped
    
    manager.terminate_all()
    assert plugin1.terminated and plugin2.terminated


def test_cache_plugin():
    cache = CachePlugin()
    cache.configure({"max_size": 2})
    cache.initialize()
    cache.start()
    
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    
    assert cache.get("key1") == "value1"
    assert cache.get("key2") == "value2"
    
    # Should evict first item when max size exceeded
    cache.set("key3", "value3")
    assert cache.get("key1") is None  # evicted
    assert cache.get("key3") == "value3"
    
    cache.clear()
    assert cache.get("key2") is None
    assert cache.get("key3") is None
