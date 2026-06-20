# SOME/IP tinySOA 测试计划 - 快速参考指南

## 📋 测试用例速查表

### 单元测试 (Unit Tests) - 78 个用例

#### Method RPC 测试 (15 个)
| 编号 | 测试名称 | 关键点 |
|------|--------|--------|
| TC-M-001 | Method注册和元数据 | 元数据管理、参数类型 |
| TC-M-002 | 同步RPC调用 | Request/Response |
| TC-M-003 | 单向调用 | Fire-and-Forget |
| TC-M-004 | 参数序列化 | 各类型支持 |
| TC-M-005 | 返回值反序列化 | 复杂对象处理 |
| TC-M-006 | 超时处理 | TimeoutError |
| TC-M-007 | Method未找到 | MethodNotFoundError |
| TC-M-008 | 参数验证 | 类型检查 |
| TC-M-009 | 错误响应 | 异常序列化 |
| TC-M-010 | 并发调用(同实例) | 100并发 |
| TC-M-011 | 并发调用(多实例) | 50并发+负载均衡 |
| TC-M-012 | 幂等性追踪 | 去重 |
| TC-M-013 | 会话/序列号管理 | Session隔离 |
| TC-M-014 | 大型负载 | 64KB+ |
| TC-M-015 | 方法调用链 | A→B→C追踪 |

#### 拦截器测试 (8个基础 + 9个内置)
| 编号 | 测试名称 | 验证点 |
|------|--------|--------|
| TC-I-001 | 执行顺序 | 5个拦截器顺序 |
| TC-I-002 | Before请求钩子 | 请求修改 |
| TC-I-003 | After响应钩子 | 响应修改 |
| TC-I-004 | Error钩子 | 异常处理 |
| TC-I-005 | 短路(Short-circuit) | 缓存命中跳过RPC |
| TC-I-006 | 异常隔离 | 单个拦截器失败 |
| TC-I-007 | 上下文传播 | trace_id保留 |
| TC-I-008 | 注销清理 | 内存释放 |
| TC-B-001 | Metrics拦截器 | 计数器/直方图 |
| TC-B-002 | Metrics百分位数 | p50/p95/p99 |
| TC-B-003 | Logging拦截器 | JSON结构化日志 |
| TC-B-004 | Tracing拦截器 | Span创建 |
| TC-B-005 | Auth拦截器 | 令牌验证 |
| TC-B-006 | RateLimit拦截器 | 令牌桶限流 |
| TC-B-007 | Retry拦截器 | 自动重试 |
| TC-B-008 | Caching拦截器 | 缓存命中 |
| TC-B-009 | Caching失效 | TTL过期 |

#### 负载均衡测试 (8个)
| 编号 | 测试名称 | 策略 |
|------|--------|------|
| TC-LB-001 | RoundRobin | 轮询分布 |
| TC-LB-002 | Random | 随机分布 |
| TC-LB-003 | LatencyWeighted | 延迟加权 |
| TC-LB-004 | 健康度评分 | 0.4+0.4+0.2权重 |
| TC-LB-005 | 实例过滤 | score < 0.1排除 |
| TC-LB-006 | 故障转移 | 自动重试 |
| TC-LB-007 | 重试耗尽 | 所有实例都试过 |
| TC-LB-008 | 策略覆盖 | 单次覆盖 |

#### Eventgroup测试 (10个)
| 编号 | 测试名称 | 功能 |
|------|--------|------|
| TC-EG-001 | 事件组注册 | 元数据 |
| TC-EG-002 | 订阅(SD) | Subscribe消息 |
| TC-EG-003 | 事件通知 | 异步迭代 |
| TC-EG-004 | 事件过滤 | filter_fn |
| TC-EG-005 | 事件历史 | 初始化事件 |
| TC-EG-006 | 多订阅者 | 独立游标 |
| TC-EG-007 | 取消订阅 | 清理 |
| TC-EG-008 | 序列号追踪 | 无重复无丢失 |
| TC-EG-009 | 大型事件 | 64KB检查 |
| TC-EG-010 | 内部事件 | SERVICE_DISCOVERED等 |

#### 原有测试 (29个)
- TC-001~029: EventBus Pub/Sub相关（映射、生命周期、并发等）

---

### 系统集成测试 (26 个用例)

#### RPC集成测试 (10个)
| 编号 | 测试名称 | 场景 |
|------|--------|------|
| ST-M-001 | 端到端RPC | 真实UDP |
| ST-M-002 | RPC调用链 | A→B→C分布式追踪 |
| ST-M-003 | 大型负载 | 1KB~100KB |
| ST-M-004 | 并发压力 | 100并发*10=1000 |
| ST-M-005 | 超时和重试 | 超时后重试成功 |
| ST-M-006 | 故障场景 | 异常/崩溃/无法找到 |
| ST-M-007 | 负载均衡 | 跨3个实例 |
| ST-M-008 | 有状态方法 | 并发修改一致性 |
| ST-M-009 | 单向调用 | Fire-and-Forget |
| ST-M-010 | 版本协商 | v1.0/v2.0自动选择 |

#### 观测性集成测试 (5个)
| 编号 | 测试名称 | 系统 |
|------|--------|------|
| ST-I-001 | 分布式追踪 | Jaeger |
| ST-I-002 | Prometheus指标 | 计数器/直方图 |
| ST-I-003 | 日志聚合 | ELK/Splunk |
| ST-I-004 | 熔断器 | CLOSED→OPEN→HALF-OPEN |
| ST-I-005 | 拦截器隔离 | 单个失败不影响链 |

#### 原有系统测试 (11个)
- ST-001~010: EventBus Pub/Sub集成（真实网络、延迟加入、压力等）

---

### 安全测试 (10 个用例)

#### 一般安全测试 (4个)
- SEC-001: SOME/IP恶意包注入
- SEC-002: SD欺骗攻击
- SEC-003: DoS资源耗尽
- SEC-004: 内存耗尽防护

#### Method安全测试 (3个)
| 编号 | 攻击类型 | 防护点 |
|------|---------|--------|
| SEC-M-001 | 参数注入 | SQL/命令注入防护 |
| SEC-M-002 | 反序列化炸弹 | ZIP炸弹解压限制 |
| SEC-M-003 | RPC洪泛 | 限流率 |

#### 拦截器安全测试 (3个)
| 编号 | 攻击类型 | 防护点 |
|------|---------|--------|
| SEC-I-001 | 拦截器注入 | 白名单验证 |
| SEC-I-002 | 追踪上下文注入 | log4shell防护 |
| SEC-I-003 | 认证绕过 | Auth顺序 |

---

### 协议测试 (10 个用例)

| 编号 | 测试名称 | SOME/IP特性 |
|------|--------|------------|
| PROTO-001 | 报文头验证 | 魔法码/版本/长度 |
| PROTO-002 | 返回服务(RxSD) | 单播响应 |
| PROTO-003 | 会话管理 | Session/Sequence隔离 |
| PROTO-004 | 方法事件多路复用 | 同端口区分 |
| PROTO-005 | SD Subscribe | 事件组订阅 |
| PROTO-006 | 多客户端订阅 | 状态追踪 |
| PROTO-007 | 端点动态更新 | 端口变更 |
| PROTO-008 | TTL和重订阅 | 过期自动注销 |
| PROTO-009 | 版本兼容性 | v1.0/v2.0选择 |
| PROTO-010 | 并发方法事件 | Mux去重 |

---

### 架构测试 (12 个用例)

#### 基础架构测试 (6个)
- ARCH-001: 配置热重载
- ARCH-002: 服务健康监控
- ARCH-003: 拦截器链功能
- ARCH-004: 插件系统
- ARCH-005: 服务依赖管理
- ARCH-006: 内部事件总线

#### 扩展架构测试 (4个)
- ARCH-001-RPC: Method配置热更新
- ARCH-002-RPC: RPC健康度和熔断器
- ARCH-003-Extended: 拦截器链+短路
- ARCH-004-Extended: 自定义编解码器插件
- ARCH-005-Extended: Method依赖注入
- ARCH-006-Extended: Method生命周期事件

---

### 非功能需求测试 (12 个用例)

#### 基础NFR (6个)
- NFR-001: 内存约束 (< 50MB for 100 topics)
- NFR-002: CPU性能 (< 5% @ 1000 msg/sec)
- NFR-003: 网络效率 (< 20% 开销)
- NFR-004: 启动性能 (< 5s cold start)
- NFR-005: 故障恢复MTTR (< 30s)
- NFR-006: 可扩展性 (1000 topics, 10K subscribers)

#### 扩展NFR (6个)
- NFR-001-Extended: Method内存开销 (< 10KB/method)
- NFR-002-Extended: RPC延迟 (p99 < 50ms, CPU < 2%)
- NFR-003-Extended: 协议效率 (RPC overhead < 12B)
- NFR-004-Extended: 注册吞吐 (1000 methods in 2s)
- NFR-005-Extended: 故障转移MTTR (< 1s)
- NFR-006-Extended: 并发限制 (10K+ RPC calls/instance)

---

## 📊 统计概览

```
┌──────────────────────────────────┐
│     测试用例总数统计             │
├──────────────────────────────────┤
│ 单元测试 (TC-*)       78 个      │
│ 系统测试 (ST-*)       26 个      │
│ 安全测试 (SEC-*)      10 个      │
│ 协议测试 (PROTO-*)    10 个      │
│ 架构测试 (ARCH-*)     12 个      │
│ NFR测试 (NFR-*)       12 个      │
├──────────────────────────────────┤
│ 新增测试              90+ 个     │
│ 原有测试              55 个      │
│ 总计                 155+ 个     │
└──────────────────────────────────┘
```

## 🎯 SOME/IP 功能完整性

```
✅ 核心功能
├─ RPC (Request/Response)
├─ Fire-and-Forget (单向)
├─ 事件订阅 (Eventgroup)
├─ 服务发现 (SD)
├─ 负载均衡 (3种策略)
└─ 故障转移 (自动重试)

✅ 协议特性
├─ 会话和序列号管理
├─ 方法/事件多路复用
├─ 版本协商
├─ TTL管理
├─ 响应路由 (RxSD)
└─ 端点动态更新

✅ 质量属性
├─ 可靠性 (重试、超时)
├─ 可观测性 (追踪、指标、日志)
├─ 安全性 (认证、限流、注入防护)
├─ 性能 (低延迟、高吞吐)
├─ 可扩展性 (10K+并发)
└─ 可维护性 (热重载、插件)
```

## 📖 设计文档关联

| 测试领域 | 设计文档 | 章节 |
|---------|---------|------|
| RPC Methods | design/03-api-design.md | Section 4 |
| 拦截器 | design/05-interceptors-plugins.md | Section 1-2 |
| 负载均衡 | design/02-core-components.md | Section 3.4 |
| 事件模型 | design/09-internal-event-model.md | Full |
| 服务发现 | design/02-core-components.md | Section 3 |
| 生命周期 | design/04-lifecycle.md | Full |
| 可观测性 | design/07-monitoring-tracing.md | Full |
| 配置管理 | design/06-configuration.md | Full |
| 架构概览 | design/01-overview.md | Full |

## 🚀 优先级建议

### Phase 1 (第1-2周) - 必需功能
- TC-M-001~005: Method基础
- TC-I-001~004: 拦截器基础
- TC-LB-001~002: 负载均衡基础
- TC-EG-001~003: Eventgroup基础
- ST-M-001: 端到端RPC

### Phase 2 (第3-4周) - 核心功能
- TC-M-006~015: Method完整
- TC-I-005~008 + TC-B-001~009: 拦截器完整
- TC-LB-003~008: 负载均衡完整
- TC-EG-004~010: Eventgroup完整
- ST-M-002~010: RPC集成测试
- PROTO-001~010: 协议完整

### Phase 3 (第5-6周) - 质量保证
- SEC-* 所有安全测试
- ST-I-001~005 观测性测试
- ARCH-* 架构测试
- NFR-* 性能基准

## 💡 使用建议

1. **快速查找**: 使用 `grep "TC-M-"` 查找所有Method测试
2. **按功能组织**: 按测试类型分别执行单元/系统/安全测试
3. **持续集成**: 每个PR运行单元测试，每晚运行系统和安全测试
4. **性能监控**: 每周运行NFR测试，追踪指标趋势
5. **追踪映射**: 每个测试编号对应唯一的设计文档和代码实现

---

**最后更新**: 2025-12-20  
**测试计划版本**: 2.0  
**覆盖范围**: SOME/IP协议 > 95%, tinySOA框架 > 95%
