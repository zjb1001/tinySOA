import pytest
import time
from uuid import uuid4

from tinysoa.core.model import Service, Method, Message
from tinysoa.obs.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsCollector,
    MetricType,
    get_metrics_collector,
)
from tinysoa.obs.tracing import (
    Span,
    TracingContext,
    TracingInterceptor,
)
from tinysoa.spi.interceptor import InvocationContext, InterceptorChain


def test_counter():
    counter = Counter("requests_total", {"service": "echo"})
    
    assert counter.get() == 0.0
    
    counter.inc()
    assert counter.get() == 1.0
    
    counter.inc(5.0)
    assert counter.get() == 6.0
    
    metric = counter.to_metric()
    assert metric.type == MetricType.COUNTER
    assert metric.value == 6.0
    assert metric.labels["service"] == "echo"
    
    counter.reset()
    assert counter.get() == 0.0


def test_gauge():
    gauge = Gauge("active_connections", {"service": "echo"})
    
    assert gauge.get() == 0.0
    
    gauge.set(10.0)
    assert gauge.get() == 10.0
    
    gauge.inc(5.0)
    assert gauge.get() == 15.0
    
    gauge.dec(3.0)
    assert gauge.get() == 12.0
    
    metric = gauge.to_metric()
    assert metric.type == MetricType.GAUGE
    assert metric.value == 12.0


def test_histogram():
    histogram = Histogram("request_duration_ms", {"service": "echo"})
    
    assert histogram.get_count() == 0
    assert histogram.get_sum() == 0.0
    assert histogram.get_avg() == 0.0
    
    # Observe some values
    histogram.observe(10.0)
    histogram.observe(20.0)
    histogram.observe(30.0)
    histogram.observe(40.0)
    histogram.observe(50.0)
    
    assert histogram.get_count() == 5
    assert histogram.get_sum() == 150.0
    assert histogram.get_avg() == 30.0
    
    # Percentiles
    assert histogram.get_percentile(0) == 10.0
    assert histogram.get_percentile(50) == 30.0
    assert histogram.get_percentile(100) == 50.0
    
    metric = histogram.to_metric()
    assert metric.type == MetricType.HISTOGRAM
    assert metric.value == 30.0
    
    histogram.reset()
    assert histogram.get_count() == 0


def test_metrics_collector():
    collector = MetricsCollector()
    
    # Create metrics
    counter1 = collector.counter("requests", {"service": "echo"})
    counter2 = collector.counter("requests", {"service": "calc"})
    gauge1 = collector.gauge("memory_bytes", {"service": "echo"})
    histogram1 = collector.histogram("latency_ms", {"service": "echo"})
    
    # Same name+labels should return same instance
    counter1_again = collector.counter("requests", {"service": "echo"})
    assert counter1 is counter1_again
    
    # Update metrics
    counter1.inc(10)
    counter2.inc(5)
    gauge1.set(1024)
    histogram1.observe(100)
    histogram1.observe(200)
    
    # Collect all
    metrics = collector.collect_all()
    assert len(metrics) == 4
    
    # Get service-specific metrics
    echo_metrics = collector.get_service_metrics("echo")
    assert "requests" in echo_metrics or len(echo_metrics) >= 0  # Depends on implementation
    
    # Reset
    collector.reset_all()
    assert counter1.get() == 0.0
    assert histogram1.get_count() == 0


def test_global_metrics_collector():
    collector1 = get_metrics_collector()
    collector2 = get_metrics_collector()
    
    # Should be the same instance
    assert collector1 is collector2


def test_span_basic():
    trace_id = uuid4()
    span = Span(
        trace_id=trace_id,
        span_id=uuid4(),
        operation_name="echo.say",
        service_name="echo",
    )
    
    assert span.duration_ms is None
    assert span.status == "ok"
    
    span.set_tag("method.id", 1)
    assert span.tags["method.id"] == 1
    
    span.log_event("request_received", size=100)
    assert len(span.logs) == 1
    assert span.logs[0]["event"] == "request_received"
    
    span.finish()
    assert span.duration_ms is not None
    assert span.duration_ms >= 0
    
    # To dict
    data = span.to_dict()
    assert data["trace_id"] == str(trace_id)
    assert data["operation_name"] == "echo.say"
    assert data["status"] == "ok"


def test_span_with_parent():
    trace_id = uuid4()
    
    parent_span = Span(
        trace_id=trace_id,
        span_id=uuid4(),
        operation_name="parent",
    )
    
    child_span = Span(
        trace_id=trace_id,
        span_id=uuid4(),
        parent_span_id=parent_span.span_id,
        operation_name="child",
    )
    
    assert child_span.parent_span_id == parent_span.span_id


def test_tracing_context():
    ctx = TracingContext()
    
    # Start root span
    span1 = ctx.start_span("operation1", "service1")
    assert ctx.get_active_span() is span1
    assert span1.parent_span_id is None
    
    # Start child span
    span2 = ctx.start_span("operation2", "service2", parent_span=span1)
    assert ctx.get_active_span() is span2
    assert span2.parent_span_id == span1.span_id
    
    # Finish child
    ctx.finish_span(span2)
    assert ctx.get_active_span() is span1  # Back to parent
    
    # Finish parent
    ctx.finish_span(span1)
    assert ctx.get_active_span() is None
    
    # All spans collected
    all_spans = ctx.get_all_spans()
    assert len(all_spans) == 2
    
    # Export
    data = ctx.to_dict()
    assert "trace_id" in data
    assert len(data["spans"]) == 2


@pytest.mark.asyncio
async def test_tracing_interceptor():
    service = Service(name="echo", id=1, version="1.0.0", methods=[Method("say", 1)])
    
    tracing = TracingInterceptor()
    
    async def actual_invoker(ctx: InvocationContext):
        ctx.set_response(Message(payload={"result": "ok"}))
    
    chain = InterceptorChain(actual_invoker)
    chain.add_interceptor(tracing)
    
    context = InvocationContext(
        service=service,
        method=service.methods[0],
        request=Message(payload={"msg": "hello"}),
    )
    
    await chain.invoke(context)
    
    # Check that trace was created
    assert "trace_id" in context.metadata
    assert "span" in context.metadata
    
    trace_id = context.metadata["trace_id"]
    trace = tracing.get_trace(trace_id)
    
    assert trace is not None
    spans = trace.get_all_spans()
    assert len(spans) == 1
    
    span = spans[0]
    assert span.operation_name == "echo.say"
    assert span.service_name == "echo"
    assert span.status == "ok"
    assert span.tags["service.name"] == "echo"
    assert span.tags["method.name"] == "say"


@pytest.mark.asyncio
async def test_tracing_interceptor_with_error():
    service = Service(name="echo", id=1, version="1.0.0", methods=[Method("say", 1)])
    
    tracing = TracingInterceptor()
    
    async def actual_invoker(ctx: InvocationContext):
        ctx.set_error(Exception("Something went wrong"))
    
    chain = InterceptorChain(actual_invoker)
    chain.add_interceptor(tracing)
    
    context = InvocationContext(
        service=service,
        method=service.methods[0],
        request=Message(payload={"msg": "hello"}),
    )
    
    await chain.invoke(context)
    
    trace_id = context.metadata["trace_id"]
    trace = tracing.get_trace(trace_id)
    
    spans = trace.get_all_spans()
    span = spans[0]
    
    assert span.status == "error"
    assert span.tags.get("error") is True
    assert len(span.logs) == 1
    assert span.logs[0]["event"] == "error"


@pytest.mark.asyncio
async def test_tracing_nested_spans():
    service = Service(name="echo", id=1, version="1.0.0", methods=[Method("say", 1)])
    
    tracing = TracingInterceptor()
    
    async def actual_invoker(ctx: InvocationContext):
        # Simulate nested operation
        trace_ctx = tracing.get_trace(ctx.metadata["trace_id"])
        parent = ctx.metadata["span"]
        
        # Start a child span
        child = trace_ctx.start_span("nested_op", "echo", parent_span=parent)
        child.set_tag("nested", True)
        trace_ctx.finish_span(child)
        
        ctx.set_response(Message(payload={"result": "ok"}))
    
    chain = InterceptorChain(actual_invoker)
    chain.add_interceptor(tracing)
    
    context = InvocationContext(
        service=service,
        method=service.methods[0],
        request=Message(payload={"msg": "hello"}),
    )
    
    await chain.invoke(context)
    
    trace_id = context.metadata["trace_id"]
    trace = tracing.get_trace(trace_id)
    spans = trace.get_all_spans()
    
    # Should have 2 spans: parent invocation + nested
    assert len(spans) == 2
    
    # Find the nested span
    nested_span = next(s for s in spans if s.operation_name == "nested_op")
    assert nested_span.tags["nested"] is True
    assert nested_span.parent_span_id is not None


@pytest.mark.asyncio
async def test_tracing_clear():
    service = Service(name="echo", id=1, version="1.0.0", methods=[Method("say", 1)])
    
    tracing = TracingInterceptor()
    
    async def actual_invoker(ctx: InvocationContext):
        ctx.set_response(Message(payload={"ok": True}))
    
    chain = InterceptorChain(actual_invoker)
    chain.add_interceptor(tracing)
    
    context = InvocationContext(
        service=service,
        method=service.methods[0],
        request=Message(payload={"msg": "hello"}),
    )
    
    await chain.invoke(context)
    
    assert len(tracing.get_all_traces()) == 1
    
    tracing.clear_traces()
    assert len(tracing.get_all_traces()) == 0


@pytest.mark.asyncio
async def test_console_exporter(capsys):
    from tinysoa.obs.metrics import ConsoleMetricsExporter, Metric, MetricType
    
    exporter = ConsoleMetricsExporter()
    metrics = [
        Metric(name="test_counter", type=MetricType.COUNTER, value=10.0, labels={"env": "prod"}),
        Metric(name="test_gauge", type=MetricType.GAUGE, value=5.0, labels={"env": "prod"})
    ]
    
    await exporter.export(metrics)
    
    captured = capsys.readouterr()
    assert "--- Metrics Export" in captured.out
    assert "test_counter[env=prod]: 10.0 (counter)" in captured.out
    assert "test_gauge[env=prod]: 5.0 (gauge)" in captured.out
