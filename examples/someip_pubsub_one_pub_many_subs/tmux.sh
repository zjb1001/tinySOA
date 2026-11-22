#!/usr/bin/env bash
# tmux 三窗格可视化：SOME/IP 一发多收。
#
#   ┌──────────────────────┬──────────────────────┐
#   │  Publisher           │  Subscriber sub-1    │
#   │  SD Offer + publish  ├──────────────────────┤
#   │                      │  Subscriber sub-2    │
#   └──────────────────────┴──────────────────────┘
#
# 用法： ./tmux.sh
#   分离(后台保留): Ctrl+b d
#   彻底关闭:       tmux kill-session -t tinysoa-someip-one-to-many
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/src:$REPO_ROOT/third_party/pysomeip/src"
PY="python3"
[ -x "$REPO_ROOT/.venv/bin/python" ] && PY="$REPO_ROOT/.venv/bin/python"
MODULE="examples.someip_pubsub_one_pub_many_subs"

SESSION="${SESSION:-tinysoa-someip-one-to-many}"
PUB_COUNT="${PUB_COUNT:-30}"
PUB_INTERVAL="${PUB_INTERVAL:-1.0}"
SUB_WANT="${SUB_WANT:-5}"
SUB_TIMEOUT="${SUB_TIMEOUT:-40}"
SUB1_PORT="${SUB1_PORT:-30930}"
SUB2_PORT="${SUB2_PORT:-30940}"

command -v tmux >/dev/null || { echo "需要先安装 tmux (apt install tmux)"; exit 1; }

PUB_CMD="cd $REPO_ROOT && PYTHONPATH=$PYTHONPATH $PY -m $MODULE.publisher --count $PUB_COUNT --interval $PUB_INTERVAL --log-level INFO"
SUB1_CMD="cd $REPO_ROOT && PYTHONPATH=$PYTHONPATH $PY -m $MODULE.subscriber sub-1 --want $SUB_WANT --timeout $SUB_TIMEOUT --local-port $SUB1_PORT --log-level INFO"
SUB2_CMD="cd $REPO_ROOT && PYTHONPATH=$PYTHONPATH $PY -m $MODULE.subscriber sub-2 --want $SUB_WANT --timeout $SUB_TIMEOUT --local-port $SUB2_PORT --log-level INFO"

tmux kill-session -t "$SESSION" 2>/dev/null || true

PUB=$(tmux new-session -d -s "$SESSION" -x 200 -y 48 -P -F '#{pane_id}' "$PUB_CMD")
tmux set-option -t "$SESSION:0" remain-on-exit on
SUB1=$(tmux split-window -h -p 50 -t "$PUB" -P -F '#{pane_id}' "$SUB1_CMD")
SUB2=$(tmux split-window -v -p 50 -t "$SUB1" -P -F '#{pane_id}' "$SUB2_CMD")

tmux select-pane -t "$PUB"  -T "Publisher (SD Offer)"
tmux select-pane -t "$SUB1" -T "Subscriber sub-1"
tmux select-pane -t "$SUB2" -T "Subscriber sub-2"

cat <<EOF
tmux 会话 '$SESSION' 已创建：
  左   = Publisher（SD Offer + 发布 $PUB_COUNT 条）
  右上 = Subscriber sub-1
  右下 = Subscriber sub-2

  分离(后台保留): Ctrl+b d    彻底关闭: tmux kill-session -t $SESSION
EOF

if [ "${TMUX_DEMO_NOATTACH:-0}" = "1" ]; then
    echo "(TMUX_DEMO_NOATTACH=1，跳过 attach)"
else
    sleep 0.5
    exec tmux attach -t "$SESSION"
fi
