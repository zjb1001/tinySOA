# Agent Flow（本地 issue/task → PR）

`scripts/agent-flow.sh` 是 tinySOA 的本地自动化开发闭环：**实现 → 测试 → 独立评审 → 修复 → PR**。
它不绑定任何具体的 agent/harness：你通过 `AGENT_CMD` 注入自己的 agent 命令，脚手架只负责
隔离、门禁、评审循环和 PR 编排。脚手架不读取任何 harness 配置，也不依赖特定的 CLI 参数。

```
issue / task
    │
    ▼
worktree + branch (agent/...)
    │
    ▼
AGENT_CMD (stage=implement) ──► scripts/ci.sh (pytest 阻断)
    │                                  │ fail
    │                                  ▼
    │                             AGENT_CMD (stage=repair)
    ▼
AGENT_CMD (stage=review, read_only=1) ──► VERDICT: PASS / BLOCK
    │                                  │ BLOCK
    │                                  ▼
    │                             AGENT_CMD (stage=repair, 最多 --max-repair 轮)
    ▼
commit ──► push ──► gh pr create
```

## 前置条件

- `git`、`gh`（已 `gh auth login`）。
- 任意能读取 prompt 文件并修改代码的 agent 命令（aider、自研脚本等）。
- Python 环境：`python -m pip install -r requirements-dev.txt`。
- 建议先跑通 `make ci`，确认本地基线是绿的。

## Agent 适配契约

脚手架不关心你用什么 agent，只要求一个可执行命令。每次调用会：

- 在 worktree 根目录执行命令；
- 导出以下环境变量：

| 变量 | 说明 |
|---|---|
| `AGENT_STAGE` | `implement` / `review` / `repair` |
| `AGENT_PROMPT_FILE` | 渲染后的 prompt 绝对路径 |
| `AGENT_WORKTREE` | 当前 worktree 绝对路径 |
| `AGENT_RUN_DIR` | 本次运行的产物目录 |
| `AGENT_LOG_FILE` | 建议写入的日志路径（stdout/stderr 也会被捕获） |
| `AGENT_READ_ONLY` | `1` 表示评审阶段，agent 不应修改文件 |
| `PYTHON` | 推荐解释器（主仓库 `.venv` 或 python3） |
| `PYTHONPATH` | worktree 的 `src` + `third_party/pysomeip/src` |

命令退出码 `0` 表示成功；非 0 会中止流程并保留 worktree。stdout/stderr 自动写入
`AGENT_LOG_FILE`。

### 示例适配器

```bash
# 一个假设的 agent CLI；具体参数由你的工具决定
export AGENT_CMD='my-agent --prompt-file "$AGENT_PROMPT_FILE" --workdir "$AGENT_WORKTREE"'

# 如果评审需要不同的只读命令
export AGENT_REVIEW_CMD='my-agent --review --prompt-file "$AGENT_PROMPT_FILE"'

# 如果修复需要不同的命令
export AGENT_REPAIR_CMD='my-agent --repair --prompt-file "$AGENT_PROMPT_FILE"'
```

> `AGENT_REVIEW_CMD` / `AGENT_REPAIR_CMD` 未设置时回退到 `AGENT_CMD`。
> `AGENT_ATTRIBUTION` 可选，用于给 commit/PR 追加 trailer（例如 co-author 行）。

## 用法

```bash
# 从 GitHub issue 开始：实现 + CI + review，本地保留 worktree，不推送
make agent-flow ARGS="--issue 123"

# 确认无误后推送并开 PR
make agent-flow ARGS="--issue 123 --yes"

# 直接从一段任务描述开始
make agent-flow ARGS="--task '把 TCPEventBus 拆成 BrokerEventBus + TCPMessageStream' --title 'eventbus layering' --yes"

# 只打印计划
make agent-flow ARGS="--issue 123 --dry-run"

# 或者直接调用脚本
bash scripts/agent-flow.sh --issue 123
bash scripts/agent-flow.sh --task "..." --title "..." --yes
```

### 常用参数

| 参数 | 说明 |
|---|---|
| `--issue N` | 读取 GitHub issue 的标题/正文/标签 |
| `--task TEXT` | 直接传入任务正文 |
| `--title TEXT` | `--task` 模式的标题（默认取第一行） |
| `--base BRANCH` | 基线分支，默认 `main` |
| `--max-repair N` | CI/评审失败后的最大修复轮数，默认 2 |
| `--yes` | 推送分支并创建 PR（对外动作必须显式授权） |
| `--no-pr` | 只做本地实现/验证/提交，不推送 |
| `--dry-run` | 只打印计划 |
| `--keep-worktree` | 成功后保留 worktree |

### 环境变量

| 变量 | 说明 |
|---|---|
| `AGENT_CMD` | **必填**，实现阶段的 agent 命令 |
| `AGENT_REVIEW_CMD` | 可选，评审阶段命令（默认 `AGENT_CMD`） |
| `AGENT_REPAIR_CMD` | 可选，修复阶段命令（默认 `AGENT_CMD`） |
| `AGENT_ATTRIBUTION` | 可选，commit/PR trailer |
| `PYTHON` | prompt 渲染/CI 使用的解释器 |

## 流程细节

1. **隔离**：每次运行创建 `.agent-flow/worktrees/<run-id>`，分支为
   `agent/issue-<n>-<slug>-<timestamp>` 或 `agent/<slug>-<timestamp>`，基线是
   `origin/main`。
2. **实现**：`prompts/implement.md` 要求 agent 保持改动最小，并为行为变化补测试。
3. **CI 门禁**：在 worktree 中执行 `scripts/ci.sh`。测试失败会触发
   `prompts/repair.md`，最多 `--max-repair` 轮。
4. **独立评审**：CI 通过后，用新的 agent 调用执行 `prompts/review.md`。
   脚手架会把 staged diff 写到 `review-<n>.diff`，评审不需要自己跑 git。
   评审必须输出 `VERDICT: PASS` 或 `VERDICT: BLOCK`。
5. **评审阻断**：`BLOCK` 会进入修复轮；达到上限仍为 `BLOCK` 则中止，不会开 PR。
6. **提交/PR**：评审通过后提交，`--yes` 时推送并 `gh pr create`。PR 正文包含实现摘要、
   CI 日志尾部、评审结论和修复轮数。

## 产物与排障

所有运行产物在 `.agent-flow/runs/<run-id>/`（已 gitignore）：

```
implement.prompt.md / implement.log / implement-summary.md
ci-<n>.log
review-<n>.prompt.md / review-<n>.log / review-<n>.diff
repair-*.prompt.md / repair-*.log
pr-body.md
task.md
```

失败时 worktree 会保留，便于检查；成功且完成 PR 后默认删除。清理全部产物：

```bash
make clean-agent-flow
```

## 安全边界

- 默认不推送：没有 `--yes` 时只做本地实现、CI、评审和提交。
- 永远不在 `main` 上直接改：所有改动在独立 worktree/branch。
- PR 不会 force-push；分支名带时间戳，避免覆盖。
- issue 带 `no-agent` 或 `agent-flow-skip` 标签时拒绝运行。
- 评审是内容门禁，但最终合并仍需要人工确认。
- `AGENT_READ_ONLY=1` 只是约定；真正的只读隔离由你选择的 agent 命令负责。

## 和 CI 的关系

`scripts/ci.sh` 是唯一的验证入口：本地手跑、agent flow、未来的 GitHub Actions
都调用同一份脚本。agent flow 只是在它前后加了 agent 的实现和评审循环。
