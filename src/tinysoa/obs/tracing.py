from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
from threading import Lock

from tinysoa.spi.interceptor import Interceptor, InvocationContext, Invoker


@dataclass
class Span:
    """Represents a span in distributed tracing."""
    
    trace_id: UUID
    span_id: UUID
    parent_span_id: Optional[UUID] = None
    operation_name: str = ""
    service_name: str = ""
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ok"  # ok, error
    
    def finish(self, status: str = "ok") -> None:
        """Mark the span as finished."""
        self.end_time = datetime.now(timezone.utc)
        self.status = status
    
    @property
    def duration_ms(self) -> Optional[float]:
        """Get span duration in milliseconds."""
        if self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() * 1000
        return None
    
    def set_tag(self, key: str, value: Any) -> None:
        """Set a tag on the span."""
        self.tags[key] = value
    
    def log_event(self, event: str, **kwargs) -> None:
        """Log an event in the span."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc),
            "event": event,
            **kwargs,
        }
        self.logs.append(log_entry)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary for export."""
        return {
            "trace_id": str(self.trace_id),
            "span_id": str(self.span_id),
            "parent_span_id": str(self.parent_span_id) if self.parent_span_id else None,
            "operation_name": self.operation_name,
            "service_name": self.service_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "tags": self.tags,
            "logs": [
                {**log, "timestamp": log["timestamp"].isoformat()}
                for log in self.logs
            ],
            "status": self.status,
        }


class TracingContext:
    """Manages tracing context and span hierarchy."""
    
    def __init__(self, trace_id: Optional[UUID] = None):
        self.trace_id = trace_id or uuid4()
        self._spans: List[Span] = []
        self._active_span: Optional[Span] = None
    
    def start_span(
        self,
        operation_name: str,
        service_name: str = "",
        parent_span: Optional[Span] = None,
    ) -> Span:
        """Start a new span."""
        parent_span_id = parent_span.span_id if parent_span else None
        
        span = Span(
            trace_id=self.trace_id,
            span_id=uuid4(),
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            service_name=service_name,
        )
        
        self._spans.append(span)
        self._active_span = span
        
        return span
    
    def finish_span(self, span: Span, status: str = "ok") -> None:
        """Finish a span."""
        span.finish(status)
        
        # Set active span to parent if exists
        if span.parent_span_id:
            for s in self._spans:
                if s.span_id == span.parent_span_id:
                    self._active_span = s
                    break
        else:
            self._active_span = None
    
    def get_active_span(self) -> Optional[Span]:
        """Get the currently active span."""
        return self._active_span
    
    def get_all_spans(self) -> List[Span]:
        """Get all spans in this trace."""
        return list(self._spans)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export trace to dictionary."""
        return {
            "trace_id": str(self.trace_id),
            "spans": [span.to_dict() for span in self.get_all_spans()],
        }


class TracingInterceptor(Interceptor):
    """Interceptor that adds distributed tracing to service calls."""
    
    def __init__(self, priority: int = 15):
        self._priority = priority
        self.traces: Dict[UUID, TracingContext] = {}
        self._lock = Lock()
    
    @property
    def priority(self) -> int:
        return self._priority
    
    async def intercept(self, context: InvocationContext, next_invoker: Invoker) -> None:
        """Intercept and add tracing."""
        # Get or create tracing context
        trace_id = context.metadata.get("trace_id")
        if trace_id and isinstance(trace_id, UUID):
            tracing_ctx = self.traces.get(trace_id)
            if not tracing_ctx:
                tracing_ctx = TracingContext(trace_id=trace_id)
                self.traces[trace_id] = tracing_ctx
        else:
            tracing_ctx = TracingContext()
            context.metadata["trace_id"] = tracing_ctx.trace_id
            self.traces[tracing_ctx.trace_id] = tracing_ctx
        
        # Get parent span if exists
        parent_span = tracing_ctx.get_active_span()
        
        # Start a new span for this invocation
        operation_name = f"{context.service.name}.{context.method.name}"
        span = tracing_ctx.start_span(
            operation_name=operation_name,
            service_name=context.service.name,
            parent_span=parent_span,
        )
        
        # Add tags
        span.set_tag("service.name", context.service.name)
        span.set_tag("service.version", context.service.version)
        span.set_tag("method.name", context.method.name)
        span.set_tag("method.id", context.method.id)
        
        # Store span in context metadata
        context.metadata["span"] = span
        
        try:
            # Call next in chain
            await next_invoker(context)
            
            # Check for errors
            if context.error:
                span.set_tag("error", True)
                span.log_event("error", message=str(context.error))
                tracing_ctx.finish_span(span, status="error")
            else:
                tracing_ctx.finish_span(span, status="ok")
        except Exception as e:
            span.set_tag("error", True)
            span.log_event("error", message=str(e))
            tracing_ctx.finish_span(span, status="error")
            raise
    
    def get_trace(self, trace_id: UUID) -> Optional[TracingContext]:
        """Get a trace by ID."""
        return self.traces.get(trace_id)
    
    def get_all_traces(self) -> List[TracingContext]:
        """Get all traces."""
        return list(self.traces.values())
    
    def clear_traces(self) -> None:
        """Clear all stored traces."""
        with self._lock:
            self.traces.clear()
