#!/usr/bin/env bash
# tmux 四窗格可视化：TCP broker 多发布者 → 单订阅者。
#
#   ┌──────────────────────┬──────────────────────┐
#   │  Broker (:8766)      │  Subscriber          │
#   ├──────────────────────┼──────────────────────┤
#   │  Publisher pub-A     │  Publisher pub-B     │
#   └──────────────────────┴──────────────────────┘
#
# 用法： ./tmux.sh
#   分离(后台保留): Ctrl+b d
#   彻底关闭:       tmux kill-session -t tinysoa-tcp-many
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/src:$REPO_ROOT/third_party/pysomeip/src"
PY="python3"
[ -x "$REPO_ROOT/.venv/bin/python" ] && PY="$REPO_ROOT/.venv/bin/python"

SESSION="${SESSION:-tinysoa-tcp-many}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8766}"
PUB_COUNT="${PUB_COUNT:-50}"
PUB_INTERVAL="${PUB_INTERVAL:-0.5}"
SHARED="examples.tcp_pubsub_one_to_many"
MODULE="examples.tcp_pubsub_many_to_one"

command -v tmux >/dev/null || { echo "需要先安装 tmux (apt install tmux)"; exit 1; }

SRV_CMD="cd $REPO_ROOT && PYTHONPATH=$PYTHONPATH $PY -m $SHARED.server --host $HOST --port $PORT --log-level INFO"
SUB_CMD="cd $REPO_ROOT && PYTHONPATH=$PYTHONPATH $PY -m $SHARED.subscriber sub-collector --host $HOST --port $PORT --log-level INFO"
PUB_A_CMD="cd $REPO_ROOT && PYTHONPATH=$PYTHONPATH $PY -m $MODULE.publisher_with_id pub-A --host $HOST --port $PORT --count $PUB_COUNT --interval $PUB_INTERVAL --log-level INFO"
PUB_B_CMD="cd $REPO_ROOT && PYTHONPATH=$PYTHONPATH $PY -m $MODULE.publisher_with_id pub-B --host $HOST --port $PORT --count $PUB_COUNT --interval $PUB_INTERVAL --log-level INFO"

tmux kill-session -t "$SESSION" 2>/dev/null || true

BUS=$(tmux new-session -d -s "$SESSION" -x 200 -y 48 -P -F '#{pane_id}' "$SRV_CMD")
tmux set-option -t "$SESSION:0" remain-on-exit on
SUB=$(tmux split-window -v -p 50 -t "$BUS" -P -F '#{pane_id}' "$SUB_CMD")
PUB_A=$(tmux split-window -h -p 50 -t "$BUS" -P -F '#{pane_id}' "$PUB_A_CMD")
PUB_B=$(tmux split-window -h -p 50 -t "$SUB" -P -F '#{pane_id}' "$PUB_B_CMD")

tmux select-pane -t "$BUS"   -T "Broker (TCP :$PORT)"
tmux select-pane -t "$SUB"   -T "Subscriber (aggregator)"
tmux select-pane -t "$PUB_A" -T "Publisher pub-A"
tmux select-pane -t "$PUB_B" -T "Publisher pub-B"

cat <<EOF
tmux 会话 '$SESSION' 已创建 (2×2)：
  左上 = Broker (:${PORT})
  左下 = Subscriber
  右上 = Publisher pub-A
  右下 = Publisher pub-B

  分离(后台保留): Ctrl+b d    彻底关闭: tmux kill-session -t $SESSION
EOF

if [ "${TMUX_DEMO_NOATTACH:-0}" = "1" ]; then
    echo "(TMUX_DEMO_NOATTACH=1，跳过 attach)"
else
    sleep 0.5
    exec tmux attach -t "$SESSION"
fi
