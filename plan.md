# tinySOA 渐进式开发计划（Plan）

本文件用于指导 tinySOA 的逐步实现，每一阶段均标注产出与参考设计文档，按阶段推进即可保持上下文连贯。所有源码与样例均统一归拢在 `tinySOA/` 目录下。

- 设计文档目录（相对当前文件）：`../design/`
  - [00-revision-summary.md](../design/00-revision-summary.md)
  - [01-overview.md](../design/01-overview.md)
  - [02-core-components.md](../design/02-core-components.md)
  - [03-api-design.md](../design/03-api-design.md)
  - [04-lifecycle.md](../design/04-lifecycle.md)
  - [05-interceptors-plugins.md](../design/05-interceptors-plugins.md)
  - [06-configuration.md](../design/06-configuration.md)
  - [07-monitoring-tracing.md](../design/07-monitoring-tracing.md)
  - [08-best-practices.md](../design/08-best-practices.md)
  - [09-internal-event-model.md](../design/09-internal-event-model.md)

## 阶段 0：Bootstrap 与目录约定
- 目标：建立最小项目结构与基础规范，便于后续增量实现。
- 产出：
  - 目录结构：
    - `tinySOA/src/tinysoa/`（源码）
    - `tinySOA/tests/`（测试）
    - `tinySOA/examples/`（样例）
    - `tinySOA/tools/`（辅助工具）
    - `tinySOA/plan.md`（本计划）
    - `tinySOA/README.md`（使用与开发指南）
  - 最小包骨架：`src/tinysoa/__init__.py`
- 参考设计文档：
  - [01-overview.md](../design/01-overview.md)
  - [03-api-design.md](../design/03-api-design.md)
- 验收标准：
  - 目录可用、可在后续阶段直接落文件与代码；README 能说明如何本地开发与运行样例。

## 阶段 1：核心概念与基础类型
- 目标：定义核心领域模型与类型（Service、Method、Event、Message、Error、Status、Endpoint 等）。
- 产出：
  - `src/tinysoa/core/model.py`：核心实体与枚举
  - `src/tinysoa/core/errors.py`：错误与异常体系
  - `tests/test_core_model.py`：基本单元测试
- 参考设计文档：
  - [02-core-components.md](../design/02-core-components.md)
- 验收标准：
  - 模型满足核心关系表达；单测覆盖关键约束（如 ID 唯一性、状态迁移约束、序列化基础）。

## 阶段 2：API 合同与对外接口骨架
- 目标：给出对外 API 的抽象接口，先有合同、后有实现（Interface First）。
- 产出：
  - `src/tinysoa/api/service_api.py`：服务注册、发现、调用的接口定义
  - `src/tinysoa/api/event_api.py`：事件发布/订阅接口定义
  - `tests/test_api_contracts.py`：接口层行为约束的契约测试（可用假实现/Mock）
- 参考设计文档：
  - [03-api-design.md](../design/03-api-design.md)
- 验收标准：
  - API 稳定且与设计一致；后续实现不破坏公共签名。

## 阶段 3：运行时与生命周期管理
- 目标：实现服务容器、启动/停止、健康检查、优雅关闭。
- 产出：
  - `src/tinysoa/runtime/container.py`：服务容器与运行时上下文
  - `src/tinysoa/runtime/lifecycle.py`：生命周期管理器
  - `tests/test_runtime_lifecycle.py`
- 参考设计文档：
  - [04-lifecycle.md](../design/04-lifecycle.md)
- 验收标准：
  - 服务可被注册、启动、停止；具备基本健康检查逻辑与钩子。

## 阶段 4：拦截器与插件机制（SPI）
- 目标：提供调用链路拦截、插件扩展点（如鉴权、限流、重试、熔断）。
- 产出：
  - `src/tinysoa/spi/interceptor.py`：拦截器接口与链式调度
  - `src/tinysoa/spi/plugin.py`：插件接口、加载与生命周期
  - `tests/test_interceptors_plugins.py`
- 参考设计文档：
  - [05-interceptors-plugins.md](../design/05-interceptors-plugins.md)
- 验收标准：
  - 可插拔的拦截器/插件；支持顺序/条件执行；对失败策略有明确定义。

## 阶段 5：配置系统
- 目标：提供统一配置加载、合并、校验与动态刷新能力。
- 产出：
  - `src/tinysoa/config/schema.py`：配置模式与校验
  - `src/tinysoa/config/loader.py`：多源加载（文件、环境变量、代码注入）
  - `tests/test_config_system.py`
- 参考设计文档：
  - [06-configuration.md](../design/06-configuration.md)
- 验收标准：
  - 支持最少文件+环境变量双源；有健壮的校验与默认策略。

## 阶段 6：监控与追踪
- 目标：暴露指标、日志语义化、分布式链路追踪（可选接入 OpenTelemetry）。
- 产出：
  - `src/tinysoa/obs/metrics.py`：关键指标（QPS、延迟、错误率等）
  - `src/tinysoa/obs/tracing.py`：追踪封装与拦截器集成
  - `tests/test_observability.py`
- 参考设计文档：
  - [07-monitoring-tracing.md](../design/07-monitoring-tracing.md)
- 验收标准：
  - 基本指标可采集；追踪上下文可贯穿一次服务调用。

## 阶段 7：内部事件模型与消息总线
- 目标：建立内部事件总线，支持发布/订阅、持久化或内存通道（先内存，后可扩展）。
- 产出：
  - `src/tinysoa/eventbus/bus.py`：事件总线接口与内存实现
  - `src/tinysoa/eventbus/message.py`：事件消息与序列化协议
  - `tests/test_event_bus.py`
- 参考设计文档：
  - [09-internal-event-model.md](../design/09-internal-event-model.md)
- 验收标准：
  - 订阅/发布可用；在压测下无明显资源泄漏；与拦截器/监控可集成。

## 阶段 8：工程化与最佳实践加固
- 目标：落地重试、超时、熔断、回退、幂等、容错策略等最佳实践。
- 产出：
  - `src/tinysoa/policies/*.py`：策略库（超时、重试、熔断等）
  - `tests/test_policies.py`
- 参考设计文档：
  - [08-best-practices.md](../design/08-best-practices.md)
- 验收标准：
  - 策略可配置、可观测、与拦截器链互通；失败模式有明确度量。

## 阶段 9：工具与示例
- 目标：提供开发者友好的 CLI/工具与最小示例服务。
- 产出：
  - `tools/`：脚手架/诊断/压测小工具
  - `examples/echo-service/`：最小可运行服务示例（含事件与监控）
  - `tests/`：集成测试或端到端冒烟测试
- 参考设计文档：
  - 综合参考 [01-overview.md](../design/01-overview.md)、[03-api-design.md](../design/03-api-design.md)
- 验收标准：
  - 示例可启动、可调用、可观测；工具可辅助本地调试与诊断。

## 阶段 10：文档与版本发布
- 目标：补充使用文档、架构说明与版本发布说明，与修订记录对齐。
- 产出：
  - `README.md`：用户/开发者指引
  - `CHANGELOG.md`：依据修订记录整理版本说明
- 参考设计文档：
  - [00-revision-summary.md](../design/00-revision-summary.md)
- 验收标准：
  - 文档可读、结构清晰；版本说明与实现范围一致。

---

## 工作方式建议
- 迭代粒度：以“阶段”为最小可交付单元；阶段内可再拆任务。
- 质量闸门：每阶段合入前需通过单测与基础静态检查。
- 里程碑节奏：0→3 完成基本可运行；4→8 完成工程化；9→10 出示例与说明。

## 快速起步（本地开发）
- 推荐在仓库根目录使用以下命令为 tinySOA 运行测试（根据需要调整环境）：

```bash
# 进入 tinySOA 目录工作
cd tinySOA

# 建议使用虚拟环境（可选）
python -m venv .venv
source .venv/bin/activate
pip install -U pip

# 后续阶段增加依赖后，这里会补充安装步骤
# pytest 等工具将在对应阶段加入
```
