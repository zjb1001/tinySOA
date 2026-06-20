#!/usr/bin/env bash
# tmux 四窗格可视化演示：TCP pub/sub 多进程示例。
#
# 田字格 2×2 布局：
#
#   ┌──────────────────────┬──────────────────────┐
#   │  Bus (TCP Server)    │  Subscriber 1        │
#   │  监听 :8765 + 扇出    │  sub-1 实时收事件      │
#   ├──────────────────────┼──────────────────────┤
#   │  Publisher           │  Subscriber 2        │
#   │  发布 N 条后退出一     │  sub-2 同 topic        │
#   └──────────────────────┴──────────────────────┘
#
# 用法：
#   ./tmux_demo.sh                     # attach 进 tmux
#   分离(后台保留): Ctrl+b d
#   彻底关闭:       tmux kill-session -t tinysoa-pubsub
#   环境变量: SESSION / HOST / PORT / PUB_COUNT / PUB_INTERVAL
#
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TINYSOA_DIR="$(cd "$SELF_DIR/../.." && pwd)"
# tinySOA is now a standalone repo (split from pysomeip).
# pysomeip is vendored under third_party/pysomeip/.
export PYTHONPATH="$TINYSOA_DIR/src:$TINYSOA_DIR/third_party/pysomeip/src"
PY="python3"
[ -x "$TINYSOA_DIR/.venv/bin/python" ] && PY="$TINYSOA_DIR/.venv/bin/python"

SESSION="${SESSION:-tinysoa-pubsub}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
PUB_COUNT="${PUB_COUNT:-50}"
PUB_INTERVAL="${PUB_INTERVAL:-0.5}"

command -v tmux >/dev/null || { echo "需要先安装 tmux (apt install tmux)"; exit 1; }

SRV_CMD="cd $TINYSOA_DIR && PYTHONPATH=$PYTHONPATH $PY $SELF_DIR/server.py --host $HOST --port $PORT --log-level INFO"
SUB1_CMD="cd $TINYSOA_DIR && PYTHONPATH=$PYTHONPATH $PY $SELF_DIR/subscriber.py sub-1 --host $HOST --port $PORT --log-level INFO"
SUB2_CMD="cd $TINYSOA_DIR && PYTHONPATH=$PYTHONPATH $PY $SELF_DIR/subscriber.py sub-2 --host $HOST --port $PORT --log-level INFO"
PUB_CMD="cd $TINYSOA_DIR && PYTHONPATH=$PYTHONPATH $PY $SELF_DIR/publisher.py --host $HOST --port $PORT --count $PUB_COUNT --interval $PUB_INTERVAL --log-level INFO"

tmux kill-session -t "$SESSION" 2>/dev/null || true

# ═══ 创建田字格 2×2 网格 ═══
#
# 正确的田字格切分顺序：先垂直切上下两行，再各自水平切左右两列。
#   ┌───────────┬───────────┐
#   │  Bus      │ Sub 1     │   上半行
#   ├───────────┼───────────┤
#   │ Publisher │ Sub 2     │   下半行
#   └───────────┴───────────┘
#
#   Step 1 — 全屏 → Bus (将成为左上)
#   Step 2 — 垂直分 Bus → Bus 上半 / Publisher 下半 (各 50% 高)
#   Step 3 — 水平分 Bus (上半) → 左上 Bus / 右上 Sub1
#   Step 4 — 水平分 Publisher (下半) → 左下 Publisher / 右下 Sub2

# 左上：Bus（先建，成为左上）
BUS=$(tmux new-session -d -s "$SESSION" -x 200 -y 48 -P -F '#{pane_id}' "$SRV_CMD")
tmux set-option -t "$SESSION:0" remain-on-exit on
# 左下：垂直切 Bus → 下半行跑 Publisher
PUB=$(tmux split-window -v -p 50 -t "$BUS" -P -F '#{pane_id}' "$PUB_CMD")
# 右上：水平切 Bus（上半行）→ Sub1 落到 Bus 右侧
SUB1=$(tmux split-window -h -p 50 -t "$BUS" -P -F '#{pane_id}' "$SUB1_CMD")
# 右下：水平切 Publisher（下半行）→ Sub2 落到 Publisher 右侧
SUB2=$(tmux split-window -h -p 50 -t "$PUB" -P -F '#{pane_id}' "$SUB2_CMD")

# 窗格标题
tmux select-pane -t "$BUS"  -T "Bus (TCP Server)"
tmux select-pane -t "$SUB1" -T "Subscriber 1"
tmux select-pane -t "$PUB"  -T "Publisher"
tmux select-pane -t "$SUB2" -T "Subscriber 2"

cat <<EOF
tmux 会话 '$SESSION' 已创建 (田字格 2×2)：

  左上 = Bus (TCP Server)   — 监听 + 扇出
  左下 = Publisher          — 发布 $PUB_COUNT 条后退出
  右上 = Subscriber 1       — 实时收事件
  右下 = Subscriber 2       — 同 topic 多消费者

  分离(后台保留): Ctrl+b d    彻底关闭: tmux kill-session -t $SESSION
EOF

if [ "${TMUX_DEMO_NOATTACH:-0}" = "1" ]; then
    echo "(TMUX_DEMO_NOATTACH=1，跳过 attach)"
else
    sleep 0.5
    exec tmux attach -t "$SESSION"
fi
