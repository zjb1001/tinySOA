# tinySOA — Claude Code skill 套件

本目录是 **tinySOA**（轻量服务架构 / SOA 框架）专属的 Claude Code skill 集合。
源码在 `tinySOA/src/tinysoa/`，设计文档在 `design/`。

> **定位**：本仓库开发的是 tinySOA 框架。`someip`（pysomeip）是 tinySOA 支持的**协议栈之一**
> （`eventbus/someip.py` 的 `SomeIPEventBus` 实现 `EventBus` ABC），与 `InMemoryEventBus`、
> `TCPEventBusServer/Client` 并列。这些 skill 面向 tinySOA 整体开发，协议栈只是其中一层。

## Skill 清单

| Skill | 角色 | 说明 |
|-------|------|------|
| `/tinysoa-dev` | 功能开发编排器 | 需求分析 → 设计 → 实现 → 风格门 → 红蓝审查 → 测试 → 集成的 7 阶段闭环 |
| `/tinysoa-pr` | PR 审查 + 修复编排器 | 分析变更、评估影响、红蓝审查、生成修复、验证 |
| `/tinysoa-review` | 红蓝对抗代码审查 | 红/蓝/约束校验三 agent 并行，输出共识报告与门决策 |
| `/tinysoa-style` | 代码风格与约束守门人 | ABC 契约、async 安全、类型注解；black/ruff/mypy 自动检查 |
| `/tinysoa-test` | 测试工程师 | 设计测试策略，生成 pytest/pytest-asyncio 测试并跑通 |
| `/tinysoa-debug` | 结构化调试 | 四阶段根因优先（复现 → 根因 → 修复 → 验证） |
| `/tinysoa-teach` | tinySOA / SOA 教学助手 | 10 模块课程，Why→What→How→Trap→Connection |
| `/tinysoa-lab` | 动手实验指导 | 10 个渐进式实验，与 teach 配对 |

## 协作关系

```
/tinysoa-dev ──┬──► /tinysoa-style (风格门)
               ├──► /tinysoa-review (质量门，红蓝对抗)
               ├──► /tinysoa-test   (测试门)
               └──► skill-evolution (演进反馈)

/tinysoa-pr ───┬──► /tinysoa-style
               └──► /tinysoa-review

/tinysoa-teach ◄────► /tinysoa-lab (教学-实验对)
```

## tinySOA 架构速览（skill 引用的真相源）

```
应用层（业务服务、消费者）
        ↓
tinySOA 框架层
  ServiceRegistry / ServiceInvoker   (api/)   ← ABC 契约
  EventPublisher / EventSubscriber   (api/)
  EventBus (ABC) ──┬─ InMemoryEventBus      (单进程)
                   ├─ TCPEventBusServer/Client (开发/演示)
                   └─ SomeIPEventBus        (生产，基于 pysomeip)  ← 协议栈之一
  Container / LifecycleManager       (runtime/)
  Interceptor / InterceptorChain     (spi/)
  Retry / Timeout / CircuitBreaker   (policies/)
  Metrics / Tracing                  (obs/)
  ConfigLoader / Config              (config/)
        ↓
SOME/IP 协议层（pysomeip）/ asyncio 传输（UDP/TCP）
```

关键事实：
- **ServiceStatus 状态机**：`INIT → REGISTERED → RUNNING → STOPPED → TERMINATED`，非法跳转抛 `StateError`（`core/model.py`）。
- **EventBus ABC**（`eventbus/bus.py`）：`publish` / `subscribe` / `unsubscribe` / `get_subscribers_count` 四个抽象方法 —— 这是协议栈的接入缝。
- **SOME/IP 是协议栈之一**：`SomeIPEventBus(EventBus)` 在 `eventbus/someip.py`，把 topic 映射到 SOME/IP eventgroup，复用 pysomeip 的 SD 与 SimpleService。
- **测试/运行**：pytest + pytest-asyncio；`cd tinySOA && export PYTHONPATH=$PWD/src`；`uvx pytest -q tests`。

## 文件

- `settings.json` / `settings.local.json` — 本仓库权限（tinySOA 的 pytest/uv/examples 命令已预授权）。
- `DEVIATION_TRACKER.md` — `tinysoa-*` skill 的偏差日志，由 `skill-evolution` 维护。
