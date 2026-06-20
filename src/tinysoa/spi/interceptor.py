from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Awaitable
from datetime import datetime, timezone

from tinysoa.core.model import Service, Method, Message
from tinysoa.obs.metrics import MetricsCollector, get_metrics_collector


@dataclass
class InvocationContext:
    """Context for a service invocation, passed through the interceptor chain."""
    
    service: Service
    method: Method
    request: Message
    response: Optional[Message] = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    
    def set_response(self, response: Message) -> None:
        """Set the response and mark end time."""
        self.response = response
        self.end_time = datetime.now(timezone.utc)
    
    def set_error(self, error: Exception) -> None:
        """Set an error and mark end time."""
        self.error = error
        self.end_time = datetime.now(timezone.utc)
    
    @property
    def duration_ms(self) -> Optional[float]:
        """Return duration in milliseconds if completed."""
        if self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() * 1000
        return None


Invoker = Callable[[InvocationContext], Awaitable[None]]


class Interceptor(ABC):
    """Base interceptor interface for request/response interception.
    
    Interceptors can:
    - Inspect and modify request/response
    - Short-circuit the chain by setting response/error
    - Add metadata for observability
    - Implement cross-cutting concerns (auth, logging, metrics, etc.)
    """
    
    @abstractmethod
    async def intercept(self, context: InvocationContext, next_invoker: Invoker) -> None:
        """Intercept the invocation.
        
        Args:
            context: The invocation context
            next_invoker: Call this to proceed to the next interceptor/actual invocation
        
        Implementation should call await next_invoker(context) to continue the chain,
        or set context.response/context.error to short-circuit.
        """
        raise NotImplementedError
    
    @property
    def priority(self) -> int:
        """Priority for ordering (lower value = earlier in chain). Default is 100."""
        return 100


class InterceptorChain:
    """Manages a chain of interceptors and invokes them in priority order."""
    
    def __init__(self, actual_invoker: Invoker):
        """
        Args:
            actual_invoker: The final invoker that performs the actual service call
        """
        self._interceptors: List[Interceptor] = []
        self._actual_invoker = actual_invoker
    
    def add_interceptor(self, interceptor: Interceptor) -> None:
        """Add an interceptor to the chain."""
        self._interceptors.append(interceptor)
        # Sort by priority (lower first)
        self._interceptors.sort(key=lambda i: i.priority)
    
    def remove_interceptor(self, interceptor: Interceptor) -> None:
        """Remove an interceptor from the chain."""
        if interceptor in self._interceptors:
            self._interceptors.remove(interceptor)
    
    async def invoke(self, context: InvocationContext) -> None:
        """Execute the interceptor chain."""
        if not self._interceptors:
            # No interceptors, call actual invoker directly
            await self._actual_invoker(context)
            return
        
        # Build the chain from end to beginning
        def build_chain(index: int) -> Invoker:
            if index >= len(self._interceptors):
                # End of chain, return actual invoker
                return self._actual_invoker
            
            interceptor = self._interceptors[index]
            next_invoker = build_chain(index + 1)
            
            async def invoker(ctx: InvocationContext) -> None:
                await interceptor.intercept(ctx, next_invoker)
            
            return invoker
        
        # Start the chain
        chain_head = build_chain(0)
        await chain_head(context)


# Common pre-built interceptors

class LoggingInterceptor(Interceptor):
    """Simple logging interceptor for demonstration."""
    
    def __init__(self, priority: int = 10):
        self._priority = priority
        self.logs: List[str] = []  # For testing
    
    @property
    def priority(self) -> int:
        return self._priority
    
    async def intercept(self, context: InvocationContext, next_invoker: Invoker) -> None:
        self.logs.append(f"[LOG] Before: {context.service.name}.{context.method.name}")
        await next_invoker(context)
        if context.error:
            self.logs.append(f"[LOG] Error: {context.error}")
        else:
            self.logs.append(f"[LOG] After: {context.service.name}.{context.method.name}")


class MetricsInterceptor(Interceptor):
    """Metrics collection interceptor."""
    
    def __init__(self, priority: int = 20, collector: Optional[MetricsCollector] = None):
        self._priority = priority
        self._collector = collector or get_metrics_collector()
    
    @property
    def priority(self) -> int:
        return self._priority
    
    async def intercept(self, context: InvocationContext, next_invoker: Invoker) -> None:
        service_name = context.service.name
        method_name = context.method.name
        labels = {"service": service_name, "method": method_name}
        
        # Track active calls
        active_gauge = self._collector.gauge("rpc_active_calls", labels)
        active_gauge.inc()
        
        try:
            await next_invoker(context)
        finally:
            active_gauge.dec()
            
            # Track total calls
            self._collector.counter("rpc_calls_total", labels).inc()
            
            # Track errors
            if context.error:
                self._collector.counter("rpc_errors_total", labels).inc()
            
            # Track duration
            if context.duration_ms:
                self._collector.histogram("rpc_duration_ms", labels).observe(context.duration_ms)


class AuthInterceptor(Interceptor):
    """Authentication interceptor (demo)."""
    
    def __init__(self, required_token: str, priority: int = 5):
        self._priority = priority
        self._required_token = required_token
    
    @property
    def priority(self) -> int:
        return self._priority
    
    async def intercept(self, context: InvocationContext, next_invoker: Invoker) -> None:
        token = context.request.headers.get("Authorization")
        if token != self._required_token:
            context.set_error(Exception("Unauthorized"))
            return
        
        await next_invoker(context)
