# 监控与追踪设计

## 1. 指标（Metrics）

- 计数：`rpc_requests_total{service_id,method_id,result}`。
- 直方图：`rpc_latency_ms{service_id,method_id}`，客户端与服务端分开统计。
- 事件：`event_notifies_total{service_id,event_id}`、订阅数与丢弃数。
- 健康：`service_health{service_id,instance_id}`，值：`0/1`。
- 导出：Prometheus `/:metrics`（可选本地端点）或 pushgateway。

## 2. 追踪（Tracing）

### 2.1 上下文传递方案

**问题**: SOME/IP 头部为固定格式，不可扩展。无法直接扩展协议头。

**解决方案**: 通过 Payload 首部的可选扩展区传递 Trace Context

```python
class TraceContextHeader:
    """
    Trace Context 嵌入格式 (Payload 首部)
    
    ┌─────────────────────────────────────────┐
    │ SOME/IP Header (固定32字节)             │
    ├─────────────────────────────────────────┤
    │ TraceContext (可选, 26字节)             │
    │ ├─ version: 1 byte (0x01)              │
    │ ├─ trace_id: 16 bytes (UUID)           │
    │ ├─ span_id: 8 bytes                    │
    │ ├─ flags: 1 byte (sampled, etc.)       │
    │ └─ reserved: 0 bytes (对齐)             │
    ├─────────────────────────────────────────┤
    │ 业务 Payload                            │
    └─────────────────────────────────────────┘
    """
    
    MAGIC_BYTES = b'\x5a\x5a'  # "ZZ" - tinySOA trace marker
    FORMAT_VERSION = 0x01
    TOTAL_SIZE = 26  # bytes (不含 magic 和 version)
    
    def __init__(
        self,
        trace_id: str = None,  # W3C Trace ID (16 bytes UUID)
        span_id: str = None,   # Span ID (8 bytes)
        sampled: bool = False,
        baggage: Optional[Dict] = None
    ):
        self.trace_id = trace_id or self._generate_trace_id()
        self.span_id = span_id or self._generate_span_id()
        self.sampled = sampled
        self.baggage = baggage or {}
    
    def encode(self) -> bytes:
        """
        编码为字节序列，嵌入到 Payload 首部
        """
        buf = bytearray(self.TOTAL_SIZE)
        
        # 位置 0: Format Version
        buf[0] = self.FORMAT_VERSION
        
        # 位置 1-16: Trace ID (UUID hex -> bytes)
        trace_id_bytes = bytes.fromhex(self.trace_id.replace('-', ''))
        buf[1:17] = trace_id_bytes
        
        # 位置 17-24: Span ID (8 bytes)
        span_id_bytes = bytes.fromhex(self.span_id)
        buf[17:25] = span_id_bytes
        
        # 位置 25: Flags
        flags = 0
        if self.sampled:
            flags |= 0x01  # Sampled flag
        buf[25] = flags
        
        return bytes(buf)
    
    @classmethod
    def decode(cls, data: bytes) -> "TraceContextHeader":
        """从 Payload 首部解码"""
        if len(data) < cls.TOTAL_SIZE:
            raise ValueError("Insufficient data for trace context")
        
        version = data[0]
        if version != cls.FORMAT_VERSION:
            raise ValueError(f"Unsupported trace context version: {version}")
        
        trace_id = data[1:17].hex()
        trace_id = f"{trace_id[0:8]}-{trace_id[8:12]}-{trace_id[12:16]}-{trace_id[16:20]}-{trace_id[20:32]}"
        
        span_id = data[17:25].hex()
        
        flags = data[25]
        sampled = bool(flags & 0x01)
        
        return cls(trace_id=trace_id, span_id=span_id, sampled=sampled)

class TraceContextInjector:
    """
    Trace Context 注入/提取器
    
    负责在 SOME/IP 请求中注入/提取 Trace Context
    """
    
    @staticmethod
    def inject(ctx: CallContext, payload: bytes) -> bytes:
        """
        将 Trace Context 注入到 Payload
        
        :param ctx: 调用上下文 (含 trace_id, span_id等)
        :param payload: 原始 payload
        :return: 带 Trace Context 的新 payload
        """
        trace_ctx = TraceContextHeader(
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            sampled=ctx.should_sample,
        )
        
        trace_header = trace_ctx.encode()
        # Payload 格式: [TraceContext(26B) | Original Payload]
        return trace_header + payload
    
    @staticmethod
    def extract(payload: bytes) -> Optional[TraceContextHeader]:
        """
        从 Payload 中提取 Trace Context
        
        :param payload: 完整 payload
        :return: 提取的 Trace Context，若不存在返回 None
        """
        if len(payload) < TraceContextHeader.TOTAL_SIZE:
            return None
        
        try:
            return TraceContextHeader.decode(payload[:TraceContextHeader.TOTAL_SIZE])
        except ValueError:
            return None

class TracingConfig:
    """追踪配置"""
    
    enabled: bool = True
    
    # 采样策略
    sampler_type: str = "adaptive"  # 或 "fixed_rate" / "always"
    sample_rate: float = 0.1  # 当 sampler_type="fixed_rate" 时使用
    
    # Trace Context 传播格式
    propagator: str = "w3c_trace_context"  # 或 "b3"
    
    # 导出配置
    exporter_type: str = "jaeger"  # 或 "otlp" / "zipkin"
    exporter_endpoint: str = "http://localhost:14268/api/traces"
    
    # 采样决策树 (优先级从高到低)
    sampling_rules = [
        # 规则1: 错误总是采样
        {"condition": "error_rate > 0.01", "sample": True},
        
        # 规则2: 特定方法总是采样 (调试用)
        {"condition": "method_id in [0x0001, 0x0002]", "sample": True},
        
        # 规则3: 根据头部 sampled flag (分布式追踪中的采样传播)
        {"condition": "parent_sampled == True", "sample": True},
        
        # 规则4: 默认固定比例采样
        {"condition": "random() < 0.1", "sample": True},
    ]
```

### 2.2 采样策略

```python
class SamplingDecision:
    """采样决策"""
    
    SAMPLE = 1      # 采样
    NOT_SAMPLE = 0  # 不采样

class AdaptiveSampler:
    """
    自适应采样器
    
    根据实时系统状态动态调整采样率
    """
    
    def __init__(self):
        self.error_rate = 0.0  # 当前错误率
        self.request_rate = 0.0  # 当前请求速率
        self.sample_rate = 0.01  # 动态采样率
    
    def should_sample(
        self,
        ctx: CallContext,
        parent_decision: Optional[int] = None  # 父请求的采样决策
    ) -> bool:
        """
        决策是否采样
        
        采样决策树:
          1. 若父请求已采样 (parent_decision=SAMPLE) → 采样 (传播)
          2. 若实时错误率 > 1% → 采样 (异常检测)
          3. 若否则按自适应概率采样
        """
        
        # 规则1: 采样传播 (W3C 标准)
        if parent_decision == SamplingDecision.SAMPLE:
            return True
        
        # 规则2: 错误采样
        if self.error_rate > 0.01:
            return True
        
        # 规则3: 自适应采样 (根据负载调整)
        # 高负载时降低采样率，低负载时提高
        adjusted_rate = self._adjust_rate(self.request_rate)
        return random.random() < adjusted_rate
    
    def _adjust_rate(self, request_rate: float) -> float:
        """根据请求速率调整采样率"""
        # 目标: 每秒采样 100 条 trace
        target_traces_per_sec = 100
        
        if request_rate == 0:
            return 0.1
        
        adjusted = min(1.0, target_traces_per_sec / request_rate)
        return max(0.001, adjusted)  # 最小0.1%采样
    
    async def update_metrics(self, metrics: Dict):
        """定期更新指标 (由监控系统调用)"""
        self.error_rate = metrics.get('error_rate', 0.0)
        self.request_rate = metrics.get('request_rate', 0.0)
```

## 3. 日志

- 结构化：JSON 行日志，包含时间戳、级别、组件、请求摘要、耗时、结果。
- 关联：在日志中携带 TraceID/SpanID 以便串联。
- 等级：可动态调整日志级别；对高频路径注意采样与降噪。

## 4. 报警与 SLO（现实化目标）

### 4.1 现实的 SLO 目标

**原设计问题**: 
- P95 ≤ 10ms (同时包含网络RTT、序列化、业务处理) - **不可达**
- 99.9% 投递率 (使用UDP) - **不可达**

**改进方案**: 分拓扑分类的现实目标

```python
class SLODefinition:
    """
    服务级别目标 (SLO)
    
    根据网络拓扑分别定义目标
    """
    
    # Phase 2 (多进程) 目标
    PHASE_2_LOCAL_PROCESS = {
        "description": "同机进程间通信",
        "p50_latency_ms": 1,
        "p95_latency_ms": 3,
        "p99_latency_ms": 5,
        "success_rate": 0.999,  # 99.9%
        "notes": "不含网络开销"
    }
    
    PHASE_2_SAME_NETWORK = {
        "description": "同局域网服务间通信",
        "p50_latency_ms": 5,
        "p95_latency_ms": 20,
        "p99_latency_ms": 50,
        "success_rate": 0.995,  # 99.5% (UDP可能丢包)
        "notes": "含一次网络RTT, 典型延迟5-20ms"
    }
    
    PHASE_3_WITH_INTERCEPTORS = {
        "description": "包含完整拦截器链的调用",
        "p50_latency_ms": 8,
        "p95_latency_ms": 25,
        "p99_latency_ms": 100,
        "success_rate": 0.999,  # 99.9%
        "notes": "含 Tracing/Metrics/Retry/RateLimit 等开销"
    }
    
    PHASE_3_WITH_RETRIES = {
        "description": "自动重试的平均延迟",
        "p50_latency_ms": 10,
        "p95_latency_ms": 50,
        "p99_latency_ms": 200,
        "success_rate": 0.9999,  # 99.99%
        "notes": "重试提高成功率但增加延迟"
    }

class SLOMonitoring:
    """
    SLO 监控与告警
    """
    
    async def evaluate_slo(
        self,
        service_id: int,
        method_id: int,
        time_window_s: int = 300  # 5分钟窗口
    ) -> Dict[str, Any]:
        """
        评估某个服务方法是否满足 SLO
        
        :return: {
            "p50": 5.2,
            "p95": 22.1,
            "p99": 89.5,
            "success_rate": 0.9985,
            "slo_violation": ["p95_exceeded"],  # 违反哪些SLO项
            "recommendation": "Consider increasing replicas or optimizing serialization"
        }
        """
        
        metrics = await self._collect_metrics(
            service_id, method_id, time_window_s
        )
        
        target_slo = self._get_slo_for_topology()
        violations = []
        
        # 检查各个指标
        if metrics['p95'] > target_slo['p95_latency_ms']:
            violations.append("p95_exceeded")
        
        if metrics['p99'] > target_slo['p99_latency_ms']:
            violations.append("p99_exceeded")
        
        if metrics['success_rate'] < target_slo['success_rate']:
            violations.append("success_rate_degraded")
        
        return {
            "p50": metrics['p50'],
            "p95": metrics['p95'],
            "p99": metrics['p99'],
            "success_rate": metrics['success_rate'],
            "slo_violations": violations,
            "recommendation": self._generate_recommendation(violations, metrics)
        }

class SLOAlert:
    """
    SLO 告警规则
    """
    
    ALERTS = [
        {
            "name": "high_error_rate",
            "condition": "error_rate > 0.01",  # 错误率超过1%
            "severity": "critical",
            "action": "page_on_call_engineer"
        },
        {
            "name": "p95_latency_degradation",
            "condition": "p95_latency_ms > slo.p95 * 1.5",  # 超过目标50%
            "severity": "warning",
            "action": "log_alert"
        },
        {
            "name": "success_rate_below_target",
            "condition": "success_rate < slo.success_rate",
            "severity": "critical",
            "action": "page_on_call_engineer"
        },
        {
            "name": "circuit_breaker_open",
            "condition": "circuit_breaker_state == 'open'",
            "severity": "critical",
            "action": "investigate_downstream_service"
        },
        {
            "name": "config_change_failure",
            "condition": "config_change_rollback_count > 3 in 1h",
            "severity": "warning",
            "action": "review_recent_config_changes"
        }
    ]
```

### 4.2 典型告警场景

```yaml
alerts:
  - name: RPC_HIGH_LATENCY
    expr: histogram_quantile(0.95, rpc_latency_ms) > 50
    for: 5m
    severity: warning
    annotations:
      summary: "RPC P95 latency exceeds 50ms"
      runbook: "docs/slo/high_latency_runbook.md"

  - name: RPC_ERROR_SPIKE
    expr: rate(rpc_errors_total[5m]) > 0.01
    for: 1m
    severity: critical
    annotations:
      summary: "RPC error rate exceeds 1%"
      runbook: "docs/slo/error_spike_runbook.md"

  - name: SERVICE_DISCOVERY_LATENCY
    expr: sd_discovery_latency_ms > 1000
    for: 1m
    severity: warning
    annotations:
      summary: "Service discovery taking longer than 1s"

  - name: CIRCUIT_BREAKER_OPEN
    expr: circuit_breaker_state{service_id="0x1234"} == 1
    for: 10s
    severity: critical
    annotations:
      summary: "Circuit breaker open for service"
      runbook: "Investigate downstream service health"

  - name: MEMORY_LEAK_DETECTED
    expr: go_memstats_alloc_bytes > threshold
    for: 30m
    severity: warning
```
