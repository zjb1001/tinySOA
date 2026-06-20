#!/usr/bin/env bash
# tmux 三窗格可视化演示：SOME/IP 跨进程 pub/sub。
#
# 布局：
#   ┌──────────────────────────────────────────────┐
#   │  上：SOME/IP SD 监控（eventbus 发现/订阅握手）  │  ← 先起，全宽
#   ├────────────────────────┬─────────────────────┤
#   │  发布者 Publisher        │  订阅者 Subscriber   │  ← 下排左右
#   └────────────────────────┴─────────────────────┘
#
# 说明：tinySOA 里 EventBus 不是独立进程（内嵌在 pub/sub 内），所以
# 上方用 pysomeip 的 SD 监控来呈现"eventbus 的发现动作"——即 pub 的 Offer、
# sub 的 Find/Subscribe/Ack 握手流量，正好把下排两个进程桥接起来。
#
# 用法： ./tmux_demo.sh            （attach 进 tmux）
#   环境变量可调：SESSION / PUB_COUNT / PUB_INTERVAL / SUB_WANT / SUB_TIMEOUT
#   分离(后台保留): Ctrl+b d     彻底关闭: tmux kill-session -t $SESSION
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TINYSOA_DIR="$(cd "$SELF_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/../../.." && pwd)"
export PYTHONPATH="$REPO_ROOT/src:$TINYSOA_DIR/src"
PY="python3"
[ -x "$REPO_ROOT/.venv/bin/python" ] && PY="$REPO_ROOT/.venv/bin/python"

SESSION="${SESSION:-tinysoa-someip}"
PUB_COUNT="${PUB_COUNT:-30}"
PUB_INTERVAL="${PUB_INTERVAL:-1.0}"
SUB_WANT="${SUB_WANT:-5}"
SUB_TIMEOUT="${SUB_TIMEOUT:-40}"

command -v tmux >/dev/null || { echo "需要先安装 tmux（apt install tmux）"; exit 1; }

# 各窗格命令
TOP_CMD="$PY $REPO_ROOT/tools/monitor-sd.py 127.0.0.1 224.224.224.245 30490"
PUB_CMD="cd $TINYSOA_DIR && PYTHONPATH=$PYTHONPATH $PY -m examples.cross_process_someip.publisher $PUB_COUNT $PUB_INTERVAL"
SUB_CMD="cd $TINYSOA_DIR && PYTHONPATH=$PYTHONPATH $PY -m examples.cross_process_someip.subscriber $SUB_WANT $SUB_TIMEOUT"

tmux kill-session -t "$SESSION" 2>/dev/null || true

# 1) 顶部全宽：SD 监控（最先起，观察 eventbus 发现动作）
TOP=$(tmux new-session -d -s "$SESSION" -x 220 -y 56 -P -F '#{pane_id}' "$TOP_CMD")
# 让进程结束后仍保留输出，便于看最终的 SUCCESS/STOP
tmux set-option -t "$SESSION:0" remain-on-exit on

# 2) 下方左右两列：发布者 / 订阅者（-v -p 68 → 顶部约 32%）
BL=$(tmux split-window -v -p 68 -t "$TOP" -P -F '#{pane_id}' "$PUB_CMD")
BR=$(tmux split-window -h -p 50 -t "$BL" -P -F '#{pane_id}' "$SUB_CMD")

tmux select-pane -t "$TOP" -T "SD Monitor (eventbus)"
tmux select-pane -t "$BL"  -T "Publisher"
tmux select-pane -t "$BR"  -T "Subscriber"

cat <<EOF
tmux 会话 '$SESSION' 已创建：
  上   = SOME/IP SD 监控（eventbus 发现/订阅握手，最先起）
  下左 = Publisher 进程
  下右 = Subscriber 进程
  分离(后台保留): Ctrl+b d    彻底关闭: tmux kill-session -t $SESSION
EOF

if [ "${TMUX_DEMO_NOATTACH:-0}" = "1" ]; then
    echo "(TMUX_DEMO_NOATTACH=1，跳过 attach)"
else
    sleep 1
    exec tmux attach -t "$SESSION"
fi
