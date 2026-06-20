# Skill Deviation Tracker (repo-local: tinySOA)

记录本仓库 `tinysoa-*` skill 偏差的偏差日志。由 `skill-evolution` 引擎维护。
全局 `~/.claude/skills/skill-evolution/DEVIATION_TRACKER.md` 不再写入；本仓库的偏差记在这里，随仓库版本管理。

> **项目定位**：本仓库正在开发的是 **tinySOA** —— 一个轻量服务架构（SOA）框架，源码在
> `tinySOA/src/tinysoa/`（子包：core / api / spi / eventbus / runtime / policies / obs / config），
> 设计文档在 `design/`。`someip`（pysomeip 库）是 tinySOA 支持的**协议栈之一**
> （通过 `eventbus/someip.py` 的 `SomeIPEventBus` 实现 `EventBus` ABC），与 `InMemoryEventBus`、
> `TCPEventBusServer/Client` 并列。这些 skill 面向 tinySOA 的开发，而非单一协议栈。
>
> **测试/运行约定**：tinySOA 用 **pytest + pytest-asyncio**（不是 unittest），通过 `PYTHONPATH=src`
> 运行，`cd tinySOA && PYTHONPATH=$PWD/src uvx pytest -q tests`。协议栈层（someip）需要先在仓库根
> `pip install -e .` 以便 `import someip`。

置信度规则：MED 首次出现 → 记录为 PENDING_SECOND_OCCURRENCE；同类型第 2 次出现 → 升级 HIGH → 触发 SKILL.md patch。

---

## Current Deviations (Active)

（暂无。skill 投入使用后，偏差会出现在这里。）

---

## Completed Evolution Cycles

（无）
