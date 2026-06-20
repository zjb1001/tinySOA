# 服务生命周期管理设计

## 1. 状态机

- **状态流转**: `STARTING` → `RUNNING` ↔ `DEGRADED` → `STOPPING` → `STOPPED`
- **状态定义**:
    - `STARTING`: 初始化资源，绑定端口，尚未对外服务。
    - `RUNNING`: 正常服务中，所有依赖健康。
    - `DEGRADED`: 服务可用，但部分非关键依赖不可用或性能下降（降级模式）。
    - `STOPPING`: 正在关闭，不再接受新请求，等待旧请求处理完毕。
    - `STOPPED`: 已完全停止，资源已释放。
- `UNHEALTHY` 为健康检查结果，可能触发从 `RUNNING` 到 `DEGRADED` 或重启。

## 2. 启动流程（改进版本）

1. **加载配置**：解析文件与环境变量，构建运行时配置。
2. **初始化组件**：Registry、SD、拦截器、编解码器、日志、指标导出、内部事件总线。
3. **绑定传输**：创建 `SOMEIPDatagramProtocol`（参见 `src/someip/sd.py`）。
4. **依赖检查**: 
   - 触发内部事件 `ServiceInitializing`
   - 等待声明的依赖服务可用 (通过SD发现)
   - 超时则进入降级模式 (DEGRADED)
5. **服务注册**：在本地 Registry 登记，二阶段提交到SD (见02章节一致性模型)。
6. **健康检查**：暴露健康探针（内部事件或本地检查函数）。
7. **Ready**：触发内部事件 `ServiceReady`，进入 `RUNNING`。

### 启动流程代码伪型：

```python
async def initialize(self, config: ServiceConfig):
    """初始化服务"""
    self.state = ServiceState.STARTING
    try:
        # 1. 加载配置
        self.config = await load_config(config)
        
        # 2. 初始化组件
        self.registry = LocalRegistry()
        self.sd = ServiceDiscovery(self.registry)
        self.event_bus = InternalEventBus()  # 内部事件总线
        
        # 3. 发出初始化事件
        await self.event_bus.publish(
            InternalEvent(type=EventType.SERVICE_INITIALIZING, service_id=self.service_id)
        )
        
        # 4. 依赖检查
        await self._check_dependencies()
        
        # 5. 注册本地服务 (二阶段提交)
        await self._register_service()
        
        # 6. 健康检查
        health = await self._perform_health_check()
        
        # 7. 就绪
        self.state = ServiceState.RUNNING
        await self.event_bus.publish(
            InternalEvent(type=EventType.SERVICE_READY, service_id=self.service_id)
        )
        
    except Exception as e:
        self.state = ServiceState.DEGRADED
        await self.event_bus.publish(
            InternalEvent(type=EventType.SERVICE_DEGRADED, error=str(e))
        )
        raise
```

## 3. 停止流程（优雅关闭）

1. **进入 `STOPPING`**：
    - 标记状态，拒绝新的 RPC 请求（返回特定错误码）。
    - 允许正在处理的请求继续执行（设置超时时间，如 5s）。
2. **停止 SD Offer**: 发送 SD StopOffer 消息，通知客户端服务下线。
3. **取消订阅**：主动取消对其他服务的订阅，停止事件循环任务。
4. **注销服务**：从本地 Registry 注销。
5. **释放资源**：关闭传输连接、清理缓存、释放文件句柄。
6. **进入 `STOPPED`**。

## 4. 依赖管理（完整设计）

### 4.1 依赖声明

```python
@Service(
    service_id=0x1234,
    instance_id=0x0001,
    version=(1, 0),
    depends_on=[
        # 绝对依赖 (启动前必须可用)
        ServiceDependency(
            service_id=0x5678,
            version=(1, 0),
            required=True,
            timeout_s=10  # 等待超时
        ),
        # 可选依赖 (启动前可不可用，但可用时优先使用)
        ServiceDependency(
            service_id=0x9999,
            required=False
        )
    ]
)
class MyService:
    pass
```

### 4.2 启动顺序管理

```python
class DependencyResolver:
    """
    依赖解析器 - 管理多个服务的启动顺序
    
    算法：拓扑排序 + 并行启动
    """
    
    def __init__(self, services: List[ServiceMetadata]):
        self.services = services
        self.graph = self._build_dependency_graph()
    
    async def start_all(self) -> None:
        """
        启动所有服务，尊重依赖关系
        
        1. 拓扑排序得到启动序列
        2. 按序列启动服务
        3. 等待依赖可用后再启动后续服务
        4. 若出现循环依赖，拒绝启动并告警
        """
        
        topo_order = self._topological_sort()
        
        if not topo_order:
            raise DependencyCycleError("Circular dependency detected")
        
        # 按拓扑序启动
        for level in topo_order:
            # 同一层的服务可并行启动
            await asyncio.gather(*[
                self._start_service(svc) for svc in level
            ])
    
    async def _start_service(self, service: ServiceMetadata) -> None:
        """启动单个服务"""
        required_deps = [d for d in service.dependencies if d.required]
        
        # 等待依赖可用
        try:
            await self._wait_for_dependencies(required_deps, timeout=10)
        except TimeoutError:
            raise DependencyTimeoutError(
                f"Service {service.service_id} timed out waiting for dependencies"
            )
        
        # 启动服务
        await service.start()
    
    async def _wait_for_dependencies(
        self,
        dependencies: List[ServiceDependency],
        timeout: float
    ) -> None:
        """
        等待所有依赖可用
        
        通过 InternalEventBus 监听 ServiceReady 事件
        """
        start = time.time()
        satisfied = set()
        
        async def wait_for_service(dep: ServiceDependency):
            async for event in self.event_bus.subscribe(
                event_type=EventType.SERVICE_READY,
                filter=lambda e: e.service_id == dep.service_id
            ):
                if time.time() - start > timeout:
                    raise TimeoutError()
                satisfied.add(dep.service_id)
                break
        
        await asyncio.gather(*[
            wait_for_service(dep) for dep in dependencies
        ])
```

### 4.3 故障转移与降级

```python
class DegradedMode:
    """
    降级模式 - 非关键依赖不可用时继续服务
    """
    
    async def evaluate_health(self, service: ServiceMetadata) -> ServiceState:
        """
        评估服务健康状态
        
        策略:
          1. 检查所有绝对依赖 (required=True)
          2. 如果有任何绝对依赖不可用 → STOPPED
          3. 检查可选依赖
          4. 可选依赖部分不可用 → DEGRADED
          5. 所有依赖可用 → RUNNING
        """
        
        required_status = {}
        optional_status = {}
        
        for dep in service.dependencies:
            instances = await registry.find_service(dep.service_id)
            available = len(instances) > 0
            
            if dep.required:
                required_status[dep.service_id] = available
            else:
                optional_status[dep.service_id] = available
        
        # 检查必需依赖
        if not all(required_status.values()):
            return ServiceState.STOPPED
        
        # 检查可选依赖
        if not all(optional_status.values()):
            return ServiceState.DEGRADED
        
        return ServiceState.RUNNING
    
    async def execute_degraded_operation(
        self,
        operation: Callable,
        fallback: Callable = None
    ) -> Any:
        """
        在降级模式下执行操作
        
        如果操作失败（依赖不可用），执行备选方案
        """
        
        try:
            return await operation()
        except DependencyUnavailableError:
            if fallback:
                return await fallback()
            else:
                # 依赖不可用但无备选方案，返回错误
                raise ServiceDegradedError()
```

### 4.4 内部事件与生命周期集成

```python
class LifecycleEvent:
    """生命周期事件"""
    type: EventType  # INITIALIZING / READY / DEGRADED / STOPPING / STOPPED
    service_id: int
    instance_id: int
    timestamp: datetime
    details: Dict[str, Any]  # 额外信息

class LifecycleEventBus(InternalEventBus):
    """
    生命周期事件总线 - 内部事件驱动
    
    发出的事件：
      - SERVICE_INITIALIZING: 服务开始初始化
      - SERVICE_READY: 服务已就绪，可接受流量
      - SERVICE_DEGRADED: 服务降级 (部分功能失效)
      - SERVICE_UNHEALTHY: 服务不健康，建议停止流量
      - SERVICE_STOPPING: 服务正在停止
      - SERVICE_STOPPED: 服务已停止
      
      - INSTANCE_DISCOVERED: 发现新实例
      - INSTANCE_LOST: 实例丢失/离线
      - INSTANCE_HEALTH_CHANGED: 实例健康度改变
      
      - DEPENDENCY_SATISFIED: 依赖变为可用
      - DEPENDENCY_LOST: 依赖变为不可用
    """
    
    async def on_service_ready(self, handler: Callable):
        """订阅 SERVICE_READY 事件"""
        return await self.subscribe(
            event_type=EventType.SERVICE_READY,
            handler=handler
        )
    
    async def on_dependency_lost(self, handler: Callable):
        """订阅 DEPENDENCY_LOST 事件"""
        return await self.subscribe(
            event_type=EventType.DEPENDENCY_LOST,
            handler=handler
        )
```

## 5. 健康与就绪

- **Liveness (存活)**: 进程是否存活，死锁或 Crash 则重启。
- **Readiness (就绪)**: 是否准备好接收流量。
- **与 Registry/SD 集成**：健康变化触发事件，影响客户端代理端点选择。

## 6. 故障与恢复

- **自动重启**：可选策略，基于失败计数与时间窗口。
- **会话恢复**：`_SessionStorage` 提供的会话 ID 分配在重启后重建。
- **复位通知**：事件组广播 `reset`，消费者可感知重启。
- **优雅降级**: 当非关键依赖不可用时，服务应能继续提供核心功能。
