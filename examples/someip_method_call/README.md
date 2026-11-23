# SOME/IP Calculator RPC

拓扑：`PEER`。Server 通过 SD 通告服务，Client 发现后发起 REQUEST/RESPONSE
方法调用（不是 pub/sub）。

## 方法

| 方法 | ID | 说明 |
|---|---|---|
| `add` | `0x0001` | 加法 |
| `subtract` | `0x0002` | 减法 |
| `multiply` | `0x0003` | 乘法 |

服务：`service_id=0x4444`，`instance_id=0x0001`。payload 为 JSON。

## 目录

```text
someip_method_call/
  calculator_contract.py  server/client 共享的 service 与 method ID
  server.py               SomeIPService + async method handlers
  client.py               SomeIPService.invoke + 3 次 RPC
  tmux.sh                 左: Server / 右: Client
  Makefile                start/stop/status/logs/smoke/tmux
```

应用代码只写逻辑方法名：

```python
# server.py
service = SomeIPService(server_config(30950), is_publisher=True)

@service.method("add")
async def add(payload: dict) -> dict:
    return {"result": payload["a"] + payload["b"]}

await service.start()


# client.py
service = SomeIPService(client_config(30960), is_publisher=False)
await service.start()
response = await service.invoke("add", {"a": 10, "b": 7})
```

SD、REQUEST/RESPONSE、session 匹配、JSON 编解码、错误响应都由框架处理。

## 运行

```bash
export PYTHONPATH="$PWD:$PWD/src:$PWD/third_party/pysomeip/src"

# 终端 1
python -m examples.someip_method_call.server

# 终端 2
python -m examples.someip_method_call.client
```

## Make 快捷方式

```bash
make smoke-calc       # Server 启动 → Client 调 3 个方法 → 验证
make tmux-calc        # tmux 双窗格
```

## 观察点

- Server 日志出现 SD Offer。
- Client 依次收到 `add(10,7)=17`、`subtract(50,18)=32`、`multiply(6,8)=48`。
- 方法调用是 unicast REQUEST/RESPONSE，不经过 broker。
