# 拦截器与插件系统设计

## 1. 拦截器模型

### 1.1 核心接口定义

- **接口定义**：
  ```python
  class Interceptor:
      async def before_request(self, ctx: Context, request: Request) -> Request:
          """
          请求前处理，可修改请求或直接返回响应（短路）
          
          :param ctx: 请求上下文 (贯穿整个链路)
          :param request: 请求对象
          :return: 修改后的请求，或抛出异常中止处理
          """
          return request

      async def after_response(self, ctx: Context, response: Response) -> Response:
          """
          响应后处理，可修改响应
          
          :param ctx: 请求上下文
          :param response: 响应对象
          :return: 修改后的响应
          """
          return response

      async def on_error(self, ctx: Context, error: Exception) -> Optional[Response]:
          """
          异常处理，可吞掉异常返回响应，或重新抛出
          
          :param ctx: 请求上下文
          :param error: 捕获的异常
          :return: 响应对象 (吞掉异常) 或 None (继续传播异常)
          """
          raise error
  ```

- **上下文 `Context`**：
  - 贯穿整个请求链路的容器。
  - 包含：`service_id`, `method_id`, `client_address`, `trace_id`, `span_id`, `deadline`, `metadata` (用户自定义字典)。
  - 线程/协程安全：基于 `contextvars` 实现，确保异步调用中的上下文隔离。
  - 可变性：拦截器可在context中存储中间结果 (如缓存结果、限流令牌)。

### 1.2 执行语义与状态转移

**客户端侧拦截器链执行顺序**：

```
请求阶段:
┌─────────────────────────────────────────────────────────┐
│ Application Layer                                       │
│ proxy.call(method_id, args)                            │
└──────────────────┬──────────────────────────────────────┘
                   │ Request 对象创建
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Interceptor: Tracing.before_request                    │
│ 创建 Span, 生成 trace_id, span_id                        │
│ Action: 在 context 中记录 trace_id                      │
└──────────────────┬──────────────────────────────────────┘
                   │ 修改后的 Request
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Interceptor: Validation.before_request                 │
│ 校验请求参数类型和范围                                    │
│ Action: 若校验失败，直接返回异常                          │
└──────────────────┬──────────────────────────────────────┘
                   │ 修改后的 Request
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Interceptor: Auth.before_request                        │
│ 检查认证令牌                                             │
│ Action: 若无权限，short-circuit 返回 403 Response      │
└──────────────────┬──────────────────────────────────────┘
                   │ 修改后的 Request
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Interceptor: RateLimit.before_request                   │
│ 检查和消费令牌桶                                         │
│ Action: 若超过限制，short-circuit 返回 429 Response    │
└──────────────────┬──────────────────────────────────────┘
                   │ 修改后的 Request
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Interceptor: Caching.before_request                     │
│ 查询缓存                                                │
│ Action: 若命中，short-circuit 返回缓存 Response        │
│        (跳过后续所有步骤)                               │
└──────────────────┬──────────────────────────────────────┘
                   │ 修改后的 Request (或 缓存 Response)
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Interceptor: Retry.before_request (外层)               │
│ 初始化重试计数器                                         │
│ Action: 记录当前重试次数 (初始0)                         │
└──────────────────┬──────────────────────────────────────┘
                   │ 进入重试循环
                   ▼
            ┌──────────────────────┐
            │ RPC Call Loop        │
            │ (可能重试多次)        │
            │                      │
            │ ServiceProxy.call()  │
            │ 发起网络请求         │
            └──────────────────────┘
                   │
              成功 │ 失败
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
    ┌─────────┐          ┌─────────┐
    │Response │        │Exception │
    └────┬────┘        └────┬────┘
         │                  │
         │ (继续)           │ (进入on_error)
         ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│ Interceptor: Retry.on_error                             │
│ 决策: 是否重试?                                          │
│ - 若是幂等方法 && 重试次数未超 && 是可重试异常           │
│   → 递增重试计数器，返回到 RPC Call Loop                │
│ - 否则 → 继续向上传播异常                                │
└──────────────────┬──────────────────────────────────────┘
                   │ (成功或不可重试的异常)
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Interceptor: Metrics.after_response / on_error          │
│ 记录调用指标                                             │
│ Action: 记录 (service_id, method_id, success, latency)  │
└──────────────────┬──────────────────────────────────────┘
                   │ Response 或 Exception
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Interceptor: Caching.after_response                     │
│ 缓存成功的响应                                           │
│ Action: 存储到本地缓存，带TTL                            │
└──────────────────┬──────────────────────────────────────┘
                   │ Response
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Interceptor: Tracing.after_response                     │
│ 完成 Span, 记录结果                                      │
│ Action: span.set_attribute('result', success)            │
│        span.end()                                       │
└──────────────────┬──────────────────────────────────────┘
                   │ Response
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Application Layer                                       │
│ 返回调用结果                                             │
└─────────────────────────────────────────────────────────┘
```

**关键特性说明**：

1. **Tracing 在最外层**: 能捕获整个请求链路，包括重试
2. **Auth/RateLimit 在 Caching 前**: 不浪费限额检查缓存命中
3. **Retry 跨越 RPC Call**: 整个网络调用都可重试
4. **Metrics 在 Retry 之后**: 记录的是最终结果 (含重试)
5. **Caching 可 Short-circuit**: 命中缓存后，跳过后续所有步骤

**Short-circuit (短路) 定义**：
- 某拦截器返回 Response 而非继续传递 Request
- 立即跳转到 after_response 阶段
- 典型场景: 认证失败 (403)、限流 (429)、缓存命中 (200)

### 1.3 服务端拦截器链

```
Request 到达 ────▶ Metrics.before_request (计时开始)
                    ▼
              Tracing.before_request (提取 trace 上下文)
                    ▼
              Auth.before_request (检查权限)
                    ▼
              RateLimit.before_request (消费令牌)
                    ▼
              Validation.before_request (校验参数)
                    ▼
              业务逻辑处理 (Service Implementation)
                    ▼
              Caching.after_response (可选缓存)
                    ▼
              Metrics.after_response (记录成功)
                    ▼
              Tracing.after_response (记录span)
                    ▼
              Response 返回
```

### 1.4 幂等性约束表

每个拦截器需声明其幂等性，以便框架决策是否可重试：

```python
class InterceptorIdempotency:
    """拦截器幂等性声明"""
    
    # Retry 拦截器：本身是幂等的，但依赖方法的幂等性标注
    RETRY = "idempotent"
    
    # Caching 拦截器：幂等 (只做读)
    CACHING = "idempotent"
    
    # Auth 拦截器：幂等 (无副作用)
    AUTH = "idempotent"
    
    # Metrics 拦截器：幂等 (无副作用，只收集数据)
    METRICS = "idempotent"
    
    # RateLimit 拦截器：非幂等 (消费令牌有副作用!)
    # 若重试，需重新消费 → 可能两次消费同一令牌
    RATE_LIMIT = "non_idempotent"
    
    # Tracing 拦截器：幂等 (生成新的 span)
    TRACING = "idempotent"
```

**使用规则**：
- 若某拦截器非幂等，不能在 Retry 外层
- Retry 必须在最外层或次外层 (Tracing 之内)

## 2. 内置拦截器（完整接口与语义）

### 2.1 日志 (Logging) 拦截器

```python
class LoggingInterceptor(Interceptor):
    """
    日志拦截器 - 结构化日志记录
    
    幂等性: 幂等 (无副作用)
    执行位置: 可在任意位置，建议靠外层 (便于捕获完整生命周期)
    """
    
    async def before_request(self, ctx: Context, request: Request) -> Request:
        # 记录请求开始
        self.logger.info(
            "RPC request started",
            extra={
                "service_id": hex(ctx.service_id),
                "method_id": hex(ctx.method_id),
                "trace_id": ctx.trace_id,
                "client": ctx.client_address,
            }
        )
        return request
    
    async def after_response(self, ctx: Context, response: Response) -> Response:
        # 记录响应成功
        self.logger.info(
            "RPC response success",
            extra={"trace_id": ctx.trace_id, "latency_ms": response.latency_ms}
        )
        return response
    
    async def on_error(self, ctx: Context, error: Exception) -> None:
        # 记录错误
        self.logger.error(
            "RPC error",
            extra={"trace_id": ctx.trace_id, "error": str(error)},
            exc_info=True
        )
        raise error
```

### 2.2 指标 (Metrics) 拦截器

```python
class MetricsInterceptor(Interceptor):
    """
    指标拦截器 - Prometheus 埋点
    
    幂等性: 幂等 (只收集数据)
    执行位置: 应在 Retry 之后，以统计最终结果
    """
    
    async def before_request(self, ctx: Context, request: Request) -> Request:
        ctx.metrics_start_time = time.time()
        return request
    
    async def after_response(self, ctx: Context, response: Response) -> Response:
        latency_ms = (time.time() - ctx.metrics_start_time) * 1000
        
        # 记录到 Prometheus
        self.request_counter.labels(
            service_id=hex(ctx.service_id),
            method_id=hex(ctx.method_id),
            result="success"
        ).inc()
        
        self.latency_histogram.labels(
            service_id=hex(ctx.service_id),
            method_id=hex(ctx.method_id)
        ).observe(latency_ms)
        
        return response
    
    async def on_error(self, ctx: Context, error: Exception) -> None:
        self.request_counter.labels(
            service_id=hex(ctx.service_id),
            method_id=hex(ctx.method_id),
            result="error"
        ).inc()
        raise error
```

### 2.3 追踪 (Tracing) 拦截器

```python
class TracingInterceptor(Interceptor):
    """
    追踪拦截器 - OpenTelemetry 集成
    
    幂等性: 幂等 (生成新 span，无副作用)
    执行位置: 最外层，包裹整个请求
    
    职责:
      - 提取/生成 Trace Context
      - 创建 Span
      - 注入到出站请求 (见第4.2节)
      - 记录 Span 属性
    """
    
    async def before_request(self, ctx: Context, request: Request) -> Request:
        # 创建 Span
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span(
            f"rpc.{ctx.service_id:04x}.{ctx.method_id:04x}"
        ) as span:
            span.set_attribute("rpc.service_id", ctx.service_id)
            span.set_attribute("rpc.method_id", ctx.method_id)
            span.set_attribute("rpc.client", ctx.client_address[0])
            
            # 将 span 存储到 context，便于后续使用
            ctx.current_span = span
        
        return request
    
    async def after_response(self, ctx: Context, response: Response) -> Response:
        if hasattr(ctx, 'current_span'):
            ctx.current_span.set_attribute("rpc.result", "success")
        return response
    
    async def on_error(self, ctx: Context, error: Exception) -> None:
        if hasattr(ctx, 'current_span'):
            ctx.current_span.set_attribute("rpc.result", "error")
            ctx.current_span.set_attribute("error.type", type(error).__name__)
        raise error
```

### 2.4 重试 (Retry) 拦截器

```python
class RetryInterceptor(Interceptor):
    """
    重试拦截器
    
    幂等性: 幂等 (决策结果不依赖重试次数)
    执行位置: 次外层 (在 Tracing 之内)
    
    重试决策逻辑:
      1. 仅对声明为幂等 (idempotent=True) 的方法重试
      2. 可重试的异常: TimeoutError, ConnectionError, ServiceUnavailable
      3. 不重试的异常: MethodNotFound, BadRequest, UnauthorizedError
      4. 退避策略: 指数退避 + 抖动
    """
    
    async def before_request(self, ctx: Context, request: Request) -> Request:
        ctx.retry_count = 0
        ctx.retry_max = self.config.max_attempts - 1
        return request
    
    async def on_error(self, ctx: Context, error: Exception) -> Optional[Response]:
        if not self._is_retryable(error):
            raise error
        
        if ctx.retry_count >= ctx.retry_max:
            raise error
        
        # 检查方法幂等性
        method_metadata = ctx.method_metadata
        if not method_metadata.get('idempotent', False):
            raise error  # 非幂等方法不重试
        
        # 计算退避时间
        delay = self._backoff_delay(ctx.retry_count)
        ctx.retry_count += 1
        
        self.logger.warning(
            f"Retry {ctx.retry_count}/{ctx.retry_max}",
            extra={"trace_id": ctx.trace_id, "delay_ms": delay * 1000}
        )
        
        await asyncio.sleep(delay)
        
        # 返回 None 表示继续向下处理 (由框架负责重新调用)
        return None
    
    def _is_retryable(self, error: Exception) -> bool:
        """判断异常是否可重试"""
        retryable_types = (
            TimeoutError,
            ConnectionError,
            OSError,  # 网络错误
        )
        return isinstance(error, retryable_types)
    
    def _backoff_delay(self, attempt: int) -> float:
        """计算指数退避延迟"""
        base = self.config.backoff_factor * (2 ** attempt)
        jitter = random.uniform(0, base * 0.1)
        return min(base + jitter, self.config.max_delay)
```

### 2.5 限流 (Rate Limiting) 拦截器

```python
class RateLimitInterceptor(Interceptor):
    """
    限流拦截器 - 令牌桶算法
    
    幂等性: 非幂等 (消费令牌有副作用)
    执行位置: 应在 Retry 之后，不能在 Retry 外层
    
    原因: 若重试，令牌会被消费多次，导致实际限流偏严
    解决: 在 Retry 之内执行，仅在最终调用前消费
    """
    
    async def before_request(self, ctx: Context, request: Request) -> Optional[Response]:
        # 获取令牌
        if not await self.token_bucket.try_acquire(ctx.service_id, timeout=0):
            # 限流 → 返回 429 响应
            return Response(
                status=429,
                payload=b"Rate limit exceeded"
            )
        
        return request
    
    async def on_error(self, ctx: Context, error: Exception) -> None:
        # 限流不处理错误，继续传播
        raise error
```

### 2.6 认证 (Auth) 拦截器

```python
class AuthInterceptor(Interceptor):
    """
    认证拦截器
    
    幂等性: 幂等 (仅检查令牌，无副作用)
    执行位置: Auth 应在 RateLimit 和业务逻辑之前
    """
    
    async def before_request(self, ctx: Context, request: Request) -> Optional[Response]:
        token = request.metadata.get("authorization")
        
        if not token:
            return Response(status=401, payload=b"Unauthorized")
        
        if not self._verify_token(token):
            return Response(status=403, payload=b"Forbidden")
        
        # 验证通过，存储到 context
        ctx.authenticated_user = self._extract_user(token)
        
        return request
    
    def _verify_token(self, token: str) -> bool:
        # 令牌验证逻辑
        pass
```

### 2.7 熔断器 (Circuit Breaker) 拦截器

```python
class CircuitBreakerInterceptor(Interceptor):
    """
    熔断器拦截器 - 防止级联故障
    
    幂等性: 幂等
    执行位置: 应在 Retry 之前或之后均可
    
    工作原理:
      - Closed (正常): 请求通过，记录失败计数
      - Open (熔断): 快速失败，拒绝请求
      - HalfOpen (半开): 允许有限的测试请求
    """
    
    async def before_request(self, ctx: Context, request: Request) -> Optional[Response]:
        state = self.circuit_breaker.get_state(ctx.service_id)
        
        if state == CircuitState.OPEN:
            # 熔断打开，快速失败
            return Response(
                status=503,
                payload=b"Service temporarily unavailable (circuit breaker open)"
            )
        
        if state == CircuitState.HALF_OPEN:
            # 半开状态，允许测试请求，但标记
            ctx.circuit_breaker_test_request = True
        
        return request
    
    async def on_error(self, ctx: Context, error: Exception) -> None:
        # 记录失败
        self.circuit_breaker.record_failure(ctx.service_id)
        raise error
    
    async def after_response(self, ctx: Context, response: Response) -> Response:
        # 记录成功
        self.circuit_breaker.record_success(ctx.service_id)
        return response
```

### 2.8 校验 (Validation) 拦截器

```python
class ValidationInterceptor(Interceptor):
    """
    校验拦截器 - 基于 Pydantic/JSON Schema
    
    幂等性: 幂等 (仅做检查)
    执行位置: 应在业务逻辑之前
    """
    
    async def before_request(self, ctx: Context, request: Request) -> Optional[Response]:
        try:
            # 获取方法的参数schema
            schema = ctx.method_schema
            
            # 校验请求参数
            request.args = schema.validate(request.args)
            
            return request
        except ValidationError as e:
            return Response(
                status=400,
                payload=json.dumps({"error": str(e)}).encode()
            )
```

## 3. 插件系统

- **发现机制**：
  - Python `entry_points` (标准方式)。
  - 扫描指定目录下的 `.py` 文件。
- **生命周期**：`setup(config) -> start() -> stop() -> teardown()`。
- **隔离性**：插件运行在主进程中，需确保插件不阻塞 Event Loop（CPU 密集型任务应提交到 ThreadPoolExecutor）。

## 4. 配置化拦截器

```yaml
interceptors:
  - name: tracing
    enabled: true
    config:
      provider: opentelemetry
      sample_rate: 0.1
  - name: rate_limit
    enabled: true
    config:
      rate: 100/s
      burst: 20
  - name: retry
    enabled: true
    config:
      max_attempts: 3
      backoff_factor: 0.5
```

## 4. 执行顺序与链构建

**推荐的拦截器顺序** (客户端):

```
最外层 (最先执行)
  ▼
[1] Tracing.before_request
  ▼
[2] Logging.before_request  
  ▼
[3] Validation.before_request
  ▼
[4] Auth.before_request (检查权限)
  ▼
[5] Caching.before_request (查询缓存，可short-circuit)
  ▼
[6] RateLimit.before_request (消费令牌)
  ▼
[7] CircuitBreaker.before_request (熔断检查)
  ▼
[8] Retry.before_request (初始化重试计数)
  ▼
══ 实际 RPC 调用 ══
  ▼
[8] Retry.on_error (重试决策) ◀─┐ (若可重试，循环)
  ▼                        │
[7] CircuitBreaker.after_response (记录成功/失败)
  ▼
[6] RateLimit.after_response (可选)
  ▼
[5] Caching.after_response (缓存结果)
  ▼
[4] Auth.after_response (可选)
  ▼
[3] Validation.after_response (可选)
  ▼
[2] Logging.after_response
  ▼
[1] Tracing.after_response
  ▼
最内层 (最后执行)
```

**关键特性**：
- **Caching 可 short-circuit**: 命中缓存 → 跳过 RateLimit、RPC 等
- **Retry 跨越 RPC**: 整个 RPC 调用都在重试范围内
- **Metrics 在 Retry 之后**: 统计的是最终结果 (含重试次数)
- **RateLimit 不在 Retry 外**: 避免重试时重复消费令牌

**服务端推荐顺序**:

```
[1] Tracing.before_request
  ▼
[2] Metrics.before_request
  ▼
[3] Auth.before_request
  ▼
[4] RateLimit.before_request
  ▼
[5] Validation.before_request
  ▼
══ 业务逻辑执行 ══
  ▼
[5] Validation.after_response
  ▼
[4] RateLimit.after_response
  ▼
[3] Auth.after_response
  ▼
[2] Metrics.after_response
  ▼
[1] Tracing.after_response
```

### 配置化拦截器

```yaml
interceptors:
  # 客户端拦截器
  client:
    - name: tracing
      enabled: true
      config:
        provider: opentelemetry
        sampler:
          type: adaptive  # 或 fixed_rate
          rate: 0.1
        # Trace Context 格式
        propagator: w3c_trace_context  # 或 b3
      
    - name: logging
      enabled: true
      config:
        level: info
        format: json
      
    - name: caching
      enabled: true
      config:
        ttl_seconds: 60
        max_size_mb: 100
      
    - name: rate_limit
      enabled: true
      config:
        algorithm: token_bucket
        rate: 1000/s
        burst: 100
      
    - name: retry
      enabled: true
      config:
        max_attempts: 3
        backoff_factor: 0.1
        max_delay_seconds: 1
      
    - name: circuit_breaker
      enabled: true
      config:
        failure_threshold: 50  # 失败率超过50%则打开
        success_threshold: 5   # 半开状态下成功5次则关闭
        timeout_seconds: 30    # 打开状态下持续30秒后进入半开

  # 服务端拦截器
  server:
    - name: auth
      enabled: true
      config:
        token_type: jwt
        secret_key: "your-secret"
    
    - name: rate_limit
      enabled: true
      config:
        per_method: true  # 按方法限流
        rate: 100/s
```
