# 内部事件模型设计

## 1. 概述

**内部事件** 是 tinySOA 框架内部的通信机制，用于：
- 服务生命周期变化通知 (ServiceStarted, ServiceReady, ServiceStopped)
- 服务发现事件 (InstanceDiscovered, InstanceLost)
- 依赖关系协调 (DependencySatisfied, DependencyLost)
- 健康状态变化 (HealthStatusChanged)
- 配置变更通知 (ConfigurationChanged)

**与业务事件的区别**：
- **内部事件**: 框架内部通信，不通过 SOME/IP 协议发送，只在本进程或本服务内有效
- **业务事件**: SOME/IP eventgroup，通过网络发送给订阅者，是 SOA 的重要特性

## 2. 事件类型定义

```python
from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict
from datetime import datetime

class InternalEventType(Enum):
    """内部事件类型"""
    
    # 服务生命周期事件
    SERVICE_INITIALIZING = "service.initializing"
    SERVICE_READY = "service.ready"
    SERVICE_DEGRADED = "service.degraded"
    SERVICE_UNHEALTHY = "service.unhealthy"
    SERVICE_STOPPING = "service.stopping"
    SERVICE_STOPPED = "service.stopped"
    SERVICE_ERROR = "service.error"
    
    # 实例发现事件
    INSTANCE_DISCOVERED = "instance.discovered"
    INSTANCE_LOST = "instance.lost"
    INSTANCE_HEALTH_CHANGED = "instance.health_changed"
    
    # 依赖管理事件
    DEPENDENCY_SATISFIED = "dependency.satisfied"
    DEPENDENCY_LOST = "dependency.lost"
    
    # 配置变更事件
    CONFIG_CHANGED = "config.changed"
    CONFIG_ROLLBACK = "config.rollback"
    
    # 连接事件
    CONNECTION_ESTABLISHED = "connection.established"
    CONNECTION_LOST = "connection.lost"

@dataclass
class InternalEvent:
    """内部事件"""
    
    # 基本信息
    event_type: InternalEventType
    timestamp: datetime
    source_service_id: int  # 事件来源服务
    
    # 事件载体
    details: Dict[str, Any]  # 事件详细信息
    
    # 关联的实体
    related_service_id: Optional[int] = None
    related_instance_id: Optional[int] = None
    
    # 追踪
    correlation_id: str = None  # 关联ID，用于追踪事件链
    
    def __post_init__(self):
        if not self.correlation_id:
            self.correlation_id = self._generate_correlation_id()
    
    def _generate_correlation_id(self) -> str:
        import uuid
        return str(uuid.uuid4())
```

## 3. 内部事件总线设计

```python
class InternalEventBus:
    """
    内部事件总线
    
    职责:
      - 发布内部事件
      - 订阅内部事件
      - 事件分发与路由
      - 事件缓冲与可靠传递
    """
    
    def __init__(self):
        self.subscribers = {}  # {event_type: [handlers]}
        self.event_buffer = asyncio.Queue(maxsize=1000)  # 事件缓冲
        self.event_history = deque(maxlen=10000)  # 保留最近10000条事件
    
    async def publish(self, event: InternalEvent) -> None:
        """
        发布事件
        
        :param event: 内部事件对象
        
        流程:
          1. 将事件存入历史记录 (用于诊断)
          2. 分发给所有订阅者
          3. 若分发失败，进入缓冲队列 (保证不丢失)
        """
        
        # 记录历史
        self.event_history.append({
            'event': event,
            'published_at': datetime.now()
        })
        
        # 分发给订阅者
        handlers = self.subscribers.get(event.event_type, [])
        
        tasks = []
        for handler in handlers:
            task = asyncio.create_task(self._invoke_handler(handler, event))
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def subscribe(
        self,
        event_type: InternalEventType,
        handler: Callable[[InternalEvent], Awaitable[None]],
        buffer_size: int = 100
    ) -> str:
        """
        订阅事件
        
        :param event_type: 事件类型
        :param handler: 事件处理器 (协程)
        :param buffer_size: 该订阅的缓冲大小
        :return: 订阅ID
        """
        
        sub_id = self._generate_subscription_id()
        
        subscription = {
            'id': sub_id,
            'event_type': event_type,
            'handler': handler,
            'buffer': asyncio.Queue(maxsize=buffer_size),
            'created_at': datetime.now(),
            'event_count': 0
        }
        
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        
        self.subscribers[event_type].append(subscription)
        
        return sub_id
    
    async def unsubscribe(self, subscription_id: str) -> None:
        """取消订阅"""
        for event_type, handlers in self.subscribers.items():
            self.subscribers[event_type] = [
                h for h in handlers if h['id'] != subscription_id
            ]
    
    async def subscribe_async_iter(
        self,
        event_type: InternalEventType,
        buffer_size: int = 100
    ) -> AsyncIterator[InternalEvent]:
        """
        异步迭代器方式订阅
        
        用法:
            async for event in event_bus.subscribe_async_iter(EventType.SERVICE_READY):
                print(f"Service ready: {event}")
        """
        
        queue = asyncio.Queue(maxsize=buffer_size)
        
        async def handler(event: InternalEvent):
            try:
                await queue.put(event)
            except asyncio.QueueFull:
                # 丢弃最旧的事件
                try:
                    queue.get_nowait()
                    await queue.put(event)
                except:
                    pass
        
        sub_id = await self.subscribe(event_type, handler, buffer_size)
        
        try:
            while True:
                yield await queue.get()
        finally:
            await self.unsubscribe(sub_id)
    
    async def _invoke_handler(
        self,
        subscription: Dict,
        event: InternalEvent
    ) -> None:
        """
        调用事件处理器，捕获异常避免一个失败影响其他
        """
        
        try:
            handler = subscription['handler']
            await handler(event)
            subscription['event_count'] += 1
        except Exception as e:
            # 记录异常，但不中断其他处理器
            self.logger.error(
                f"Error in event handler for {event.event_type}",
                exc_info=True
            )
    
    def get_event_history(
        self,
        event_type: Optional[InternalEventType] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        获取事件历史
        
        用于调试和诊断
        """
        
        if event_type:
            return [
                e for e in list(self.event_history)[-limit:]
                if e['event'].event_type == event_type
            ]
        else:
            return list(self.event_history)[-limit:]
```

## 4. 具体事件定义与使用

### 4.1 服务生命周期事件

```python
class ServiceLifecycleEvent:
    """服务生命周期事件"""
    
    @staticmethod
    def service_ready(service_id: int, instance_id: int) -> InternalEvent:
        """服务已就绪"""
        return InternalEvent(
            event_type=InternalEventType.SERVICE_READY,
            timestamp=datetime.now(),
            source_service_id=service_id,
            related_service_id=service_id,
            related_instance_id=instance_id,
            details={
                'message': f'Service {service_id:04x} instance {instance_id:04x} is ready',
                'ready_to_serve': True
            }
        )
    
    @staticmethod
    def service_degraded(
        service_id: int,
        reason: str,
        affected_methods: List[int] = None
    ) -> InternalEvent:
        """服务降级"""
        return InternalEvent(
            event_type=InternalEventType.SERVICE_DEGRADED,
            timestamp=datetime.now(),
            source_service_id=service_id,
            related_service_id=service_id,
            details={
                'reason': reason,
                'affected_methods': affected_methods or [],
                'can_serve': True,
                'partial_functionality': True
            }
        )
    
    @staticmethod
    def service_unhealthy(
        service_id: int,
        reason: str,
        auto_restart: bool = True
    ) -> InternalEvent:
        """服务不健康"""
        return InternalEvent(
            event_type=InternalEventType.SERVICE_UNHEALTHY,
            timestamp=datetime.now(),
            source_service_id=service_id,
            related_service_id=service_id,
            details={
                'reason': reason,
                'should_shutdown': True,
                'auto_restart': auto_restart
            }
        )
```

### 4.2 实例发现事件

```python
class InstanceDiscoveryEvent:
    """实例发现事件"""
    
    @staticmethod
    def instance_discovered(
        service_id: int,
        instance_id: int,
        endpoint: Tuple[str, int],
        version: Tuple[int, int]
    ) -> InternalEvent:
        """发现新实例"""
        return InternalEvent(
            event_type=InternalEventType.INSTANCE_DISCOVERED,
            timestamp=datetime.now(),
            source_service_id=service_id,
            related_service_id=service_id,
            related_instance_id=instance_id,
            details={
                'instance_id': instance_id,
                'endpoint': endpoint,
                'version': version,
                'discovery_method': 'sd_protocol',
                'ttl': 30  # 秒
            }
        )
    
    @staticmethod
    def instance_lost(
        service_id: int,
        instance_id: int,
        reason: str = 'ttl_expired'
    ) -> InternalEvent:
        """实例丢失"""
        return InternalEvent(
            event_type=InternalEventType.INSTANCE_LOST,
            timestamp=datetime.now(),
            source_service_id=service_id,
            related_service_id=service_id,
            related_instance_id=instance_id,
            details={
                'instance_id': instance_id,
                'reason': reason,  # 'ttl_expired' / 'explicit_stop' / 'network_unreachable'
                'active_connections': 0
            }
        )
```

### 4.3 依赖管理事件

```python
class DependencyEvent:
    """依赖管理事件"""
    
    @staticmethod
    def dependency_satisfied(
        service_id: int,
        dependency_service_id: int
    ) -> InternalEvent:
        """依赖服务变为可用"""
        return InternalEvent(
            event_type=InternalEventType.DEPENDENCY_SATISFIED,
            timestamp=datetime.now(),
            source_service_id=service_id,
            related_service_id=dependency_service_id,
            details={
                'dependent_service': service_id,
                'dependency_service': dependency_service_id,
                'available_instances': 1,
                'all_required_met': True
            }
        )
    
    @staticmethod
    def dependency_lost(
        service_id: int,
        dependency_service_id: int,
        required: bool = True
    ) -> InternalEvent:
        """依赖服务变为不可用"""
        return InternalEvent(
            event_type=InternalEventType.DEPENDENCY_LOST,
            timestamp=datetime.now(),
            source_service_id=service_id,
            related_service_id=dependency_service_id,
            details={
                'dependent_service': service_id,
                'dependency_service': dependency_service_id,
                'required': required,
                'should_degrade': required == False
            }
        )
```

## 5. 事件驱动的应用模式

### 5.1 依赖协调示例

```python
class DependencyCoordinator:
    """
    依赖协调器 - 使用内部事件驱动依赖管理
    """
    
    def __init__(self, service: Service, event_bus: InternalEventBus):
        self.service = service
        self.event_bus = event_bus
        self.dependencies_satisfied = asyncio.Event()
    
    async def wait_for_dependencies(self, timeout: float = 30.0):
        """
        等待所有必需依赖可用
        
        通过内部事件通知而非轮询
        """
        
        required_deps = [d for d in self.service.dependencies if d.required]
        satisfied = set()
        
        # 订阅 DEPENDENCY_SATISFIED 事件
        async for event in self.event_bus.subscribe_async_iter(
            InternalEventType.DEPENDENCY_SATISFIED
        ):
            # 检查是否是我们关心的依赖
            if event.related_service_id in [d.service_id for d in required_deps]:
                satisfied.add(event.related_service_id)
            
            # 所有依赖都满足了
            if len(satisfied) == len(required_deps):
                break
        
        self.dependencies_satisfied.set()
```

### 5.2 健康监控示例

```python
class HealthMonitor:
    """
    健康监控 - 监听依赖的健康状态变化
    """
    
    def __init__(self, event_bus: InternalEventBus):
        self.event_bus = event_bus
        self.unhealthy_services = set()
    
    async def monitor_health(self):
        """持续监控服务健康状态"""
        
        async for event in self.event_bus.subscribe_async_iter(
            InternalEventType.SERVICE_UNHEALTHY
        ):
            self.unhealthy_services.add(event.related_service_id)
            self.logger.warning(
                f"Service {event.related_service_id:04x} unhealthy: {event.details['reason']}"
            )
            
            # 触发报警
            await self._trigger_alert(event)
        
        async for event in self.event_bus.subscribe_async_iter(
            InternalEventType.SERVICE_READY
        ):
            if event.related_service_id in self.unhealthy_services:
                self.unhealthy_services.remove(event.related_service_id)
                self.logger.info(f"Service {event.related_service_id:04x} recovered")
```

## 6. 事件持久化与可观测性

```python
class EventPersistence:
    """
    事件持久化 - 将内部事件记录到文件或数据库
    
    用于:
      - 故障后根因分析
      - 审计日志
      - 性能分析
    """
    
    async def persist_event(self, event: InternalEvent):
        """持久化事件"""
        
        record = {
            'timestamp': event.timestamp.isoformat(),
            'event_type': event.event_type.value,
            'source_service_id': hex(event.source_service_id),
            'related_service_id': hex(event.related_service_id) if event.related_service_id else None,
            'correlation_id': event.correlation_id,
            'details': event.details
        }
        
        # 写入到结构化日志或时间序列数据库
        self.logger.info(json.dumps(record))
        # 或
        # await self.elasticsearch.index(index='tinysoa-events', body=record)
```

## 7. 事件与拦截器的集成

```python
class EventPublishingInterceptor(Interceptor):
    """
    拦截器 - 在关键节点发布内部事件
    """
    
    def __init__(self, event_bus: InternalEventBus):
        self.event_bus = event_bus
    
    async def before_request(self, ctx: CallContext, request: Request) -> Request:
        # 发布请求开始事件
        await self.event_bus.publish(InternalEvent(
            event_type=InternalEventType.RPC_REQUEST_STARTED,
            timestamp=datetime.now(),
            source_service_id=ctx.service_id,
            details={
                'method_id': ctx.method_id,
                'trace_id': ctx.trace_id
            }
        ))
        return request
    
    async def on_error(self, ctx: CallContext, error: Exception) -> Optional[Response]:
        # 发布错误事件
        await self.event_bus.publish(InternalEvent(
            event_type=InternalEventType.RPC_ERROR,
            timestamp=datetime.now(),
            source_service_id=ctx.service_id,
            details={
                'method_id': ctx.method_id,
                'error': str(error),
                'error_type': type(error).__name__
            }
        ))
        raise error
```
