# tinySOA API 设计与使用指南

## 1. 设计原则

- 简洁：以声明式方式定义服务与方法，最少样板代码。
- 异步：基于 asyncio，统一使用 `async/await`。
- 可插拔：拦截器链贯穿调用生命周期，支持插件扩展。
- 可观测：内建指标与追踪钩子，易于集成 Prometheus / OpenTelemetry。

## 2. 核心概念

- 服务（Service）：由 `service_id`、`instance_id`、版本、方法与事件组成。
- 方法（Method）：远程过程调用（RPC），请求-响应。
- 事件（Event）：发布/订阅模型，通知订阅者最新状态。
- 代理（Proxy）：客户端侧的服务调用封装，支持负载均衡、重试与超时。
- 注册表（Registry）：本地维护已注册与已发现的服务元数据与状态。

## 3. 服务定义（Server）

建议提供声明式装饰器与简易构造器，封装 `someip.service.SimpleService`。

```python
# 伪代码，仅为API提案
from tinysoa import Service, rpc, eventgroup

@Service(
    service_id=0x1234,
    instance_id=0x0001,
    version=(1, 0),
    name="CalcService",
)
class CalcService:
    @rpc(method_id=0x0001)
    async def add(self, a: int, b: int) -> int:
        return a + b

    @rpc(method_id=0x0002)
    async def mul(self, a: int, b: int) -> int:
        return a * b

    # 事件组：用于发布状态变化通知
    status = eventgroup(id=0x0001)

    async def on_start(self):
        # 初始化资源、连接、缓存等
        pass

    async def on_stop(self):
        # 释放资源
        pass


async def main():
    svc = await CalcService.start(bind=("0.0.0.0", 30490))
    # 更新事件值并通知
    svc.status.values[0x0001] = b"ready"
    await svc.status.notify_once(events=[0x0001])
```

要点：
- `@Service` 装饰器将类与元数据绑定，并提供 `start()/stop()` 生命周期方法。
- `@rpc` 装饰器将协程方法绑定到 SOME/IP `method_id`，自动完成序列化/反序列化。
- `eventgroup(...)` 基于 `SimpleEventgroup`，支持周期性通知与一次性通知。

## 4. 客户端代理（Client / Proxy）

代理负责：发现可用实例、选择端点、发起调用、处理重试与超时、上下文传播。

### 4.1 完整的代理接口

```python
class ServiceProxyConfig:
    """代理配置"""
    service_id: int
    instance_id: Optional[int] = None  # 指定特定实例，None表示自动选择
    version: Tuple[int, int] = (1, 0)
    
    # 调用参数
    timeout_ms: float = 500
    max_retries: int = 2
    
    # 负载均衡
    lb_policy: str = "latency_weighted"  # 或 round_robin / consistent_hash / adaptive
    lb_weights: Dict[str, float] = None  # 健康度评分权重
    
    # 实例过滤
    min_health_score: float = 0.1  # 过滤掉评分低于此值的实例
    preferred_version: Optional[Tuple[int, int]] = None
    
    # 拦截器
    interceptors: List[Interceptor] = []
    
    # 编解码器
    codec: str = "msgpack"

class CallContext:
    """
    单次调用的上下文
    
    可通过上下文管理器设置单次调用的覆盖参数
    """
    service_id: int
    method_id: int
    client_address: Tuple[str, int]
    trace_id: str
    span_id: str
    deadline: float  # Unix 时间戳
    metadata: Dict[str, Any]  # 用户自定义元数据
    
    # 调用覆盖参数
    timeout_override: Optional[float] = None
    retry_override: Optional[int] = None
    lb_policy_override: Optional[str] = None

class ServiceProxy:
    """
    服务代理 - 客户端侧的服务访问入口
    
    职责:
      1. 服务发现: 通过 Registry 查找可用实例
      2. 负载均衡: 按策略选择实例
      3. 调用执行: 发起RPC请求
      4. 拦截器链: 注入监控、追踪、限流等
      5. 故障处理: 重试、故障转移、熔断
    """
    
    def __init__(self, config: ServiceProxyConfig):
        self.config = config
        self.registry: ServiceRegistry = get_default_registry()
        self.load_balancer = self._create_load_balancer(config.lb_policy)
        self.interceptor_chain = InterceptorChain(config.interceptors)
        self.circuit_breaker = CircuitBreaker()  # 熔断器
    
    async def connect(self) -> "ServiceProxy":
        """
        连接代理 (可选)
        
        预连接到服务的某个实例，或发起首次服务发现
        """
        instances = await self.registry.find_service(
            service_id=self.config.service_id,
            min_version=self.config.preferred_version
        )
        if not instances:
            raise ServiceUnavailableError(
                f"Service {self.config.service_id} not found"
            )
        return self
    
    async def call(
        self,
        method_id: int,
        args: tuple = (),
        kwargs: dict = None,
        **options
    ) -> Any:
        """
        同步RPC调用
        
        :param method_id: 方法ID
        :param args: 位置参数
        :param kwargs: 关键字参数
        :param options: 单次调用的覆盖参数 (timeout, retries等)
        :return: 远程方法的返回值
        
        用法:
            result = await proxy.call(method_id=0x0001, args=(3, 5))
            result = await proxy.call(0x0001, a=3, b=5)  # 命名参数
        """
        ctx = self._build_context(method_id, options)
        
        # 拦截器 before_request
        request = Request(
            service_id=self.config.service_id,
            method_id=method_id,
            args=args,
            kwargs=kwargs or {},
            context=ctx
        )
        request = await self.interceptor_chain.before_request(ctx, request)
        
        try:
            # 执行调用 (含重试和故障转移)
            response = await self._execute_with_failover(request, ctx)
            
            # 拦截器 after_response
            response = await self.interceptor_chain.after_response(ctx, response)
            return response.payload
            
        except Exception as e:
            # 拦截器 on_error
            response = await self.interceptor_chain.on_error(ctx, e)
            if response:
                return response.payload
            raise
    
    async def call_oneway(
        self,
        method_id: int,
        args: tuple = (),
        fire_and_forget: bool = True,
        **options
    ) -> None:
        """
        单向异步调用 (Fire and Forget)
        
        发送请求但不等待响应，用于异步通知
        """
        ctx = self._build_context(method_id, options)
        request = Request(
            service_id=self.config.service_id,
            method_id=method_id,
            args=args,
            context=ctx,
            message_type=SOMEIPMessageType.REQUEST_NO_RETURN
        )
        await self.interceptor_chain.before_request(ctx, request)
        await self._send_async_request(request, ctx)
    
    async def subscribe(
        self,
        eventgroup_id: int,
        filter_fn: Optional[Callable[[Event], bool]] = None
    ) -> AsyncIterator[Event]:
        """
        订阅事件组
        
        :param eventgroup_id: 事件组ID
        :param filter_fn: 事件过滤函数 (可选)
        :return: 异步事件迭代器
        
        用法:
            async for event in proxy.subscribe(eventgroup_id=0x0001):
                print(f"Event: {event.payload}")
        """
        
        # 找到实例
        instances = await self.registry.find_service(self.config.service_id)
        if not instances:
            raise ServiceUnavailableError()
        
        instance = await self.load_balancer.select(instances)
        
        # 订阅 (通过SD协议)
        sub_id = await self.registry.subscribe_eventgroup(
            service_id=self.config.service_id,
            instance_id=instance.id,
            eventgroup_id=eventgroup_id
        )
        
        try:
            async for event in self.registry.event_stream(sub_id):
                if filter_fn is None or filter_fn(event):
                    yield event
        finally:
            await self.registry.unsubscribe_eventgroup(sub_id)
    
    async def _execute_with_failover(
        self,
        request: Request,
        ctx: CallContext
    ) -> Response:
        """
        带故障转移的执行
        
        尝试多个实例，直到成功
        """
        instances = await self.registry.find_service(self.config.service_id)
        if not instances:
            raise ServiceUnavailableError()
        
        # 应用实例过滤
        instances = self._filter_instances(instances, ctx)
        
        max_retries = ctx.retry_override or self.config.max_retries
        last_error = None
        attempted = set()
        
        for attempt in range(max_retries + 1):
            try:
                # 熔断器检查
                if self.circuit_breaker.is_open():
                    raise CircuitBreakerOpenError()
                
                # 选择实例
                available = [i for i in instances if i.id not in attempted]
                if not available:
                    break
                
                instance = await self.load_balancer.select(available, ctx)
                attempted.add(instance.id)
                
                # 执行请求
                start_time = time.time()
                response = await self._call_method(request, instance, ctx)
                elapsed = (time.time() - start_time) * 1000
                
                # 成功 → 记录
                await self.load_balancer.record_result(instance, success=True, latency_ms=elapsed)
                self.circuit_breaker.record_success()
                
                return response
                
            except (TimeoutError, ConnectionError, RemoteServiceError) as e:
                last_error = e
                await self.load_balancer.record_result(instance, success=False, latency_ms=0)
                self.circuit_breaker.record_failure()
                
                # 如果是幂等方法，继续重试
                if self._is_idempotent(request.method_id):
                    await asyncio.sleep(self._backoff_delay(attempt))
                    continue
                else:
                    raise  # 非幂等方法不重试
        
        raise FailoverExhaustedError(f"All instances failed. Last: {last_error}")
    
    def _filter_instances(
        self,
        instances: List[ServiceInstance],
        ctx: CallContext
    ) -> List[ServiceInstance]:
        """应用实例过滤条件"""
        # 健康度过滤
        min_score = self.config.min_health_score
        instances = [i for i in instances if self.load_balancer.get_health_score(i).score >= min_score]
        
        # 版本过滤
        if self.config.preferred_version:
            instances = [
                i for i in instances
                if (i.metadata.version_major, i.metadata.version_minor) >= self.config.preferred_version
            ]
        
        # 区域亲和性过滤 (从context检测)
        if hasattr(ctx, 'preferred_zone'):
            preferred = [i for i in instances if i.tags.get('zone') == ctx.preferred_zone]
            if preferred:  # 有优先区域的实例，否则不限制
                instances = preferred
        
        return instances or instances  # 至少返回一个
    
    def _build_context(self, method_id: int, options: dict) -> CallContext:
        """构建调用上下文"""
        ctx = CallContext(
            service_id=self.config.service_id,
            method_id=method_id,
            client_address=get_local_address(),
            trace_id=options.get('trace_id') or generate_trace_id(),
            span_id=generate_span_id(),
            deadline=time.time() + (options.get('timeout') or self.config.timeout_ms) / 1000,
            metadata=options.get('metadata') or {}
        )
        
        # 覆盖参数
        if 'timeout' in options:
            ctx.timeout_override = options['timeout']
        if 'retries' in options:
            ctx.retry_override = options['retries']
        if 'lb_policy' in options:
            ctx.lb_policy_override = options['lb_policy']
        
        return ctx
    
    def _is_idempotent(self, method_id: int) -> bool:
        """判断方法是否幂等 (配置管理)"""
        idempotent_methods = self.config.metadata.get('idempotent_methods', set())
        return method_id in idempotent_methods
    
    def _backoff_delay(self, attempt: int) -> float:
        """计算重试延迟 (指数退避+抖动)"""
        base = 0.01 * (2 ** attempt)  # 10ms, 20ms, 40ms, ...
        jitter = random.uniform(0, base * 0.1)
        return min(base + jitter, 1.0)  # 最大延迟1秒

class ContextManager:
    """
    上下文管理器 - 设置单次调用的参数
    
    用法:
        with context.timeout(1.0), context.metadata({"trace_id": "abc"}):
            result = await proxy.call(method_id=0x0001, args=(3, 5))
    """
    
    @staticmethod
    def timeout(timeout_ms: float):
        """设置单次调用的超时"""
        # 返回上下文管理器
        pass
    
    @staticmethod
    def retries(max_retries: int):
        """设置单次调用的重试次数"""
        pass
    
    @staticmethod
    def metadata(**metadata):
        """设置调用元数据"""
        pass
    
    @staticmethod
    def lb_policy(policy: str):
        """单次调用覆盖LB策略"""
        pass
```

### 4.2 使用示例

```python
# 创建代理
calc_proxy = await ServiceProxy(
    ServiceProxyConfig(
        service_id=0x1234,
        version=(1, 0),
        timeout_ms=500,
        max_retries=2,
        lb_policy="latency_weighted",
        interceptors=[
            metrics_interceptor(),
            tracing_interceptor(),
            retry_interceptor()
        ]
    )
).connect()

# 同步RPC调用
result = await calc_proxy.call(method_id=0x0001, args=(3, 5))

# 单次调用覆盖参数
with context.timeout(1000), context.metadata({"user_id": "123"}):
    result = await calc_proxy.call(method_id=0x0002, a=10, b=20)

# 异步单向调用
await calc_proxy.call_oneway(method_id=0x0003, args=("notify",))

# 事件订阅
async for event in calc_proxy.subscribe(eventgroup_id=0x0001):
    print(f"Status: {event.payload}")
```

## 5. 数据编解码

- 默认使用简单字节序列（`bytes`）或结构体编码；提供可插拔的编解码器（如 msgpack/CBOR/Protobuf）。
- 方法签名与编解码器绑定：在 `@rpc` 中指定 `codec="msgpack"` 等。

```python
@rpc(method_id=0x0001, codec="msgpack")
async def add(self, req: AddRequest) -> AddResponse:
    ...
```

## 6. 错误与重试

- 统一异常层：`TimeoutError`、`UnavailableError`、`DecodeError`、`RemoteError`。
- 可配置重试策略：固定间隔、指数退避、幂等方法限定重试。
- 支持熔断（Circuit Breaker）与限流（Rate Limit）作为拦截器实现。

## 7. 拦截器链（Interceptor Chain）

- 形态：`before(request) -> request`，`after(response) -> response`，`on_error(error) -> error/response`。
- 常见拦截器：日志、指标、追踪、鉴权、压缩、缓存。
- 执行顺序：注册顺序 + 明确的阶段划分（调用前、调用后、错误处理）。

```python
from tinysoa import interceptors

calc = await Proxy(...).use(
    interceptors.tracing(),
    interceptors.metrics(),
    interceptors.retry(max_attempts=2),
)
```

## 8. 配置与环境

- 层次：默认值 → 文件（YAML/JSON/TOML）→ 环境变量 → 代码覆盖。
- 关键项：端口、接口版本、超时、重试、LB 策略、拦截器启用、编解码器。
- 动态更新：在不变更服务 ID/版本前提下支持热更新（参考 `02-core-components.md` 的配置管理器）。

## 9. 可观测性

- 指标：`rpc_requests_total`、`rpc_latency_ms`、`rpc_errors_total`、`event_notifies_total`。
- 追踪：注入/提取上下文（W3C Trace Context 或 B3），跨进程相关性。
- 日志：结构化日志，包含 `service_id/method_id/session_id/client_addr` 等。

## 10. 安全（可选）

- 传输层：优先 UDP；如需 TCP，请遵循 SOME/IP over TCP 约束。
- 身份：令牌/签名（可由拦截器实现），最小权限原则。
- 输入验证：服务端在编解码阶段验证类型与范围。

## 11. 示例目录结构

```
app/
  services/
    calc_service.py
  client/
    calc_client.py
  config/
    tinysOA.yaml
  README.md
```
