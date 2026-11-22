#!/usr/bin/env bash
# tmux 双窗格可视化：SOME/IP Calculator RPC。
#
# 左 (55%)：Server 运行日志（REQUEST → RESPONSE）
# 右 (45%)：Client 调用结果 + 架构说明
#
# 用法：
#   ./tmux.sh                     # attach 进 tmux
#   Ctrl+b d                      # 分离（后台保留）
#   tmux kill-session -t tinysoa-calc  # 彻底关闭
#
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TINYSOA_DIR="$(cd "$SELF_DIR/../.." && pwd)"
export PYTHONPATH="$TINYSOA_DIR:$TINYSOA_DIR/src:$TINYSOA_DIR/third_party/pysomeip/src"
PY="python3"
[ -x "$TINYSOA_DIR/.venv/bin/python" ] && PY="$TINYSOA_DIR/.venv/bin/python"

SESSION="${SESSION:-tinysoa-calc}"

command -v tmux >/dev/null || { echo "需要先安装 tmux (apt install tmux)"; exit 1; }

# ── 释放可能占用的端口 ──────────────────────────────────────────────
fuser -k 30950/udp 2>/dev/null || true
sleep 0.6

# ── 关闭旧 tmux 会话 ────────────────────────────────────────────────
tmux kill-session -t "$SESSION" 2>/dev/null || true
sleep 0.3

# ── 左窗格：Server 运行 ─────────────────────────────────────────────
SRV_CMD="cd $TINYSOA_DIR && PYTHONPATH=$PYTHONPATH $PY -m examples.someip_method_call.server --log-level INFO"

LEFT=$(tmux new-session -d -s "$SESSION" -x 180 -y 36 -P -F '#{pane_id}' "$SRV_CMD")
tmux set-option -t "$SESSION:0" remain-on-exit on

# ── 右窗格：Client + 说明 ───────────────────────────────────────────
# 用单引号内联脚本可以少写转义，通过 export 传入路径
RIGHT=$(tmux split-window -h -p 45 -t "$LEFT" -P -F '#{pane_id}' \
  "export CLI_WD='$TINYSOA_DIR' \
          CLI_PP='$PYTHONPATH' \
          CLI_PY='$PY' \
          CLI_MODULE='examples.someip_method_call.client'; bash -c '
clear
cat <<\"INNER\"

  ==============================
    SOME/IP Calculator RPC
  ==============================

    service_id = 0x4444
    instance   = 0x0001

    Methods:
      add       (0x0001)
      sub       (0x0002)
      mul       (0x0003)

    Protocol:
      JSON over SOME/IP REQUEST/RESPONSE

  ------------------------------
    左: Server — SD Offer + 等待 REQUEST
    右: Client — SD Find → 3× RPC call
  ------------------------------

    Waiting for Server to announce ...

INNER

sleep 4
cd \"\$CLI_WD\" && PYTHONPATH=\"\$CLI_PP\" \"\$CLI_PY\" -m \"\$CLI_MODULE\" --log-level INFO
echo \"\"
echo \"  All done. Press Enter...\"
read -r _
'")

tmux select-pane -t "$LEFT"  -T "Server"
tmux select-pane -t "$RIGHT" -T "Client"

cat <<EOF
tmux 会话 '$SESSION' 已创建：

  左 (55%) = Server — SD Offer + REQUEST/RESPONSE
  右 (45%) = Client — 3 x RPC call (add/sub/mul)

  分离: Ctrl+b d    关闭: tmux kill-session -t $SESSION
EOF

if [ "${TMUX_DEMO_NOATTACH:-0}" = "1" ]; then
  echo "(TMUX_DEMO_NOATTACH=1，跳过 attach)"
else
  sleep 0.5
  exec tmux attach -t "$SESSION"
fi
