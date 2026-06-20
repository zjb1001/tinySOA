# tinySOA 核心组件设计

## 1. 服务注册中心 (Service Registry)

### 1.1 职责
- **本地服务视图 (Local Service View)**: 维护通过 SD 协议发现的远程服务列表，而非中心化的注册服务器。
- **服务元数据缓存**: 缓存服务的配置、版本、端点等信息，减少网络查询。
- **服务状态跟踪**: 实时更新服务的在线/离线状态 (TTL 管理)。
- **本地服务发布**: 管理本节点提供的服务实例信息。

### 1.2 数据结构

```python
@dataclass
class ServiceMetadata:
    """服务元数据"""
    service_id: int
    instance_id: int
    version_major: int
    version_minor: int
    service_name: str
    description: str
    methods: Dict[int, MethodMetadata]
    eventgroups: Dict[int, EventgroupMetadata]
    created_at: datetime
    tags: Dict[str, str]

@dataclass
class ServiceInstance:
    """服务实例"""
    metadata: ServiceMetadata
    endpoint: Tuple[str, int] # IP, Port
    protocol: str # UDP/TCP
    status: ServiceStatus  # STARTING, RUNNING, STOPPING, STOPPED
    health: HealthStatus   # HEALTHY, UNHEALTHY, UNKNOWN
    last_heartbeat: datetime
    ttl: int # Time To Live in seconds
    statistics: ServiceStatistics
```

### 1.3 接口设计

```python
class ServiceRegistry:
    async def register_local(self, service: ServiceMetadata, endpoint: Tuple[str, int]) -> str:
        """注册本地服务，触发 SD Offer"""
        
    async def unregister_local(self, registration_id: str) -> None:
        """注销本地服务，触发 SD StopOffer"""
        
    async def process_sd_message(self, message: SDMessage) -> None:
        """处理收到的 SD 报文 (Offer/Find/Subscribe)，更新本地视图"""

    async def find_service(
        self, 
        service_id: Optional[int] = None,
        service_name: Optional[str] = None,
        min_version: Optional[Tuple[int, int]] = None
    ) -> List[ServiceInstance]:
        """查找服务 (优先查缓存，未命中则触发 SD Find)"""
        
    def watch(self, service_id: int) -> AsyncIterator[ServiceEvent]:
        """监听服务上下线变化"""
```

### 1.4 实现要点
- **去中心化设计**: 基于 SOME/IP-SD 协议，不依赖中心节点。
- **TTL 管理**: 定期清理超时的服务实例 (SD Offer 包含 TTL)。
- **事件驱动**: 内部通过 InternalEventBus 通知服务状态变更。
- **多索引查询**: 支持按 ID、名称快速检索。

### 1.5 一致性模型

#### 1.5.1 本地视图与分布式一致性

**一致性边界定义**:

```
强一致性 (Strong Consistency - 需要)
├─ 本地服务注册/注销
│  └─ 双写: (1) LocalRegistry (2) SD OfferService/StopOfferService
│  └─ 原子性: 两个写操作必须全部成功或全部失败
│  └─ 失败处理: 若SD写失败，需自动重试或告警
│
├─ 配置变更的版本管理
│  └─ 每个变更带版本号 (config_version)
│  └─ 服务端原子性应用 (要么全部新配置，要么全部旧配置)
│  └─ 不允许部分实例应用新配置、部分旧配置
│
└─ 幂等操作列表 (可安全重试)
   ├─ FindService (查询操作，无副作用)
   ├─ GetServiceMetadata (查询操作)
   ├─ SubscribeEventgroup (重复订阅无害，带去重)
   └─ ReportHealth (健康状态报告)

最终一致性 (Eventual Consistency - 允许)
├─ 远程服务发现缓存
│  └─ TTL机制保证最坏情况下的一致性时间
│  └─ 过期前不同节点对服务可用性有不同视图 (可接受)
│  └─ 容忍窗口: TTL秒内的视图差异
│
├─ 事件通知传递
│  └─ 事件可能丢失 (UDP特性)
│  └─ 事件可能重复 (重试机制)
│  └─ 接收端需支持幂等消费或去重
│
└─ 实例健康度评分
   └─ 不同客户端对同一实例的健康评分不同
   └─ 这是可接受的，客户端各自做LB决策

非一致性容错 (Tolerance Specification)
├─ 网络分区: 分区两侧的服务发现缓存各自独立
│  └─ TTL到期后，无法感知分区另一侧的新实例
│  └─ 但分区内通信继续正常
│
├─ SD消息丢失: 需要重传机制
│  └─ Find -> Offer 的应答是单向UDP，可丢失
│  └─ 应对: 客户端定期重发FindService
│  └─ Subscribe -> Notify 的持续订阅需心跳
│
└─ 时钟不同步: TTL计时可能不精确
   └─ 应对: TTL值设置较大冗余 (如20s而非5s)
```

#### 1.5.2 二阶段提交流程 (双写一致性)

对于本地服务注册，使用以下流程确保与SD协议的一致:

```
步骤 1: 本地注册
  input: ServiceMetadata
  → LocalRegistry.add(metadata)
  → 状态: PENDING_SD_OFFER
  ✓ 本地已知，但还未对外广播

步骤 2: SD广播
  → SD.offerService(service_id, instance_id, endpoint, ttl)
  → 等待确认 (SD实际上是UDP发送，无ACK机制)
  → 等待超时 T1 (如100ms，以验证本地端口绑定)
  ✓ 对外可见

步骤 3: 成功状态
  → LocalRegistry.update_status(REGISTERED)
  → 发出 InternalEvent: ServiceOffered
  ✗ 失败回滚
    → LocalRegistry.remove(metadata)
    → 异常告警
```

#### 1.5.3 查询命中策略

```
find_service(service_id, filter) {
  // 优先查本地缓存 (Registry Local View)
  cached = LocalRegistry.get(service_id)
  
  if cached && not_expired(cached):
    return cached  // 快速路径
  
  // 缓存未命中或已过期，触发SD Find
  if is_expiring(cached) or not cached:
    sd_result = await SD.findService(service_id, TIMEOUT=300ms)
    // 并行: 更新本地缓存，无需等待完成
    asyncio.create_task(LocalRegistry.refresh(sd_result))
    return cached or sd_result  // 返回缓存或新结果
  
  return empty
}
```

## 2. 连接管理器 (Connection Manager)

### 2.1 职责
- **传输层抽象**: 统一管理 UDP Endpoint 和 TCP 连接。
- **连接复用 (Connection Pooling)**: 针对 TCP 连接维护连接池，避免频繁握手。
- **多路复用 (Multiplexing)**: 在同一连接上并发处理多个请求/响应 (基于 Session ID)。
- **故障恢复**: 自动处理断线重连、网络抖动。
- **Socket 优化**: 配置 SO_REUSEADDR, SO_REUSEPORT, TCP_NODELAY 等选项。

### 2.2 接口设计

```python
class ConnectionManager:
    async def get_transport(self, endpoint: Tuple[str, int, str]) -> Transport:
        """获取到指定端点的传输通道 (TCP/UDP)，支持复用"""
        
    async def send_request(self, endpoint: Tuple[str, int, str], message: Message) -> None:
        """发送请求消息，自动处理连接建立"""
        
    def register_listener(self, service_id: int, listener: Callable) -> None:
        """注册消息接收回调 (按 Service ID 分发)"""
        
    async def close_idle_connections(self, timeout: int) -> None:
        """清理空闲 TCP 连接"""
```

## 3. 服务发现 (Service Discovery)

### 2.1 职责
- 与 SOME/IP SD 协议集成
- 自动发现网络上的服务
- 维护远程服务的可用性
- 处理服务订阅

### 2.2 核心流程

```
┌──────────────┐
│ Start Service│
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ Offer Service    │ ─────► SD OfferService Message
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Listen for       │ ◄───── SD FindService Message
│ FindService      │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Send OfferService│ ─────► SD OfferService Response
│ Response         │
└──────────────────┘
```

### 2.3 接口设计

```python
class ServiceDiscovery:
    def __init__(self, registry: ServiceRegistry):
        self.registry = registry
        self.sd_protocol: ServiceDiscoveryProtocol
        
    async def start(self) -> None:
        """启动服务发现"""
        
    async def stop(self) -> None:
        """停止服务发现"""
        
    async def offer_service(
        self, 
        service_id: int, 
        instance_id: int,
        endpoint: Tuple[str, int]
    ) -> None:
        """提供服务"""
        
    async def stop_offer_service(
        self, 
        service_id: int, 
        instance_id: int
    ) -> None:
        """停止提供服务"""
        
    async def find_service(
        self, 
        service_id: int,
        instance_id: Optional[int] = None
    ) -> List[ServiceEndpoint]:
        """查找服务"""
        
    async def subscribe_eventgroup(
        self,
        service_id: int,
        instance_id: int,
        eventgroup_id: int
    ) -> None:
        """订阅事件组"""
```

### 2.4 实现要点
- 封装 ServiceDiscoveryProtocol
- 自动处理 OfferService/StopOfferService
- 维护服务发现缓存
- TTL 过期自动清理

## 3. 服务代理 (Service Proxy)

### 3.1 职责
- 提供远程服务的本地代理
- 处理请求序列化和响应反序列化
- 实现负载均衡和故障转移
- 管理连接池

### 3.2 代理模式

```python
class ServiceProxy:
    """服务代理基类"""
    
    def __init__(
        self, 
        service_id: int,
        instance_id: Optional[int] = None,
        registry: ServiceRegistry = None,
        serializer: Serializer = None
    ):
        self.service_id = service_id
        self.instance_id = instance_id
        self.registry = registry or get_default_registry()
        self.serializer = serializer or JsonSerializer()
        
    async def _call_method(
        self,
        method_id: int,
        args: tuple,
        kwargs: dict,
        timeout: float = 5.0
    ) -> Any:
        """调用远程方法"""
        # 1. 序列化参数
        payload = self.serializer.serialize({"args": args, "kwargs": kwargs})
        
        # 2. 查找服务实例
        instances = await self.registry.find_service(
            service_id=self.service_id,
            instance_id=self.instance_id
        )
        
        # 3. 负载均衡选择实例
        instance = self._select_instance(instances)
        
        # 4. 发送请求
        response = await self._send_request(
            instance.endpoint,
            method_id,
            payload,
            timeout
        )
        
        # 5. 反序列化响应
        return self.serializer.deserialize(response.payload)
```

### 3.3 动态代理生成

```python
def create_proxy(service_interface: Type) -> ServiceProxy:
    """
    根据服务接口自动生成代理类
    
    Example:
        class ITimeService:
            @method(method_id=1)
            async def get_time(self) -> str: ...
            
            @method(method_id=2)
            async def set_time(self, time: str) -> None: ...
        
        proxy = create_proxy(ITimeService)
        time = await proxy.get_time()
    """
    # 使用元类或类装饰器动态生成代理方法
```

### 3.4 完整的负载均衡设计

#### 3.4.1 负载均衡接口

```python
class HealthScore:
    """实例健康度评分"""
    availability: float      # [0, 1] - 可用性 (1 - error_rate)
    latency_ratio: float     # [0, 1] - 延迟比率 (measured / baseline)
    connection_load: float   # [0, 1] - 当前连接占用比
    score: float             # [0, 1] - 综合评分
    timestamp: datetime      # 评分时间
    
    def compute_score(self, weights: Dict[str, float] = None) -> float:
        """
        计算综合评分
        默认权重: availability(40%) + (1-latency_ratio)(40%) + (1-connection_load)(20%)
        """
        w = weights or {"availability": 0.4, "latency": 0.4, "load": 0.2}
        return (
            self.availability * w["availability"] +
            (1 - self.latency_ratio) * w["latency"] +
            (1 - self.connection_load) * w["load"]
        )

class LoadBalancer(ABC):
    """
    负载均衡器基类
    
    职责:
      - 维护实例健康度评分
      - 根据策略选择实例
      - 记录调用成功/失败以更新评分
    """
    
    @abstractmethod
    async def select(
        self, 
        instances: List[ServiceInstance],
        context: RequestContext = None
    ) -> ServiceInstance:
        """
        选择一个实例
        
        :param instances: 可用实例列表 (已过滤健康度)
        :param context: 请求上下文 (用于基于上下文的选择)
        :return: 选中的实例
        """
        pass
    
    @abstractmethod
    async def record_result(
        self,
        instance: ServiceInstance,
        success: bool,
        latency_ms: float
    ) -> None:
        """
        记录调用结果，更新实例评分
        
        :param instance: 被调用的实例
        :param success: 是否成功
        :param latency_ms: 调用耗时(毫秒)
        """
        pass
    
    def get_health_score(self, instance: ServiceInstance) -> HealthScore:
        """获取实例的当前健康度评分"""
        pass
```

#### 3.4.2 内置负载均衡实现

```python
class RoundRobinLoadBalancer(LoadBalancer):
    """
    轮询负载均衡
    
    特点: 简单、公平，但不考虑实例性能差异
    使用场景: 所有实例性能相近的均匀部署
    """
    def __init__(self, enable_health_filter: bool = True):
        self.counter = 0
        self.enable_health_filter = enable_health_filter
    
    async def select(self, instances, context=None):
        # 过滤掉极不健康的实例 (score < 0.1)
        if self.enable_health_filter:
            healthy = [i for i in instances if self.get_health_score(i).score > 0.1]
            instances = healthy or instances
        
        self.counter = (self.counter + 1) % len(instances)
        return instances[self.counter]

class RandomLoadBalancer(LoadBalancer):
    """
    随机负载均衡
    
    特点: 简单随机，避免热点
    使用场景: 短连接、批处理任务
    """
    async def select(self, instances, context=None):
        return random.choice(instances)

class LatencyWeightedLoadBalancer(LoadBalancer):
    """
    延迟加权负载均衡 (实时性能导向)
    
    特点: 根据实时延迟选择最快的实例，适应性强
    权重公式: weight = 1 / (latency_p50 + epsilon)
    使用场景: 性能敏感的服务、实例性能差异大
    """
    def __init__(self, window_size: int = 100):
        self.latency_history = {}  # {instance_id: deque[latency]}
        self.window_size = window_size
    
    async def select(self, instances, context=None):
        if not instances:
            raise NoAvailableInstanceError()
        
        # 计算每个实例的权重
        weights = []
        for inst in instances:
            score = self.get_health_score(inst)
            # 延迟越低，权重越高; 如果无历史，给予中等权重
            latency_p50 = self._get_p50_latency(inst.id) or 10.0
            weight = 1.0 / (latency_p50 + 0.1)  # 避免除以0
            weight *= score.score  # 乘以整体健康度
            weights.append(weight)
        
        # 按权重随机选择
        total = sum(weights)
        if total == 0:
            return random.choice(instances)
        
        r = random.uniform(0, total)
        cumsum = 0
        for inst, w in zip(instances, weights):
            cumsum += w
            if r <= cumsum:
                return inst
        return instances[-1]

class ConsistentHashLoadBalancer(LoadBalancer):
    """
    一致性哈希负载均衡 (会话亲和性)
    
    特点: 同一客户端请求总是路由到同一实例
    优点: 利用实例本地缓存，减少缓存失效
    缺点: 某实例故障时才重新哈希，可能出现不均衡
    使用场景: 有状态服务、需要会话亲和性
    """
    def __init__(self, replica_count: int = 160):
        self.ring = {}
        self.replica_count = replica_count
    
    async def select(self, instances, context=None):
        # 重新构建哈希环 (实例集合变化时)
        key = context.client_address if context else "default"
        hash_val = self._consistent_hash(key, instances)
        return hash_val

class AdaptiveLoadBalancer(LoadBalancer):
    """
    自适应负载均衡 (推荐用于生产)
    
    特点: 根据实时系统状态自动选择最优策略
    工作流程:
      1. 收集指标 (延迟、错误率、连接数)
      2. 计算健康度评分
      3. 根据评分分布选择策略:
         - 评分均匀 → RoundRobin (所有实例都好)
         - 评分差异大 → LatencyWeighted (明显有快/慢机)
         - 有会话需求 → ConsistentHash (从context检测)
    """
    def __init__(self):
        self.strategies = {
            "round_robin": RoundRobinLoadBalancer(),
            "latency_weighted": LatencyWeightedLoadBalancer(),
            "consistent_hash": ConsistentHashLoadBalancer(),
        }
        self.current_strategy = "round_robin"
    
    async def select(self, instances, context=None):
        # 根据实例评分分布调整策略
        scores = [self.get_health_score(i).score for i in instances]
        variance = self._compute_variance(scores)
        
        if variance > 0.3:
            # 性能差异明显，使用延迟加权
            self.current_strategy = "latency_weighted"
        else:
            # 性能接近，轮询足够
            self.current_strategy = "round_robin"
        
        return await self.strategies[self.current_strategy].select(instances, context)

class InstanceFilterChain:
    """
    实例过滤链 (选择前的预处理)
    
    职责: 根据多个条件过滤实例
    """
    
    def __init__(self):
        self.filters = []
    
    def add_filter(self, filter_fn: Callable[[ServiceInstance], bool]):
        """添加过滤条件"""
        self.filters.append(filter_fn)
    
    def filter_instances(self, instances: List[ServiceInstance]) -> List[ServiceInstance]:
        """应用所有过滤条件"""
        for f in self.filters:
            instances = [i for i in instances if f(i)]
        return instances

# 预定义的过滤条件
class InstanceFilters:
    
    @staticmethod
    def health_threshold(min_score: float = 0.5):
        """健康度阈值过滤"""
        def f(inst):
            return get_health_score(inst).score >= min_score
        return f
    
    @staticmethod
    def version_match(required_version: Tuple[int, int]):
        """版本匹配过滤"""
        def f(inst):
            return (inst.metadata.version_major, inst.metadata.version_minor) >= required_version
        return f
    
    @staticmethod
    def zone_affinity(preferred_zone: str):
        """区域亲和性过滤 (优先同机房)"""
        def f(inst):
            inst_zone = inst.tags.get("zone", "unknown")
            if inst_zone == preferred_zone:
                return True
            return False
        return f
    
    @staticmethod
    def exclude_zones(excluded_zones: List[str]):
        """排除某些区域"""
        def f(inst):
            inst_zone = inst.tags.get("zone", "unknown")
            return inst_zone not in excluded_zones
        return f
```

#### 3.4.3 故障转移策略

```python
class FailoverStrategy:
    """
    故障转移策略
    
    当实例调用失败时，自动切换到其他实例
    """
    
    async def execute_with_failover(
        self,
        service_id: int,
        method_id: int,
        args: tuple,
        proxy: ServiceProxy,
        max_retries: int = 3
    ) -> Any:
        """
        带故障转移的RPC调用
        
        :param service_id: 服务ID
        :param method_id: 方法ID
        :param args: 参数
        :param proxy: 服务代理
        :param max_retries: 最大重试次数 (跨实例)
        :return: 调用结果
        
        流程:
          1. 获取所有可用实例列表
          2. 按LB策略选择实例
          3. 尝试调用
          4. 调用失败 → 标记实例为不健康 → 选择下一个实例
          5. 重复直到成功或达到最大重试次数
        """
        
        instances = await proxy.registry.find_service(service_id)
        if not instances:
            raise ServiceUnavailableError(f"No instance found for service {service_id}")
        
        last_error = None
        attempted_instances = set()
        
        for attempt in range(max_retries):
            try:
                # 获取可用实例 (排除已失败的)
                available = [i for i in instances if i.id not in attempted_instances]
                if not available:
                    break
                
                # LB选择实例
                instance = await proxy.load_balancer.select(available)
                attempted_instances.add(instance.id)
                
                # 调用
                result = await proxy._call_method(method_id, args, instance)
                
                # 成功 → 记录到LB
                await proxy.load_balancer.record_result(instance, success=True, latency_ms=0)
                return result
                
            except (TimeoutError, ConnectionError, RemoteServiceError) as e:
                last_error = e
                # 记录失败
                await proxy.load_balancer.record_result(instance, success=False, latency_ms=0)
                # 标记实例不健康
                await proxy.registry.update_health(instance.id, HealthStatus.UNHEALTHY)
                continue
        
        raise FailoverExhaustedError(
            f"Failover exhausted after {max_retries} attempts. Last error: {last_error}"
        )
```

## 4. 事件总线 (Event Bus)

### 4.1 职责
- 实现发布/订阅模式
- 事件路由和分发
- 支持事件过滤
- 事件持久化（可选）

### 4.2 核心概念

```python
@dataclass
class Event:
    """事件"""
    event_id: int
    event_name: str
    source_service: str
    timestamp: datetime
    data: Any
    metadata: Dict[str, Any]

class EventHandler(Protocol):
    """事件处理器"""
    async def __call__(self, event: Event) -> None: ...

class EventFilter(Protocol):
    """事件过滤器"""
    def __call__(self, event: Event) -> bool: ...
```

### 4.3 接口设计

```python
class EventBus:
    async def publish(
        self, 
        event_id: int,
        data: Any,
        eventgroup_id: Optional[int] = None
    ) -> None:
        """发布事件"""
        
    async def subscribe(
        self,
        event_id: int,
        handler: EventHandler,
        filter: Optional[EventFilter] = None
    ) -> str:
        """订阅事件，返回订阅 ID"""
        
    async def unsubscribe(self, subscription_id: str) -> None:
        """取消订阅"""
        
    async def subscribe_eventgroup(
        self,
        service_id: int,
        instance_id: int,
        eventgroup_id: int,
        handler: EventHandler
    ) -> str:
        """订阅事件组"""
```

### 4.4 实现要点
- 基于 SimpleEventgroup 封装
- 支持本地和远程事件
- 异步事件分发
- 事件队列缓冲

## 5. 生命周期管理器 (Lifecycle Manager)

### 5.1 服务生命周期

```
┌─────────┐
│ CREATED │
└────┬────┘
     │ initialize()
     ▼
┌─────────┐
│STARTING │
└────┬────┘
     │ start()
     ▼
┌─────────┐
│ RUNNING │
└────┬────┘
     │ stop()
     ▼
┌─────────┐
│STOPPING │
└────┬────┘
     │ cleanup()
     ▼
┌─────────┐
│ STOPPED │
└─────────┘
```

### 5.2 接口设计

```python
class LifecycleManager:
    async def register_service(
        self, 
        service: 'SOAService'
    ) -> None:
        """注册服务到生命周期管理"""
        
    async def start_service(self, service_name: str) -> None:
        """启动服务"""
        
    async def stop_service(self, service_name: str) -> None:
        """停止服务"""
        
    async def start_all(self) -> None:
        """启动所有服务"""
        
    async def stop_all(self, graceful: bool = True) -> None:
        """停止所有服务"""
        
    async def wait_for_termination(self) -> None:
        """等待终止信号"""

class SOAService(ABC):
    """SOA 服务基类"""
    
    @abstractmethod
    async def initialize(self) -> None:
        """初始化"""
        
    @abstractmethod
    async def start(self) -> None:
        """启动"""
        
    @abstractmethod
    async def stop(self) -> None:
        """停止"""
        
    @abstractmethod
    async def cleanup(self) -> None:
        """清理资源"""
```

## 6. 拦截器链 (Interceptor Chain)

### 6.1 拦截器模式

```python
class Interceptor(ABC):
    """拦截器基类"""
    
    @abstractmethod
    async def before_request(
        self, 
        context: RequestContext
    ) -> RequestContext:
        """请求前拦截"""
        
    @abstractmethod
    async def after_response(
        self, 
        context: ResponseContext
    ) -> ResponseContext:
        """响应后拦截"""
        
    @abstractmethod
    async def on_error(
        self, 
        context: RequestContext, 
        error: Exception
    ) -> None:
        """错误处理"""

class InterceptorChain:
    def __init__(self):
        self.interceptors: List[Interceptor] = []
        
    def add(self, interceptor: Interceptor) -> None:
        """添加拦截器"""
        
    async def execute(
        self, 
        request: Request, 
        handler: Callable
    ) -> Response:
        """执行拦截器链"""
```

### 6.2 内置拦截器

```python
class LoggingInterceptor(Interceptor):
    """日志拦截器"""
    
class MetricsInterceptor(Interceptor):
    """度量拦截器"""
    
class AuthenticationInterceptor(Interceptor):
    """认证拦截器"""
    
class RateLimitInterceptor(Interceptor):
    """限流拦截器"""
    
class CircuitBreakerInterceptor(Interceptor):
    """熔断器拦截器"""
```

## 7. 配置管理器 (Configuration Manager)

### 7.3 配置结构

```yaml
# tinysoa.yaml
framework:
  name: "my-app"
  version: "1.0.0"
  
discovery:
  multicast_group: "224.224.224.245"
  multicast_port: 30490
  announce_interval: 3.0
  
services:
  - name: "TimeService"
    service_id: 0xB0A7
    instance_id: 1
    endpoints:
      - protocol: udp
        address: "0.0.0.0"
        port: 30509
        
serialization:
  default: json
  formats:
    - json
    - msgpack
    
monitoring:
  enabled: true
  metrics_port: 9090
```

### 7.4 接口设计

```python
class ConfigurationManager:
    async def load(self, config_path: str) -> None:
        """加载配置"""
        
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        
    async def reload(self) -> None:
        """重新加载配置"""
        
    def watch(self, key: str) -> AsyncIterator[Any]:
        """监听配置变化"""
```

## 8. 监控与度量 (Monitoring & Metrics)

### 8.1 度量指标

```python
@dataclass
class ServiceMetrics:
    """服务度量"""
    request_count: int
    error_count: int
    avg_response_time: float
    p95_response_time: float
    p99_response_time: float
    active_connections: int

class MetricsCollector:
    def record_request(
        self, 
        service_id: int, 
        method_id: int,
        duration: float,
        success: bool
    ) -> None:
        """记录请求"""
        
    def get_metrics(self, service_id: int) -> ServiceMetrics:
        """获取度量数据"""
        
    async def export_prometheus(self) -> str:
        """导出 Prometheus 格式"""
```

### 8.2 健康检查

```python
class HealthCheck:
    async def check(self) -> HealthStatus:
        """执行健康检查"""
        
    def register_check(
        self, 
        name: str, 
        checker: Callable[[], Awaitable[bool]]
    ) -> None:
        """注册健康检查项"""
```

## 9. 模块依赖关系

```
LifecycleManager
    ↓
ServiceRegistry ←→ ServiceDiscovery
    ↓                      ↓
ServiceProxy          EventBus
    ↓                      ↓
InterceptorChain      Monitoring
    ↓
ConfigurationManager
```

## 10. 线程模型

- 单线程异步模型（asyncio event loop）
- 所有 I/O 操作异步化
- CPU 密集型任务可选线程池
- 避免阻塞操作
