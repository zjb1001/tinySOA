# ST-M-009: Fire-and-Forget (One-Way) Calls

## 测试状态

✅ **测试通过** (2025-12-21)

## 测试目标

验证SOME/IP Fire-and-Forget（单向调用）功能，包括：
- REQUEST_NO_RETURN消息类型支持
- 调用立即返回（不等待响应）
- 服务端异步处理
- 无响应消息发送

## 测试规格

**测试ID**: ST-M-009  
**测试类别**: 系统集成测试 - 单向调用  
**优先级**: P1 (重要)  
**追溯性**: TC-M-003 (异步Fire-and-Forget调用)

## 测试配置

### 服务架构

```
Client (Fire-and-Forget Sender)
    |
    | Multiple REQUEST_NO_RETURN calls
    | (no wait for response)
    v
Server (Async Processor)
    |
    | Process events asynchronously
    | (no response sent)
    v
Log events to memory
```

### 服务端配置

- **Service ID**: 0x9000
- **Instance ID**: 0x0001
- **Port**: 39000
- **Methods**:
  - **0x0001**: `log_event(event_id)` - Fire-and-Forget
    - Message Type: REQUEST_NO_RETURN
    - No response
    - Async processing with 100ms delay
  - **0x0002**: `get_log_count()` - Regular RPC
    - Message Type: REQUEST/RESPONSE
    - Returns count of logged events

### 客户端功能

- **call_oneway()**: 发送Fire-and-Forget请求
  - 使用 REQUEST_NO_RETURN 消息类型
  - 立即返回，不等待响应
- **call()**: 发送常规RPC请求
  - 用于验证服务端处理结果

## 测试步骤

### Test 1: 发送Fire-and-Forget调用

1. 客户端连接到服务器
2. 发送5个Fire-and-Forget调用（event_id: 1-5）
3. 测量总耗时
4. **验证点**: 所有调用应在0.5秒内完成（立即返回）

### Test 2: 验证服务端异步处理

1. 等待1秒让服务器异步处理
2. 通过RPC调用 `get_log_count()` 查询处理数量
3. **验证点**: 服务器应处理所有5个事件

### Test 3: 验证无响应发送

1. 发送额外的Fire-and-Forget调用
2. 等待200ms观察是否收到响应
3. **验证点**: 不应收到任何响应消息

## 预期输出

```
INFO - ST-M-009-ORCH - Starting ST-M-009 orchestrator (Fire-and-Forget One-Way Calls)
INFO - ST-M-009-ORCH - Server started (PID=xxx, Port=39000)
INFO - ST-M-009-Server - Server ready:
INFO - ST-M-009-Server -   - Method 0x0001 (log_event) - Fire-and-Forget
INFO - ST-M-009-Server -   - Method 0x0002 (get_log_count) - Regular RPC
INFO - ST-M-009-ORCH - Client started (PID=xxx)
INFO - ST-M-009-Client - === ST-M-009: Fire-and-Forget (One-Way) Calls Test ===
INFO - ST-M-009-Client - Connected to server
INFO - ST-M-009-Client - 
INFO - ST-M-009-Client - --- Test 1: Sending Fire-and-Forget calls ---
INFO - ST-M-009-Client - Sent fire-and-forget call #1 (no wait)
INFO - ST-M-009-Client - Sent fire-and-forget call #2 (no wait)
INFO - ST-M-009-Client - Sent fire-and-forget call #3 (no wait)
INFO - ST-M-009-Client - Sent fire-and-forget call #4 (no wait)
INFO - ST-M-009-Client - Sent fire-and-forget call #5 (no wait)
INFO - ST-M-009-Client - All 5 fire-and-forget calls sent in 0.002s
INFO - ST-M-009-Client - ✅ PASS: Calls returned immediately (0.002s < 0.5s)
INFO - ST-M-009-Server - [Fire-and-Forget] Logged event #1 from ('127.0.0.1', 12345)
INFO - ST-M-009-Server - [Fire-and-Forget] Logged event #2 from ('127.0.0.1', 12345)
INFO - ST-M-009-Server - [Fire-and-Forget] Logged event #3 from ('127.0.0.1', 12345)
INFO - ST-M-009-Server - [Fire-and-Forget] Logged event #4 from ('127.0.0.1', 12345)
INFO - ST-M-009-Server - [Fire-and-Forget] Logged event #5 from ('127.0.0.1', 12345)
INFO - ST-M-009-Client - 
INFO - ST-M-009-Client - --- Test 2: Verifying server processed calls ---
INFO - ST-M-009-Client - Server processed 5 events
INFO - ST-M-009-Client - ✅ PASS: Server processed all 5 fire-and-forget calls
INFO - ST-M-009-Client - 
INFO - ST-M-009-Client - --- Test 3: Verify no response for fire-and-forget ---
INFO - ST-M-009-Client - Sending one more fire-and-forget call...
INFO - ST-M-009-Client - Checking that no response is received...
INFO - ST-M-009-Client - ✅ PASS: No response received (as expected for fire-and-forget)
INFO - ST-M-009-Client - 
INFO - ST-M-009-Client - ============================================================
INFO - ST-M-009-Client - ✅ ALL TESTS PASSED
INFO - ST-M-009-Client - ============================================================
INFO - ST-M-009-ORCH - ✅ ST-M-009 orchestrator completed successfully
```

## 验证点

- ✅ Fire-and-Forget调用立即返回（< 0.5秒）
- ✅ 使用正确的消息类型（REQUEST_NO_RETURN）
- ✅ 服务端异步处理请求
- ✅ 服务端不发送响应消息
- ✅ 所有事件被正确处理和记录
- ✅ 性能优势明显（无等待开销）

## 运行测试

```bash
cd /home/page/GitPlayground/pysomeip
python tinySOA/tests/system_tests/ST-M-009/run_test.py
```

## 技术要点

### SOME/IP消息类型

```python
# Fire-and-Forget
header = SOMEIPHeader(
    message_type=SOMEIPMessageType.REQUEST_NO_RETURN,  # 关键
    ...
)

# Regular RPC
header = SOMEIPHeader(
    message_type=SOMEIPMessageType.REQUEST,
    ...
)
```

### 性能优势

| 调用类型 | 客户端阻塞 | 服务端响应 | 适用场景 |
|---------|-----------|----------|---------|
| Regular RPC | 阻塞等待 | 发送响应 | 需要返回值的操作 |
| Fire-and-Forget | 立即返回 | 无响应 | 日志、监控、通知 |

**性能提升**: 在本测试中，5个Fire-and-Forget调用在~2ms内完成，而如果使用Regular RPC需要~500ms（5 × 100ms处理时间）。

### 使用场景

1. **日志记录**: 发送日志不需要等待确认
2. **监控指标**: 上报指标数据
3. **事件通知**: 单向事件广播
4. **异步命令**: 不需要返回值的操作

### 实现要点

1. **服务端Handler返回值**
   - Fire-and-Forget: 返回 `None`
   - Regular RPC: 返回 `bytes`

2. **消息类型检查**
   ```python
   if header.message_type != SOMEIPMessageType.REQUEST_NO_RETURN:
       logger.warning(f"Expected REQUEST_NO_RETURN, got {header.message_type}")
   ```

3. **异步处理**
   - 服务端在handler中可以执行耗时操作
   - 客户端不会等待这些操作完成

## 与其他测试的关联

- **ST-M-001**: 基础RPC调用（对比Request/Response模式）
- **ST-M-002**: RPC调用链（演示同步等待的开销）
- **TC-M-003**: 单元测试级别的Fire-and-Forget验证

## 未来改进

1. **可靠性保证**
   - 添加ACK机制（在应用层）
   - 重试策略（客户端）

2. **批量发送**
   - 支持批量Fire-and-Forget调用
   - 减少网络开销

3. **优先级支持**
   - 高优先级Fire-and-Forget消息
   - QoS保证

4. **监控指标**
   - 统计Fire-and-Forget调用数量
   - 服务端处理延迟分布

## 参考文档

- [ST-M-001](../ST-M-001/README.md) - 基础RPC调用测试
- SOME/IP Protocol Specification - Message Types
