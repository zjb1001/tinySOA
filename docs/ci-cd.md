# 本地 CI/CD

tinySOA 当前采用 **本地 CI 脚本**（不依赖 GitHub Actions）。目标是把“改完就跑
一次”固化成可重复的门禁，同时为后续接入任何 CI 平台保留同一套命令。

## 门禁策略

| 检查 | 默认行为 | 说明 |
|---|---|---|
| `pytest tests` | **阻断** | 任何失败退出码非 0 |
| `ruff check` | **阻断** | 未安装则 SKIP |
| `black --check` | **阻断** | 未安装则 SKIP |
| `mypy src/tinysoa` | **阻断** | 未安装则 SKIP |
| examples smoke | 可选 | `--with-smoke` / `--smoke-only` |

默认即为严格模式。需要临时降级时使用 `--advisory` / `make ci-advisory`：
pytest 仍然阻断，ruff/black/mypy 只记录 WARN。

## 常用命令

```bash
# 推荐入口（根目录 Makefile）
make ci                  # pytest + ruff/black/mypy 全部阻断（默认）
make ci-advisory         # pytest 阻断，质量检查仅告警
make ci-strict           # make ci 的兼容别名
make ci-coverage         # pytest + coverage
make test                # 只跑 pytest
make lint                # ruff + black
make typecheck           # mypy
make smoke               # examples 稳定冒烟组

# 直接调用脚本
bash scripts/ci.sh
bash scripts/ci.sh --advisory
bash scripts/ci.sh --tests-only
bash scripts/ci.sh --with-smoke
bash scripts/ci.sh --coverage
```

环境变量：

- `PYTHON`：解释器，默认 `.venv/bin/python`，否则 `python3`。
- `CI_ROOT`：要测试的仓库根目录，默认脚本上一级。

## 安装开发工具

```bash
python -m pip install -r requirements-dev.txt
```

如果只想跑测试，至少需要 `pytest` 和 `pytest-asyncio`。`pyproject.toml` 已配置
`pythonpath = ["src", "third_party/pysomeip/src"]`，脚本也会显式设置
`PYTHONPATH`，两种方式都可用。

## 冒烟组

`make smoke` 只跑稳定、可重复的快速子集：

```bash
make -C examples smoke-vdp smoke-calc smoke-pubsub-one-pub-many-subs
```

`make -C examples smoke-all` 额外包含 SOME/IP 事件冒烟。
SOME/IP 事件冒烟的默认参数已按订阅延迟调优：

```bash
make -C examples smoke-someip-one-pub-many-subs   # 1 pub → N subs，20 条 @ 1.0s
make -C examples smoke-someip-many-pubs-one-sub   # N pubs → 1 sub，30 条 @ 0.5s，AGG_COUNT=9
```

WSL2 回环上 SD 仍可能偶发竞态；失败时先确认没有遗留 SOME/IP 进程。

## 本地发布（CD）

`scripts/release.sh` 把“验证过的源码快照”作为发布单元：

```bash
# 仅创建本地 tag，不推送
bash scripts/release.sh --version v0.3.0

# 跑 CI -> 打 tag -> 推送 -> 创建 GitHub Release
bash scripts/release.sh --version v0.3.0 --notes RELEASE_NOTES.md --yes
```

前提：工作区干净、当前在 `main`、本地不比 `origin/main` 落后、`gh` 已登录。
发布不会构建 wheel 或部署服务；仓库当前没有打包/部署目标。

## 后续接入 GitHub Actions

如果以后要搬到 GitHub Actions，直接复用 `scripts/ci.sh` 即可，例如：

```yaml
- uses: actions/checkout@v4
  with: { submodules: recursive }
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: python -m pip install -r requirements-dev.txt
- run: bash scripts/ci.sh
```

这样本地和 CI 不会出现两套命令漂移。
