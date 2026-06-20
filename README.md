# tinySOA

tinySOA 是一个基于设计文档（见仓库 design/ 目录）的轻量服务架构实现。本目录归拢了与 tinySOA 相关的所有源码、测试与示例。

- 设计文档目录：`design/`

## 快速搭建

```bash
# 1) 克隆（务必带 --recurse-submodules，否则 SOME/IP 协议栈不完整）
git clone --recurse-submodules <repo-url>
cd tinySOA

# 2) 初始化第三方依赖（已克隆但漏了 --recurse-submodules 时补跑）
git submodule update --init --recursive

# 3) 可选：创建虚拟环境用于跑测试
uv venv .venv && source .venv/bin/activate && uv pip install pytest pytest-asyncio

# 4) 跑 echo demo 验证环境
PYTHONPATH=src python examples/echo_service/app.py

# 5) 跑测试套件
.venv/bin/python -m pytest tests/unit -q          # 单元测试 (72 个, <1s)
.venv/bin/python -m pytest tests/ -q             # 全量 (131 个, ~48s)
```

> `third_party/pysomeip` 通过 git submodule 引入，**不会打包进本项目仓库**。
> 首次克隆时必须 `--recurse-submodules` 或随后执行 `git submodule update --init` 才能拿到 `someip` 包。
> pysomeip 自身无第三方依赖（仅 Python 标准库 + asyncio）。

## 目录结构
- `src/tinysoa/`：核心源码（core/runtime/api/spi/policies/eventbus/obs 等）
- `tests/`：测试用例
- `examples/`：示例（echo 服务、一发多收、多发一收）
- `third_party/`：第三方依赖（以 git submodule 形式引入）
  - `third_party/pysomeip/`：[pysomeip](https://github.com/afflux/pysomeip)，SOME/IP 协议栈（提供 `someip` 包），供 `src/tinysoa/eventbus/someip.py` 使用

## 第三方依赖（third_party）
SOME/IP 协议栈以 git submodule 形式引入 `third_party/pysomeip`（[afflux/pysomeip](https://github.com/afflux/pysomeip)，安装名为 `someip` 包）。`src/tinysoa/eventbus/someip.py` 通过它实现 SOME/IP 事件总线，与内存版 `InMemoryEventBus`、开发用 `TCPEventBus` 并列为本项目支持的协议栈之一。

**首次克隆本仓库后**，需初始化 submodule 才能拿到 `someip` 源码：

```bash
git submodule update --init --recursive
```

> 已克隆过的仓库也可用 `git clone --recurse-submodules <repo-url>` 一步到位。

pysomeip 自身无第三方依赖（仅 Python 标准库 + asyncio），无需额外安装。

### 导入路径
- **pytest**：`pyproject.toml` 的 `pythonpath` 配置会自动把 `src` 与 `third_party/pysomeip/src` 加入搜索路径，因此直接运行 `pytest` 即可，无需设置 `PYTHONPATH`。
- **直接用 `python` 运行示例/脚本**：需要同时把两个源码根放进 `PYTHONPATH`：

```bash
PYTHONPATH=src:third_party/pysomeip/src python -c "import someip; print(someip.__file__)"
```

## 安装与环境
无需安装到 site-packages，直接通过 `PYTHONPATH` 运行；或配合 uv：

```bash
cd tinySOA
# 仅用 tinysoa（不含 SOME/IP）：
export PYTHONPATH=$PWD/src
# 同时需要 SOME/IP 协议栈（eventbus/someip.py）：
export PYTHONPATH=$PWD/src:$PWD/third_party/pysomeip/src
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

> 提示：`pyproject.toml` 已配置 `pythonpath = ["src", "third_party/pysomeip/src"]`，pytest 自动解析，无需 `PYTHONPATH`。

- 临时工具方式（无需激活虚拟环境）：

```bash
cd tinySOA
uvx pytest -q tests
```

- 项目虚拟环境方式：

```bash
cd tinySOA
uv venv .venv
source .venv/bin/activate
uv pip install -U pytest
pytest -q tests
```

提示：如未安装 uv，可参考官方安装脚本（可选）：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
