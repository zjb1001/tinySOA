# ST-M-002: Multi-Service RPC Chain

## 测试状态

✅ **测试通过** (2025-12-21)

## 测试目标

验证SOME/IP RPC调用能够在多个服务之间形成调用链，包括：
- 跨服务的RPC调用传播
- 多跳调用的正确性
- 调用链的端到端完整性
- 分布式追踪能力（未来实现）

## 测试规格

**测试ID**: ST-M-002  
**测试类别**: 系统集成测试 - RPC调用链  
**优先级**: P1 (重要)  
**追溯性**: TC-M-002 (同步请求-响应调用)

## 测试配置

### 服务架构

```
Service A (Client)
    |
    | RPC: add_then_multiply(3, 5)
    v
Service B (Middle)
    |
    | Step 1: Calculate 3 + 5 = 8
    | Step 2: RPC: multiply(8, 2)
    v
Service C (Leaf)
    |
    | Calculate: 8 * 2 = 16
    v
Result: 16
```

### 服务配置

#### Service C (端点服务)
- **Service ID**: 0x3000
- **Instance ID**: 0x0001
- **Port**: 33000
- **Method**: `multiply(x, y) -> x * y`
- **Method ID**: 0x0001

#### Service B (中间服务)
- **Service ID**: 0x2000
- **Instance ID**: 0x0001
- **Port**: 32000
- **Method**: `add_then_multiply(a, b) -> (a + b) * 2`
- **Method ID**: 0x0001
- **内部逻辑**:
  1. 计算 a + b
  2. 调用 Service C 的 multiply 方法
  3. 返回结果

#### Service A (客户端)
- **Role**: 测试客户端
- **Operation**: 调用 Service B 的 add_then_multiply(3, 5)
- **Expected Result**: 16

## 测试步骤

1. **启动 Service C**
   - 绑定端口 33000
   - 注册 multiply 方法
   
2. **启动 Service B**
   - 绑定端口 32000
   - 注册 add_then_multiply 方法
   - 准备调用 Service C
   
3. **启动 Service A (测试客户端)**
   - 等待所有服务就绪
   - 调用 Service B: add_then_multiply(3, 5)
   
4. **验证调用链**
   - Service A -> Service B: 发送 (3, 5)
   - Service B: 计算 3 + 5 = 8
   - Service B -> Service C: 发送 (8, 2)
   - Service C: 计算 8 * 2 = 16
   - Service C -> Service B: 返回 16
   - Service B -> Service A: 返回 16
   
5. **验证结果**
   - Service A 接收到结果 16
   - 测试通过

## 运行测试

### 执行命令

```bash
cd /home/page/GitPlayground/pysomeip
python tinySOA/tests/system_tests/ST-M-002/run_test.py
```

### 预期输出

```
INFO - ST-M-002-ORCH - Starting ST-M-002 orchestrator (Multi-Service RPC Chain)
INFO - ST-M-002-ORCH - Service C started (PID=xxx, Port=33000)
INFO - ST-M-002-ServiceC - Service C ready - Method 0x0001 (multiply) registered
INFO - ST-M-002-ORCH - Service B started (PID=xxx, Port=32000)
INFO - ST-M-002-ServiceB - Service B ready - Method 0x0001 (add_then_multiply) registered
INFO - ST-M-002-ORCH - Service A started (PID=xxx)
INFO - ST-M-002-ServiceA - Calling Service B: add_then_multiply(3, 5)
INFO - ST-M-002-ServiceB - Received request add_then_multiply(3, 5)
INFO - ST-M-002-ServiceB - Step 1: 3 + 5 = 8
INFO - ST-M-002-ServiceB - Step 2: Calling Service C multiply(8, 2)
INFO - ST-M-002-ServiceC - Received request multiply(8, 2)
INFO - ST-M-002-ServiceC - Returning result: 16
INFO - ST-M-002-ServiceB - Step 3: Got result from Service C: 16
INFO - ST-M-002-ServiceA - Final result: 16
INFO - ST-M-002-ServiceA - ✅ TEST PASSED: Got expected result 16
INFO - ST-M-002-ORCH - ✅ ST-M-002 orchestrator completed successfully
```

## 验证点

- ✅ 服务启动和初始化
- ✅ Method 注册
- ✅ Service A -> Service B 调用成功
- ✅ Service B 本地计算正确 (3 + 5 = 8)
- ✅ Service B -> Service C 调用成功
- ✅ Service C 计算正确 (8 * 2 = 16)
- ✅ 响应正确传播回 Service A
- ✅ 最终结果验证 (16)

## 技术要点

### RPC 调用链实现

1. **同步调用模式**
   - Service B 的 handler 是同步函数
   - 内部使用 `loop.run_until_complete()` 执行异步 RPC 调用
   - 保持调用链的顺序性

2. **客户端封装**
   - `RPCClient` 类封装 SOME/IP 客户端逻辑
   - 提供简单的 `call()` 接口
   - 自动处理请求/响应匹配

3. **超时处理**
   - 每个 RPC 调用都有超时保护
   - Service A 设置 10 秒超时（包含整个调用链）
   - Service B 调用 Service C 使用 5 秒超时

### SOME/IP 消息流

```
Time  Service A         Service B         Service C
  |                                           
  |  --> REQUEST(add_then_multiply, 3, 5)
  |                    |
  |                    | (calculate 3+5=8)
  |                    |
  |                    | --> REQUEST(multiply, 8, 2)
  |                                        |
  |                                        | (calculate 8*2=16)
  |                                        |
  |                    | <-- RESPONSE(16)
  |                    |
  |  <-- RESPONSE(16)
  |
```

## 未来改进

1. **分布式追踪**
   - 传播 trace_id 通过所有服务
   - 记录每跳延迟
   - 生成调用链可视化

2. **错误传播**
   - 中间服务异常的传播机制
   - 调用链断开的恢复策略

3. **性能优化**
   - 异步调用链（非阻塞）
   - 连接池管理
   - 并行调用支持

4. **监控指标**
   - 调用链深度统计
   - 端到端延迟监控
   - 失败率追踪

## 参考文档

- [ST-M-001](../ST-M-001/README.md) - 基础 RPC 调用测试
- [design/02-core-components.md](../../../../design/02-core-components.md) - 核心组件设计
