#!/usr/bin/env bash
# tmux 四窗格可视化演示：SOME/IP 多传感器 + 聚合订阅者。
#
# 布局：
#   ┌───────────────────────────────────────────────────────┐
#   │         Aggregator Subscriber (统一仪表盘)              │
#   │         发现 3 个传感器 SD 服务，实时渲染仪表盘            │
#   ├──────────────────┬──────────────────┬─────────────────┤
#   │ Temperature      │   Humidity       │   Pressure      │
#   │ (Service 0x1001) │ (Service 0x1002) │ (Service 0x1003)│
#   │ 30500            │   30501           │   30502          │
#   └──────────────────┴──────────────────┴─────────────────┘
#
# 用法：
#   ./tmux_demo.sh                     # attach 进 tmux
#   分离(后台保留): Ctrl+b d           # 彻底关闭: tmux kill-session -t tinysoa-multisensor
#   环境变量: SESSION / LOG_LEVEL
#
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TINYSOA_DIR="$(cd "$SELF_DIR/../.." && pwd)"
# tinySOA is now a standalone repo (split from pysomeip).
# pysomeip is vendored under third_party/pysomeip/.
export PYTHONPATH="$TINYSOA_DIR/src:$TINYSOA_DIR/third_party/pysomeip/src"
PY="python3"
[ -x "$TINYSOA_DIR/.venv/bin/python" ] && PY="$TINYSOA_DIR/.venv/bin/python"

SESSION="${SESSION:-tinysoa-multisensor}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

command -v tmux >/dev/null || { echo "需要先安装 tmux (apt install tmux)"; exit 1; }

TEMP_CMD="cd $SELF_DIR && PYTHONPATH=$PYTHONPATH $PY publisher1_temperature.py --log-level $LOG_LEVEL"
HUMID_CMD="cd $SELF_DIR && PYTHONPATH=$PYTHONPATH $PY publisher2_humidity.py --log-level $LOG_LEVEL"
PRESS_CMD="cd $SELF_DIR && PYTHONPATH=$PYTHONPATH $PY publisher3_pressure.py --log-level $LOG_LEVEL"
AGG_CMD="cd $SELF_DIR && PYTHONPATH=$PYTHONPATH $PY subscriber_aggregator.py --log-level $LOG_LEVEL"

tmux kill-session -t "$SESSION" 2>/dev/null || true

# 1) 顶部全宽：Aggregator（最先显示仪表盘）
TOP=$(tmux new-session -d -s "$SESSION" -x 200 -y 52 -P -F '#{pane_id}' "$AGG_CMD")
tmux set-option -t "$SESSION:0" remain-on-exit on

# 2) 底部左：Temperature
BL=$(tmux split-window -v -p 50 -t "$TOP" -P -F '#{pane_id}' "$TEMP_CMD")

# 3) 底部中：Humidity（在 BL 右侧）
BM=$(tmux split-window -h -p 50 -t "$BL" -P -F '#{pane_id}' "$HUMID_CMD")

# 4) 底部右：Pressure（在 BL 右侧再分）
BR=$(tmux split-window -h -p 50 -t "$BM" -P -F '#{pane_id}' "$PRESS_CMD")

tmux select-pane -t "$TOP" -T "Aggregator Subscriber"
tmux select-pane -t "$BL"  -T "Temperature Publisher"
tmux select-pane -t "$BM"  -T "Humidity Publisher"
tmux select-pane -t "$BR"  -T "Pressure Publisher"

cat <<EOF
tmux 会话 '$SESSION' 已创建：
  上   = Aggregator Subscriber (SD 发现 + 仪表盘渲染)
  下左 = Temperature (Service 0x1001, port 30500)
  下中 = Humidity    (Service 0x1002, port 30501)
  下右 = Pressure    (Service 0x1003, port 30502)
  分离(后台保留): Ctrl+b d    彻底关闭: tmux kill-session -t $SESSION
EOF

if [ "${TMUX_DEMO_NOATTACH:-0}" = "1" ]; then
    echo "(TMUX_DEMO_NOATTACH=1，跳过 attach)"
else
    sleep 0.5
    exec tmux attach -t "$SESSION"
fi
