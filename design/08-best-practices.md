# 最佳实践与示例

## 1. 目录与分层

```
my_tinysoa_app/
├── services/
│   ├── __init__.py
│   ├── auth_service.py         # 认证服务
│   ├── calc_service.py         # 计算服务
│   └── payment_service.py      # 支付服务
│
├── clients/
│   ├── __init__.py
│   ├── calc_client.py          # 计算服务客户端
│   └── payment_client.py       # 支付服务客户端
│
├── common/
│   ├── __init__.py
│   ├── interceptors.py         # 自定义拦截器
│   ├── serializers.py          # 自定义编解码器
│   ├── constants.py            # 常量定义 (服务ID等)
│   └── utils.py                # 工具函数
│
├── config/
│   ├── default.yaml            # 默认配置
│   ├── dev.yaml                # 开发配置
│   ├── staging.yaml            # 预发配置
│   └── prod.yaml               # 生产配置
│
├── tests/
│   ├── __init__.py
│   ├── test_services.py        # 服务测试
│   ├── test_integration.py     # 集成测试
│   └── fixtures/
│       ├── mocks.py            # Mock对象
│       └── helpers.py          # 测试工具
│
├── scripts/
│   ├── run_service.py          # 启动脚本
│   ├── migrate_config.py       # 配置迁移
│   └── benchmark.py            # 性能测试
│
├── docs/
│   ├── architecture.md         # 架构说明
│   ├── api.md                  # API文档
│   └── deployment.md           # 部署指南
│
├── requirements.txt
├── pyproject.toml
└── README.md
```

## 2. 开发流程（按阶段）

### Phase 1: 单机基础开发

1. **定义服务与方法签名**
   ```python
   @Service(service_id=0x1234, version=(1, 0))
   class CalcService:
       @rpc(method_id=0x0001, idempotent=True)
       async def add(self, a: int, b: int) -> int:
           return a + b
   ```

2. **编写业务逻辑**
   ```python
   async def on_start(self):
       # 初始化资源
       self.logger.info("Calc service started")
   
   async def on_stop(self):
       # 释放资源
       pass
   ```

3. **本地集成测试**
   ```python
   @pytest.mark.asyncio
   async def test_add():
       service = await CalcService.start()
       result = await service.call(0x0001, args=(3, 5))
       assert result == 8
       await service.stop()
   ```

4. **配置基础拦截器**
   - 日志、指标、追踪
   ```yaml
   interceptors:
     - type: logging
       level: debug
   ```

### Phase 2: 分布式部署

1. **配置服务发现**
   ```yaml
   discovery:
     multicast_group: "239.0.0.1"
     announce_interval: 3.0
   ```

2. **声明依赖关系**
   ```python
   @Service(
       depends_on=[
           ServiceDependency(0x5678, required=True),
           ServiceDependency(0x9999, required=False)
       ]
   )
   ```

3. **部署多实例**
   - 实例1: instance_id=0x0001, port=30490
   - 实例2: instance_id=0x0002, port=30491
   - 自动发现与负载均衡

4. **故障恢复测试**
   ```python
   # 模拟实例故障
   await service_instance1.stop()
   # 验证客户端自动转移到instance2
   assert await client.call(method_id) == expected_result
   ```

### Phase 3: 生产级优化

1. **完整的拦截器链**
   ```python
   client = await Proxy(
       service_id=0x1234,
       interceptors=[
           tracing_interceptor(),     # Jaeger集成
           metrics_interceptor(),     # Prometheus
           retry_interceptor(max_attempts=3),
           rate_limit_interceptor(rate="100/s"),
           circuit_breaker_interceptor(),
           auth_interceptor(token_type="jwt")
       ]
   ).connect()
   ```

2. **SLO监控与告警**
   ```python
   # Prometheus告警规则
   - alert: HighLatency
     expr: histogram_quantile(0.95, rpc_latency_ms{method="add"}) > 20
   ```

3. **性能基准测试**
   ```bash
   python scripts/benchmark.py --concurrency 100 --duration 60s
   # 验证P95延迟 < 25ms
   ```

### Phase 4: 工程完善

1. **代码生成**
   ```bash
   tinysoa-gen --proto services/calc.proto
   # 生成 CalcServiceServer 和 CalcServiceClient
   ```

2. **文档自动生成**
   ```bash
   tinysoa-docs generate --output docs/api.html
   ```

3. **安全加固**
   - 启用TLS
   - Token认证
   - 审计日志

## 3. 测试建议

- 单元测试：方法逻辑与编解码器；拦截器行为。
- 集成测试：SD 发现、事件订阅、故障注入（丢包、超时、重启）。
- 压测：并发与背压、P95/P99 延迟、丢弃/重试率。

## 4. 部署建议

- 资源：限制并发与队列长度，避免过载。
- 监控：启用指标与追踪，设置报警阈值。
- 配置：采用不可变镜像 + 环境变量覆盖，关键参数热更新。

## 5. 安全建议

- 输入校验与最小权限；关闭未使用的事件/方法；审计日志。
- 对外暴露端口与网络策略严格控制；按需开启 TCP。

## 6. 完整示例代码片段

### 6.1 服务端示例（Phase 1 MVP）

```python
# services/calc_service.py
from tinysoa import Service, rpc
from datetime import datetime

@Service(
    service_id=0x1234,
    instance_id=0x0001,
    version=(1, 0),
    name="CalcService"
)
class CalcService:
    
    async def on_start(self):
        """服务启动时调用"""
        self.logger.info("CalcService initialized")
        self.start_time = datetime.now()
    
    @rpc(method_id=0x0001, idempotent=True)
    async def add(self, a: int, b: int) -> int:
        """
        加法操作
        
        Args:
            a: 第一个数
            b: 第二个数
        
        Returns:
            和
        """
        return a + b
    
    @rpc(method_id=0x0002, idempotent=True)
    async def multiply(self, a: int, b: int) -> int:
        """乘法操作"""
        return a * b
    
    @rpc(method_id=0x0003, idempotent=False)
    async def log_operation(self, operation: str, result: int) -> None:
        """记录操作（非幂等，不支持重试）"""
        self.logger.info(f"{operation}: {result}")
    
    async def on_stop(self):
        """服务停止时调用"""
        uptime = datetime.now() - self.start_time
        self.logger.info(f"CalcService stopped. Uptime: {uptime}")

# 启动服务
async def main():
    svc = CalcService()
    await svc.start(bind=("0.0.0.0", 30490))
    try:
        # 发出就绪通知
        await svc.publish_ready()
        # 阻塞直到收到停止信号
        await svc.wait_for_termination()
    finally:
        await svc.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### 6.2 客户端示例（Phase 1 MVP）

```python
# clients/calc_client.py
from tinysoa import Proxy, ServiceProxyConfig, context

async def main():
    # 创建代理
    config = ServiceProxyConfig(
        service_id=0x1234,
        version=(1, 0),
        timeout_ms=500,
        max_retries=2
    )
    
    calc_proxy = await Proxy(config).connect()
    
    try:
        # 基础RPC调用
        result = await calc_proxy.call(method_id=0x0001, args=(3, 5))
        print(f"3 + 5 = {result}")  # 输出: 3 + 5 = 8
        
        # 带上下文的调用
        with context.timeout(1000), context.metadata({"user_id": "alice"}):
            result = await calc_proxy.call(method_id=0x0002, args=(6, 7))
            print(f"6 * 7 = {result}")  # 输出: 6 * 7 = 42
        
        # 非幂等方法（不支持重试）
        await calc_proxy.call(method_id=0x0003, args=("addition",), kwargs={"result": 8})
        
    finally:
        await calc_proxy.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### 6.3 拦截器自定义示例（Phase 3）

```python
# common/interceptors.py
from tinysoa import Interceptor, Context, Request, Response
import json
import hashlib

class CustomLoggingInterceptor(Interceptor):
    """自定义日志拦截器"""
    
    async def before_request(self, ctx: Context, request: Request) -> Request:
        self.logger.info(
            f"[{ctx.trace_id}] RPC starting",
            extra={
                "service": hex(ctx.service_id),
                "method": hex(ctx.method_id),
                "client": ctx.client_address[0]
            }
        )
        ctx.start_time = time.time()
        return request
    
    async def after_response(self, ctx: Context, response: Response) -> Response:
        elapsed_ms = (time.time() - ctx.start_time) * 1000
        self.logger.info(
            f"[{ctx.trace_id}] RPC completed",
            extra={"elapsed_ms": elapsed_ms, "status": response.status}
        )
        return response

class RequestSigningInterceptor(Interceptor):
    """请求签名拦截器 (安全)"""
    
    def __init__(self, secret: str):
        self.secret = secret
    
    async def before_request(self, ctx: Context, request: Request) -> Request:
        # 计算请求签名
        payload_bytes = json.dumps(request.args).encode()
        signature = hashlib.sha256(payload_bytes + self.secret.encode()).hexdigest()
        
        # 加入元数据
        ctx.metadata["X-Signature"] = signature
        
        return request
    
    async def on_error(self, ctx: Context, error: Exception) -> Optional[Response]:
        if isinstance(error, AuthenticationError):
            # 认证错误直接返回401
            return Response(status=401, payload=b"Invalid signature")
        raise error

class CachingInterceptor(Interceptor):
    """结果缓存拦截器"""
    
    def __init__(self, ttl_seconds: int = 60):
        self.cache = {}
        self.ttl = ttl_seconds
    
    async def before_request(self, ctx: Context, request: Request) -> Optional[Response]:
        # 只缓存幂等方法
        if not ctx.method_metadata.get('idempotent', False):
            return request
        
        # 生成缓存键
        cache_key = f"{ctx.service_id}:{ctx.method_id}:{json.dumps(request.args)}"
        
        # 查询缓存
        if cache_key in self.cache:
            cached_result, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.ttl:
                self.logger.debug(f"Cache hit: {cache_key}")
                return Response(status=200, payload=cached_result)
        
        return request
    
    async def after_response(self, ctx: Context, response: Response) -> Response:
        # 缓存成功的响应
        if response.status == 200:
            cache_key = f"{ctx.service_id}:{ctx.method_id}:{json.dumps(request.args)}"
            self.cache[cache_key] = (response.payload, time.time())
        
        return response
```

### 6.4 依赖管理示例（Phase 2）

```python
# services/payment_service.py
from tinysoa import Service, ServiceDependency, rpc

@Service(
    service_id=0x5678,
    instance_id=0x0001,
    version=(1, 0),
    depends_on=[
        # 依赖认证服务 (必需，启动前等待)
        ServiceDependency(
            service_id=0x1111,
            version=(1, 0),
            required=True,
            timeout_s=10
        ),
        # 依赖日志服务 (可选，启动前可不可用)
        ServiceDependency(
            service_id=0x2222,
            required=False
        )
    ]
)
class PaymentService:
    
    async def on_start(self):
        """启动时等待依赖"""
        self.logger.info("Waiting for dependencies...")
        
        # 等待必需依赖
        await self._wait_for_dependency(0x1111)
        
        self.logger.info("All required dependencies satisfied, service ready")
    
    @rpc(method_id=0x0001, idempotent=True)
    async def process_payment(self, amount: float, account_id: str) -> bool:
        """处理支付 (需要先通过认证服务)"""
        
        # 调用认证服务验证账户
        try:
            auth_result = await self.call_dependency(
                service_id=0x1111,
                method_id=0x0001,
                args=(account_id,),
                timeout=2.0
            )
        except DependencyUnavailableError:
            # 依赖服务不可用 → 进入降级模式
            self.logger.warning("Auth service unavailable, using cached policy")
            auth_result = await self._use_cached_policy(account_id)
        
        if not auth_result:
            return False
        
        # 执行支付逻辑
        return await self._do_payment(amount, account_id)
```

### 6.5 配置示例

```yaml
# config/prod.yaml
service:
  service_id: 0x1234
  instance_id: 0x0001
  version: [1, 0]
  name: "CalcService"

network:
  bind: "0.0.0.0:30490"
  multicast: "239.0.0.1:30490"
  multicast_interval: 3.0

client:
  timeout_ms: 500
  retries: 2
  lb_policy: latency_weighted
  lb_weights:
    availability: 0.4
    latency: 0.4
    load: 0.2

interceptors:
  client:
    - name: tracing
      enabled: true
      config:
        provider: opentelemetry
        sampler:
          type: adaptive
          rate: 0.01
        exporter: jaeger
        jaeger_endpoint: "http://jaeger:14268/api/traces"
    
    - name: metrics
      enabled: true
      config:
        prometheus_port: 9090
    
    - name: retry
      enabled: true
      config:
        max_attempts: 3
        backoff_factor: 0.1
    
    - name: rate_limit
      enabled: true
      config:
        rate: "1000/s"
        burst: 100
    
    - name: circuit_breaker
      enabled: true
      config:
        failure_threshold: 50
        timeout_seconds: 30

logging:
  level: info
  format: json
  output: stdout

monitoring:
  enabled: true
  health_check_interval: 10
```
