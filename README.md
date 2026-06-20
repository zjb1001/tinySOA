# tinySOA

tinySOA 是一个基于设计文档（见仓库 design/ 目录）的轻量服务架构实现。本目录归拢了与 tinySOA 相关的所有源码、测试、工具与示例，配合 `tinySOA/plan.md` 逐步推进开发。

- 计划文件：`tinySOA/plan.md`
- 设计文档目录：`design/`

## 目录结构
- `src/tinysoa/`：核心源码（core/runtime/api/spi/policies/eventbus/obs 等）
- `tests/`：测试用例
- `examples/`：示例（echo 服务、一发多收、多发一收）
- `tools/`：辅助工具

## 安装与环境
无需安装到 site-packages，直接通过 `PYTHONPATH=src` 运行；或配合 uv：

```bash
cd tinySOA
export PYTHONPATH=$PWD/src
```

## 快速开始
- Echo 服务示例：
```bash
PYTHONPATH=src python examples/echo_service/app.py --help
```
- Pub/Sub：一发布者，多订阅者：
```bash
PYTHONPATH=src python examples/pubsub_multi/server.py --host 127.0.0.1 --port 8765
PYTHONPATH=src python examples/pubsub_multi/subscriber.py sub-1 --topic demo.topic --host 127.0.0.1 --port 8765
PYTHONPATH=src python examples/pubsub_multi/subscriber.py sub-2 --topic demo.topic --host 127.0.0.1 --port 8765
PYTHONPATH=src python examples/pubsub_multi/publisher.py --topic demo.topic --count 5 --interval 1.0 --host 127.0.0.1 --port 8765
```
- Pub/Sub：多发布者，一订阅者：
```bash
PYTHONPATH=src python examples/pubsub_multi/server.py --host 127.0.0.1 --port 8767
PYTHONPATH=src python examples/pubsub_multi/subscriber.py collector --topic demo.topic --host 127.0.0.1 --port 8767
PYTHONPATH=src python examples/multi_publishers_single_sub/publisher_with_id.py pub-A --topic demo.topic --count 5 --interval 0.5 --host 127.0.0.1 --port 8767
PYTHONPATH=src python examples/multi_publishers_single_sub/publisher_with_id.py pub-B --topic demo.topic --count 5 --interval 0.7 --host 127.0.0.1 --port 8767
```

## 主要能力
- 运行时容器与生命周期管理
- 拦截器/插件（日志、指标、追踪）
- 配置系统（schema + loader）
- 策略库：超时、重试、熔断（支持 backoff 与抖动）
- 事件总线：内存版 InMemoryEventBus 与开发用 TCPEventBus

策略使用示例：
```python
from tinysoa.policies import RetryPolicy, exponential_backoff, full_jitter

policy = RetryPolicy(max_attempts=3, backoff=exponential_backoff(0.1), jitter=full_jitter(0.05))
@policy
def fragile_call():
    ...
```

## 使用 uv 运行测试
如你本地使用 uv 管理环境，推荐以下两种方式运行测试：

- 临时工具方式（无需激活虚拟环境）：

```bash
cd tinySOA
PYTHONPATH=$PWD/src uvx pytest -q tests
```

- 项目虚拟环境方式：

```bash
cd tinySOA
uv venv .venv
source .venv/bin/activate
uv pip install -U pytest
PYTHONPATH=$PWD/src pytest -q tests
```

提示：如未安装 uv，可参考官方安装脚本（可选）：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
