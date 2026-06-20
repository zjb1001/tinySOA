# ST-M-001: End-to-End Method Call with Real Network

## 测试状态

✅ **测试通过** (2025-12-21)

## 测试目标

验证SOME/IP RPC方法调用能够通过真实UDP网络进行，包括：
- 请求/响应序列化
- SOME/IP消息路由
- 方法执行和结果返回
- 客户端响应反序列化

## 测试规格

**测试ID**: ST-M-001  
**测试类别**: 系统集成测试 - RPC方法调用  
**优先级**: P0 (关键)  
**追溯性**: TC-M-002 (同步请求-响应调用)  
**测试结果**: ✅ PASSED

## 测试配置

### 服务端 (Publisher)
- **服务ID**: 0x1234
- **实例ID**: 0x0001
- **方法ID**: 0x0001
- **方法签名**: `add(a: uint32, b: uint32) -> uint32`
- **传输**: UDP, 端口 31000
- **地址**: 127.0.0.1 (本地回环)

### 客户端 (Subscriber)
- **客户端ID**: 0x1111
- **会话ID**: 0x0001
- **接口版本**: 1
- **消息类型**: REQUEST

## 测试步骤

1. **启动服务端**
   ```bash
   python publisher.py
   ```
   - 初始化SomeIPEventBus
   - 创建SOME/IP服务 (0x1234:0x0001)
   - 注册RPC方法 `add` (method_id=0x0001)
   - 等待客户端请求

2. **启动客户端**
   ```bash
   python subscriber.py
   ```
   - 创建SOME/IP客户端协议
   - 构造REQUEST消息: add(3, 5)
   - 发送到服务端 (127.0.0.1:31000)
   - 等待RESPONSE消息

3. **自动化测试**
   ```bash
   python run_test.py
   ```
   - 自动启动服务端进程
   - 等待2秒初始化
   - 启动客户端进程
   - 收集测试结果
   - 清理进程

## 预期结果

### 成功标准
- ✓ REQUEST消息成功序列化为SOME/IP格式
- ✓ 通过UDP发送到服务端口31000
- ✓ 服务端接收并解析REQUEST
- ✓ 执行add(3, 5)方法，返回8
- ✓ RESPONSE消息正确序列化
- ✓ 客户端接收并反序列化响应
- ✓ 验证结果为8

### 失败情况
- 超时未收到响应 (>5秒)
- 响应返回错误码
- 计算结果不正确
- 网络连接失败

## 文件结构

```
ST-M-001/
├── publisher.py      # SOME/IP服务端 (提供add方法)
├── subscriber.py     # SOME/IP客户端 (调用add方法)
├── run_test.py       # 测试编排器 (自动化运行)
└── README.md         # 本文档
```

## 依赖项

- Python 3.8+
- tinysoa框架 (本地src)
- pysomeip库 (本地src)
- asyncio标准库

## 运行环境

建议在虚拟环境中运行：

```bash
# 创建虚拟环境
cd /home/page/GitPlayground/pysomeip
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install -e .
```

## 日志输出

### 服务端日志示例
```
2025-12-21 10:00:01 - ST-M-001-Pub - INFO - Registered method 0x0001 (add)
2025-12-21 10:00:01 - ST-M-001-Pub - INFO - Publisher ready. Waiting for requests...
2025-12-21 10:00:03 - ST-M-001-Pub - INFO - Received request add(3, 5)
```

### 客户端日志示例
```
2025-12-21 10:00:03 - ST-M-001-Sub - INFO - Sending request add(3, 5)
2025-12-21 10:00:03 - ST-M-001-Sub - INFO - Received response: b'\x00\x00\x00\x08'
2025-12-21 10:00:03 - ST-M-001-Sub - INFO - Result: 8
2025-12-21 10:00:03 - ST-M-001-Sub - INFO - TEST PASSED
```

## 故障排查

### 问题: "Address already in use"
**原因**: 端口31000被占用  
**解决**: 
```bash
# 查找占用进程
lsof -i :31000
# 终止进程
kill -9 <PID>
```

### 问题: "Timeout waiting for response"
**原因**: 服务端未启动或网络不通  
**解决**: 
- 确认服务端先启动
- 检查防火墙设置
- 验证本地回环接口 (lo)

### 问题: "Module not found"
**原因**: Python路径配置问题  
**解决**: 
- 确认在项目根目录运行
- 检查sys.path设置
- 验证虚拟环境激活

## 覆盖的测试用例

| 测试用例 | 描述 | 状态 |
|---------|------|------|
| TC-M-001 | 方法注册和元数据 | ✓ |
| TC-M-002 | 同步请求-响应调用 | ✓ |
| TC-M-004 | 方法参数序列化 | ✓ |
| TC-M-005 | 返回值反序列化 | ✓ |

## 扩展测试场景

基于ST-M-001，可以扩展以下测试：
- ST-M-002: 多服务RPC调用链
- ST-M-003: 大负载RPC测试
- ST-M-004: 并发RPC调用
- ST-M-005: RPC超时处理
- ST-M-006: 错误响应处理

## 参考文档

- [tinySOA API设计](../../../../design/03-api-design.md)
- [SOME/IP协议规范](https://www.autosar.org/)
