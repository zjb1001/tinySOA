#!/usr/bin/env bash
# tmux 双窗格可视化：SOME/IP 一对一 pub/sub。
#
#   ┌──────────────────────┬──────────────────────┐
#   │  Publisher           │  Subscriber          │
#   │  SD Offer + publish  │  SD FindSubscribe    │
#   └──────────────────────┴──────────────────────┘
#
# 用法： ./tmux.sh
#   分离(后台保留): Ctrl+b d
#   彻底关闭:       tmux kill-session -t tinysoa-someip-one-to-one
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/src:$REPO_ROOT/third_party/pysomeip/src"
PY="python3"
[ -x "$REPO_ROOT/.venv/bin/python" ] && PY="$REPO_ROOT/.venv/bin/python"
MODULE="examples.someip_pubsub_one_to_one"

SESSION="${SESSION:-tinysoa-someip-one-to-one}"
PUB_COUNT="${PUB_COUNT:-30}"
PUB_INTERVAL="${PUB_INTERVAL:-1.0}"
SUB_WANT="${SUB_WANT:-5}"
SUB_TIMEOUT="${SUB_TIMEOUT:-40}"
SUB_PORT="${SUB_PORT:-30980}"

command -v tmux >/dev/null || { echo "需要先安装 tmux (apt install tmux)"; exit 1; }

PUB_CMD="cd $REPO_ROOT && PYTHONPATH=$PYTHONPATH $PY -m $MODULE.publisher --count $PUB_COUNT --interval $PUB_INTERVAL --log-level INFO"
SUB_CMD="cd $REPO_ROOT && PYTHONPATH=$PYTHONPATH $PY -m $MODULE.subscriber --want $SUB_WANT --timeout $SUB_TIMEOUT --local-port $SUB_PORT --log-level INFO"

tmux kill-session -t "$SESSION" 2>/dev/null || true

PUB=$(tmux new-session -d -s "$SESSION" -x 200 -y 48 -P -F '#{pane_id}' "$PUB_CMD")
tmux set-option -t "$SESSION:0" remain-on-exit on
SUB=$(tmux split-window -h -p 50 -t "$PUB" -P -F '#{pane_id}' "$SUB_CMD")

tmux select-pane -t "$PUB" -T "Publisher (SD Offer)"
tmux select-pane -t "$SUB" -T "Subscriber"

cat <<EOF
tmux 会话 '$SESSION' 已创建：
  左 = Publisher（SD Offer + 发布 $PUB_COUNT 条）
  右 = Subscriber

  分离(后台保留): Ctrl+b d    彻底关闭: tmux kill-session -t $SESSION
EOF

if [ "${TMUX_DEMO_NOATTACH:-0}" = "1" ]; then
    echo "(TMUX_DEMO_NOATTACH=1，跳过 attach)"
else
    sleep 0.5
    exec tmux attach -t "$SESSION"
fi
