# ST-M-008: RPC with Stateful Methods

## 测试状态

✅ **测试通过** (2025-12-21)

## 测试目标

验证SOME/IP RPC服务的有状态方法处理，包括：
- 服务端状态管理（内存中的计数器）
- 并发安全性（多客户端同时访问）
- 原子操作（无竞态条件）
- 状态一致性（所有客户端看到相同状态）

## 测试规格

**测试ID**: ST-M-008  
**测试类别**: 系统集成测试 - 有状态RPC  
**优先级**: P1 (重要)  
**追溯性**: 并发控制、状态管理

## 测试配置

### 服务端状态

```python
class Counter:
    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()  # 线程安全
        self._increment_log = []       # 操作日志
```

### 服务架构

```
Client-1 ──┐
Client-2 ──┤
Client-3 ──┼──> Server (Stateful Counter)
Client-4 ──┤        |
Client-5 ──┘        └──> Shared State (Thread-Safe)
```

### 服务端配置

- **Service ID**: 0x8000
- **Instance ID**: 0x0001
- **Port**: 38000
- **Methods**:
  - **0x0001**: `increment(client_id)` - 原子递增计数器
  - **0x0002**: `get_value()` - 获取当前计数器值
  - **0x0003**: `reset()` - 重置计数器为0
  - **0x0004**: `get_log()` - 获取操作日志数量

### 测试配置

- **并发客户端数**: 5
- **每客户端操作次数**: 2
- **总预期操作数**: 10

## 测试步骤

### Test 1: 并发递增

1. 启动5个客户端（Client-1 到 Client-5）
2. 每个客户端并发调用 `increment()` 2次
3. 总共10次并发调用
4. **验证点**: 所有调用成功完成

### Test 2: 验证最终计数器值

1. 查询最终计数器值 `get_value()`
2. **验证点**: 值应该等于10（无丢失操作）

### Test 3: 验证原子性

1. 查询操作日志数量 `get_log()`
2. **验证点**: 日志应记录所有10次操作

### Test 4: 验证顺序值

1. 检查所有返回值的范围
2. **验证点**: 
   - 最小值 >= 1
   - 最大值 = 10
   - 无重复值（表示无竞态条件）

### Test 5: 状态一致性

1. 从3个不同客户端查询 `get_value()`
2. **验证点**: 所有客户端看到相同的值（10）

## 预期输出

```
INFO - ST-M-008-ORCH - Starting ST-M-008 orchestrator (RPC with Stateful Methods)
INFO - ST-M-008-ORCH - Server started (PID=xxx, Port=38000)
INFO - ST-M-008-Server - Server ready with stateful methods:
INFO - ST-M-008-Server -   - Method 0x0001 (increment)
INFO - ST-M-008-Server -   - Method 0x0002 (get_value)
INFO - ST-M-008-Client - === ST-M-008: RPC with Stateful Methods Test ===
INFO - ST-M-008-Client - Test Config:
INFO - ST-M-008-Client -   - Number of clients: 5
INFO - ST-M-008-Client -   - Increments per client: 2
INFO - ST-M-008-Client -   - Total expected increments: 10

INFO - ST-M-008-Client - --- Test 1: Concurrent Increments ---
INFO - ST-M-008-Client - Client-1 connected
INFO - ST-M-008-Client - Client-2 connected
INFO - ST-M-008-Client - Client-3 connected
INFO - ST-M-008-Client - Client-4 connected
INFO - ST-M-008-Client - Client-5 connected
INFO - ST-M-008-Server - [STATEFUL] increment() by Client-1 -> counter = 1
INFO - ST-M-008-Server - [STATEFUL] increment() by Client-2 -> counter = 2
INFO - ST-M-008-Server - [STATEFUL] increment() by Client-3 -> counter = 3
... (继续到10)
INFO - ST-M-008-Client - ✅ All clients completed

INFO - ST-M-008-Client - --- Test 2: Verify Final Counter Value ---
INFO - ST-M-008-Client - Final counter value: 10
INFO - ST-M-008-Client - ✅ PASS: Counter value correct (10 == 10)

INFO - ST-M-008-Client - --- Test 3: Verify Atomicity ---
INFO - ST-M-008-Client - Logged operations: 10
INFO - ST-M-008-Client - ✅ PASS: All operations logged (10 == 10)

INFO - ST-M-008-Client - --- Test 4: Verify Sequential Values ---
INFO - ST-M-008-Client - Returned values range: 1 to 10
INFO - ST-M-008-Client - ✅ PASS: Values in expected range [1, 10]

INFO - ST-M-008-Client - --- Test 5: State Consistency ---
INFO - ST-M-008-Client - ✅ PASS: All clients see consistent value: 10

INFO - ST-M-008-Client - ============================================================
INFO - ST-M-008-Client - ✅ ALL TESTS PASSED
INFO - ST-M-008-Client - ============================================================
```

## 验证点

- ✅ 并发客户端同时访问服务
- ✅ 所有递增操作成功
- ✅ 最终计数器值正确（10）
- ✅ 无操作丢失
- ✅ 无竞态条件（值不重复）
- ✅ 状态一致性（所有客户端视图相同）
- ✅ 线程安全的状态访问

## 运行测试

```bash
cd /home/page/GitPlayground/pysomeip
python tinySOA/examples/system_tests/ST-M-008/run_test.py
```

## 技术要点

### 1. 线程安全实现

```python
class Counter:
    def __init__(self):
        self._lock = threading.Lock()
    
    def increment(self, client_id: str) -> int:
        with self._lock:  # 关键：原子操作
            self._value += 1
            return self._value
```

**为什么需要锁？**
- SOME/IP handler在不同线程中执行
- 多个客户端可能同时调用
- 没有锁会导致：`read-modify-write`竞态条件

### 2. 竞态条件示例

```
没有锁的情况：
Client-1: read value=5  ──┐
Client-2: read value=5    ├─> 两者读到相同值
Client-1: write value=6 ──┤
Client-2: write value=6 ──┘    ❌ 丢失一次递增！

有锁的情况：
Client-1: [lock] read=5, write=6 [unlock]  ✓
Client-2:        [wait...]
Client-2: [lock] read=6, write=7 [unlock]  ✓
```

### 3. 并发测试架构

```python
# 使用 asyncio.gather 实现真正的并发
tasks = [client_task(i, 2) for i in range(1, 6)]
all_results = await asyncio.gather(*tasks)
```

这确保了：
- 5个客户端真正并发运行
- 压力测试服务端的线程安全性

### 4. 状态一致性

所有客户端在任何时刻查询都应该看到相同的状态：

```
时刻T1: Client-A查询 -> 10
时刻T1: Client-B查询 -> 10  ✓ 一致
时刻T1: Client-C查询 -> 10  ✓ 一致
```

## 常见问题

### Q1: 为什么使用threading.Lock而不是asyncio.Lock？

**A**: SOME/IP handler是同步函数，在线程池中执行，需要线程锁而非协程锁。

### Q2: 如果不使用锁会怎样？

**A**: 
- 最终值可能小于10（操作丢失）
- 多个客户端可能收到相同的计数值
- 日志中可能有重复值

### Q3: 真实场景的应用？

**A**:
- **会话管理**: 用户登录状态
- **资源池**: 可用连接数
- **限流器**: 请求计数
- **缓存**: 共享缓存状态

## 性能考虑

### 锁粒度

```python
# 粗粒度（当前实现）
with self._lock:
    self._value += 1
    self._log.append(...)
    
# 细粒度（优化版本）
with self._lock:
    self._value += 1
    new_value = self._value
# 日志记录可以在锁外进行
self._log.append(new_value)
```

### 读写锁优化

对于读多写少的场景，可以使用读写锁：
```python
from threading import RLock
# 允许多个读者同时访问
```

## 与其他测试的关联

- **ST-M-001**: 基础RPC（无状态）
- **ST-M-004**: 并发RPC调用（压力测试）
- **ST-M-009**: Fire-and-Forget（无状态单向）

## 未来改进

1. **分布式状态**
   - 使用Redis等外部存储
   - 跨服务实例的状态共享

2. **事务支持**
   - 多操作原子性
   - 回滚机制

3. **乐观锁**
   - 版本号机制
   - CAS操作

4. **状态持久化**
   - 定期快照
   - WAL日志

## 参考文档

- [someip-bus-test-plan.md](../../../someip-bus-test-plan.md) - 完整测试计划
- [ST-M-001](../ST-M-001/README.md) - 基础RPC测试
- Python threading.Lock 文档
