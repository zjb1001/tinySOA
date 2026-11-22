# Local echo service

拓扑：`LOCAL`（`InMemoryEventBus`，单进程、无网络）。
这是最小的完整 SOA 闭环：Service 定义 → 方法调用 → 事件发布/订阅。

## 目录

```text
local_echo_service/
  app.py        EchoServiceApp：Service + InMemoryEventBus + InterceptorChain
  Makefile      run/smoke/clean
```

## 运行

```bash
make -C examples/local_echo_service run
# 或
PYTHONPATH=$PWD:$PWD/src python -m examples.local_echo_service.app
```

## 观察点

- `say` 方法被调用，返回 payload。
- `echo.said` 事件在方法调用后到达订阅者。
- 整个过程不启动线程、不绑定端口，适合作为测试基线。
