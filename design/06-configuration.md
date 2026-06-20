# 配置管理系统设计

## 1. 目标

- 一致的加载顺序与合并策略；强校验；热更新；与拦截器/注册表联动。

## 2. 结构

```yaml
service:
  service_id: 0x1234
  instance_id: 0x0001
  version: [1, 0]
network:
  bind: "0.0.0.0:30490"
  multicast: "239.0.0.1:30490"
client:
  timeout_ms: 500
  retries: 2
  lb_policy: round_robin
interceptors:
  - type: metrics
  - type: tracing
codec:
  request: msgpack
  response: msgpack
registry:
  cleanup_interval_s: 60
  heartbeat_timeout_s: 10
logging:
  level: info
  format: json
```

## 3. 来源与优先级

1. 默认配置（内置）
2. 配置文件（YAML/JSON/TOML）
3. 环境变量（`TINY_SOA_*`）
4. 代码覆盖（构造参数）

## 4. 校验与模式

- 使用 Pydantic 或自定义校验器，确保类型与范围正确。
- 错误处理：抛出 `ConfigurationError`，并记录详细位置与值。

## 5. 热更新与版本控制

### 5.1 配置版本管理

```python
class ConfigVersion:
    """配置版本对象"""
    version_id: str  # 通常为 MD5(config_yaml)
    timestamp: datetime
    checksum: str
    changed_fields: Set[str]  # 变更了哪些字段
    
    def __lt__(self, other) -> bool:
        """版本比较，用于检测回滚"""
        return self.timestamp < other.timestamp

class ConfigChange:
    """配置变更记录"""
    version_id: str
    previous_version_id: str
    changes: Dict[str, Tuple[Any, Any]]  # {field: (old_value, new_value)}
    applied_at: datetime
    applied_services: Set[str]  # 哪些服务已应用该配置
    status: ConfigChangeStatus  # PENDING / APPLIED / ROLLED_BACK

class ConfigurationManager:
    
    async def load_config(self, config_path: str) -> ConfigVersion:
        """
        加载配置并生成版本号
        
        :return: ConfigVersion 对象
        """
        config = await self._parse_config_file(config_path)
        version = self._compute_version(config)
        self.current_version = version
        return version
    
    async def update_config(
        self,
        new_config: Dict,
        atomic: bool = True,
        rollback_on_error: bool = True
    ) -> bool:
        """
        更新配置 (热更新)
        
        :param new_config: 新配置字典
        :param atomic: 是否原子化 (所有服务同时应用或全部失败)
        :param rollback_on_error: 出错时是否回滚
        :return: 是否成功
        
        流程:
          1. 计算新配置版本
          2. 验证配置 (schema + 依赖检查)
          3. 如果不允许修改的字段被改了 → 拒绝
          4. 广播给所有服务，要求应用新配置
          5. 等待 ACK (带超时)
          6. 若全部成功 → 提交变更
          7. 若有失败 & rollback_on_error → 全部回滚
        """
        
        new_version = self._compute_version(new_config)
        
        # 步骤1: 验证配置
        try:
            self._validate_config(new_config)
        except ConfigValidationError as e:
            self.logger.error(f"Config validation failed: {e}")
            return False
        
        # 步骤2: 检查不可修改的字段
        if not self._check_immutable_fields(self.current_version, new_version):
            self.logger.error("Attempted to modify immutable fields")
            return False
        
        # 步骤3: 广播配置变更
        change = ConfigChange(
            version_id=new_version.version_id,
            previous_version_id=self.current_version.version_id,
            changes=self._compute_diff(self.current_version, new_version),
            applied_services=set()
        )
        
        # 步骤4: 收集 ACK
        acks = await self._broadcast_config_change(new_version, timeout=10)
        
        # 步骤5: 检查结果
        if atomic and len(acks['success']) != len(acks['total']):
            if rollback_on_error:
                await self._broadcast_config_rollback(self.current_version)
            change.status = ConfigChangeStatus.ROLLED_BACK
            return False
        
        # 步骤6: 提交变更
        change.status = ConfigChangeStatus.APPLIED
        change.applied_services = acks['success']
        self._record_change_history(change)
        self.current_version = new_version
        
        return True
    
    async def rollback_config(self, target_version_id: str) -> bool:
        """
        回滚到指定版本
        
        :param target_version_id: 目标版本号
        :return: 是否成功
        """
        target_config = self._get_config_from_history(target_version_id)
        if not target_config:
            return False
        
        return await self.update_config(target_config, atomic=True)
    
    def _check_immutable_fields(self, old_ver: ConfigVersion, new_ver: ConfigVersion) -> bool:
        """
        检查是否有不可修改的字段被改了
        
        不可修改的字段:
          - service.service_id
          - service.instance_id  
          - service.version
          - network.bind_address (需要重启)
        """
        immutable = {'service_id', 'instance_id', 'bind_address'}
        for field in immutable:
            if field in new_ver.changed_fields:
                self.logger.error(f"Field '{field}' is immutable")
                return False
        return True
    
    def _compute_diff(self, old_ver: ConfigVersion, new_ver: ConfigVersion) -> Dict:
        """计算两个配置版本的差异"""
        old_config = self._get_config_by_version(old_ver)
        new_config = self._get_config_by_version(new_ver)
        
        diff = {}
        for key in set(old_config.keys()) | set(new_config.keys()):
            if old_config.get(key) != new_config.get(key):
                diff[key] = (old_config.get(key), new_config.get(key))
        
        return diff
```

### 5.2 灰度变更 (Canary Deployment)

```python
class CanaryConfigDeployment:
    """
    灰度配置变更 - 逐步验证新配置的正确性
    """
    
    async def deploy_canary(
        self,
        new_config: Dict,
        canary_percentage: float = 10.0,  # 10% 的服务先应用
        validation_period_s: float = 60.0,  # 验证60秒
        error_threshold: float = 0.01  # 错误率超过1%则回滚
    ) -> bool:
        """
        灰度部署配置变更
        
        流程:
          1. 选择 10% 的服务实例作为 canary
          2. 将新配置应用到 canary 实例
          3. 监控 canary 实例的指标 (错误率、延迟)
          4. 若验证期间内错误率超过阈值 → 回滚
          5. 若验证通过 → 逐步扩大到其他实例 (10% -> 50% -> 100%)
        """
        
        # 步骤1: 选择 canary 实例
        canary_services = await self._select_canary_services(canary_percentage)
        
        # 步骤2: 应用新配置
        try:
            await self._apply_config_to_services(canary_services, new_config)
        except Exception as e:
            self.logger.error(f"Failed to apply canary config: {e}")
            return False
        
        # 步骤3: 监控验证
        metrics = await self._collect_metrics(canary_services, validation_period_s)
        
        error_rate = metrics['error_count'] / max(metrics['total_count'], 1)
        if error_rate > error_threshold:
            self.logger.warning(
                f"Canary error rate {error_rate:.2%} exceeds threshold, rolling back"
            )
            await self._rollback_config(canary_services)
            return False
        
        # 步骤4: 逐步推送到其他实例
        for percentage in [50, 100]:
            services = await self._select_canary_services(percentage)
            await self._apply_config_to_services(services, new_config)
        
        return True
```

### 5.3 原子性边界定义

```python
class ConfigUpdateBoundary:
    """
    定义哪些配置字段必须原子化更新
    """
    
    # 必须同时生效 (不允许部分实例新/旧配置混合)
    ATOMIC_GROUPS = {
        "codec": {"request_format", "response_format"},  # 编解码格式必须同时更改
        "routing": {"lb_policy", "lb_weights"},  # LB策略和权重必须同时更新
        "security": {"auth_enabled", "tls_cert_path"},  # 安全配置必须一起更新
    }
    
    # 可以独立更新 (允许某些实例先应用)
    INDEPENDENT_FIELDS = {
        "log_level",  # 日志级别
        "metrics_enabled",  # 监控开关
        "timeout_ms",  # 超时时间
        "max_retries",  # 重试次数
    }
    
    @classmethod
    def get_atomic_group(cls, field: str) -> Optional[str]:
        """获取字段所属的原子组"""
        for group_name, fields in cls.ATOMIC_GROUPS.items():
            if field in fields:
                return group_name
        return None
    
    @classmethod
    def validate_atomic_update(cls, changed_fields: Set[str]) -> bool:
        """
        验证配置变更是否满足原子性约束
        
        规则: 若某个原子组中的字段被改了，必须该组内所有字段同时被改
        """
        for group_name, fields in cls.ATOMIC_GROUPS.items():
            changed_in_group = fields & changed_fields
            if changed_in_group and changed_in_group != fields:
                # 该组内有字段被改，但不是全部 → 违反原子性
                return False
        
        return True
```

### 5.4 配置变更通知

```python
class ConfigChangeNotification:
    """
    配置变更通知机制
    
    当配置变更时，通知所有订阅方
    """
    
    async def subscribe_config_changes(
        self,
        fields: Optional[Set[str]] = None  # 只监听这些字段的变更
    ) -> AsyncIterator[ConfigChange]:
        """
        订阅配置变更事件
        
        :param fields: 感兴趣的字段集合，None=所有字段
        :return: 配置变更事件的异步迭代器
        """
        sub_id = self._generate_subscription_id()
        
        try:
            async for change in self._config_change_event_bus.subscribe(sub_id):
                if fields is None or (change.changed_fields & fields):
                    yield change
        finally:
            await self._config_change_event_bus.unsubscribe(sub_id)
    
    async def _notify_config_changes(self, change: ConfigChange):
        """
        发布配置变更事件
        
        被 update_config() 调用
        """
        await self._config_change_event_bus.publish(change)
```

## 6. 与 SD/Registry 的协作

- 根据配置决定 OfferService/FindService 策略与过滤条件。
- 变更网络参数需要重建传输；其余参数可在线应用。
