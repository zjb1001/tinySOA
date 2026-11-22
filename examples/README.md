# tinySOA examples

所有案例都以 **包模块** 运行：

```bash
PYTHONPATH=$PWD:$PWD/src:$PWD/third_party/pysomeip/src \
  python -m examples.<name>.<module>
```

推荐从仓库根目录使用 Makefile（本地 CI 也用同一套命令）：

```bash
make -C examples help
make -C examples smoke-all
```

## 命名约定

| 前缀 | 拓扑 | 说明 |
|---|---|---|
| `local_*` | `LOCAL` | 进程内 `InMemoryEventBus`，无网络 |
| `tcp_*` | `BROKER` | 中心 `TCPEventBusBroker`，客户端 `TCPEventBus` |
| `someip_*` | `PEER` | SOME/IP SD 发现，无中心 broker |

## 案例目录

| 案例 | 拓扑 | 进程 | 入口 | 观察重点 |
|---|---|---|---|---|
| `local_echo_service` | LOCAL | 单进程 | `local_echo_service.app` | 方法调用 + 事件 |
| `local_interceptor_auth` | LOCAL | 单进程 | `local_interceptor_auth.app` | 拦截器排序 / Auth 短路 / 异常传播 |
| `local_vehicle_platform` | LOCAL | 单进程 | `local_vehicle_platform.app` | Container 依赖/生命周期/健康检查 |
| `local_pubsub_topologies` | LOCAL | 单进程 | `local_pubsub_topologies.app` | 1v1 / 1vN / Nv1 应用 API 观察 |
| `tcp_pubsub_one_to_many` | BROKER | broker + pub + N sub | `tcp_pubsub_one_to_many.{server,publisher,subscriber}` | TCP 中心 broker 扇出 |
| `tcp_pubsub_many_to_one` | BROKER | broker + sub + N pub | `tcp_pubsub_many_to_one.publisher_with_id` | 多来源聚合、publisher_id |
| `someip_pubsub_echo` | PEER | pub + sub | `someip_pubsub_echo.{publisher,subscriber}` | 1v1：SD Offer/FindSubscribe |
| `someip_pubsub_one_to_many` | PEER | 1 pub + N sub | `someip_pubsub_one_to_many.{publisher,subscriber}` | 1vN：同一服务多订阅者 |
| `someip_pubsub_multi_sensor` | PEER | 3 pub + agg | `someip_pubsub_multi_sensor.*` | Nv1：多服务发现、聚合仪表盘 |
| `someip_method_call` | PEER | server + client | `someip_method_call.{server,client}` | SOME/IP RPC |
| `someip_cross_process` | PEER | orchestrator + 2 进程 | `someip_cross_process.run_cross_process` | 真实跨进程事件投递 |

## 常用命令

```bash
# 本地单进程
make -C examples echo
make -C examples interceptors
make -C examples vdp
make -C examples topologies
make -C examples topologies SCENARIO=1vn SUBSCRIBERS=5

# TCP broker
make -C examples tmux-pubsub
make -C examples tmux-pubsub-many
make -C examples smoke-pubsub
make -C examples smoke-pubsub-many

# SOME/IP
make -C examples tmux-echo-someip
make -C examples tmux-someip-one-to-many
make -C examples tmux-someip
make -C examples tmux-xprocess
make -C examples smoke-calc

# 全局
make -C examples smoke-all
make -C examples clean-all
```

每个案例目录都有自己的 `Makefile` 和 `README.md`；单进程案例用 `make run`，
多进程案例用 `make start/stop/logs/smoke/tmux`。
