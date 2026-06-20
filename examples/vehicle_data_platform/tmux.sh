#!/usr/bin/env bash
# tmux 双窗格可视化：车辆数据平台。
#
# 左 (60%)：app.py 运行日志
# 右 (40%)：架构概览 + 实时服务状态（每秒刷新）
#
# 用法：
#   ./tmux.sh                     # attach 进 tmux
#   Ctrl+b d                      # 分离（后台保留）
#   tmux kill-session -t tinysoa-vdp  # 彻底关闭
#   环境变量: SESSION / DURATION / HEALTH_INTERVAL
#
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TINYSOA_DIR="$(cd "$SELF_DIR/../.." && pwd)"
export PYTHONPATH="$TINYSOA_DIR/src"
PY="python3"
[ -x "$TINYSOA_DIR/.venv/bin/python" ] && PY="$TINYSOA_DIR/.venv/bin/python"

SESSION="${SESSION:-tinysoa-vdp}"
DURATION="${DURATION:-20}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-3.0}"

command -v tmux >/dev/null || { echo "需要先安装 tmux (apt install tmux)"; exit 1; }

# ── 左窗格：app 运行 ──────────────────────────────────────────────
APP_CMD="cd $TINYSOA_DIR && PYTHONPATH=$PYTHONPATH $PY $SELF_DIR/app.py \
  --duration $DURATION --health-interval $HEALTH_INTERVAL --log-level INFO"

# ── 右窗格：架构说明 + 实时状态（循环刷新） ─────────────────────────
# 用 ANSI 颜色做轻量高亮，避免 ASCII box 浪费横向空间
RIGHT_CMD=$(cat <<'ASCIIDOC'
clear
while true; do
  # 移到屏幕顶部
  tput cup 0 0 2>/dev/null || true

  cat <<'EOF'
[1;36m═══════════════════════════════════════[0m
  [1mVehicle Data Platform[0m — SOA 工程案例
[1;36m═══════════════════════════════════════[0m

  4 个车载服务，依赖感知启停：

  [1;33mEngineService[0m (0x1000)
    methods: get_rpm, get_temperature
    events:  rpm_changed, temperature_changed

  [1;33mTransmissionService[0m (0x2000)  ── 依赖 Engine
    methods: get_gear
    events:  gear_changed

  [1;33mDashboardService[0m (0x3000)  ── 依赖 Engine + Trans
    methods: get_display
    events:  display_updated

  [1;33mDiagnosticsService[0m (0x4000)  ── 独立运行
    methods: run_diagnostics, get_report

[1;36m───────────────────────────────────────[0m
  启动: Engine → Transmission → Dashboard
        (+ Diagnostics 并行)
  停止: Dashboard → Transmission → Engine
        (+ Diagnostics 并行)
[1;36m───────────────────────────────────────[0m
  框架组件：
    Container · LifecycleManager
    VehicleHealthChecker (自定义)
    InMemoryEventBus (服务间 pub/sub)
    argparse · 结构化日志 · 信号优雅关闭
[1;36m───────────────────────────────────────[0m

  [2mCtrl+b d  分离（后台运行）[0m
  [2mCtrl+b q  显示窗格编号，按 x 关闭[0m
EOF

  sleep 1
done
ASCIIDOC
)

tmux kill-session -t "$SESSION" 2>/dev/null || true

# 左 60%：app 运行
LEFT=$(tmux new-session -d -s "$SESSION" -x 200 -y 42 -P -F '#{pane_id}' "$APP_CMD")
tmux set-option -t "$SESSION:0" remain-on-exit on

# 右 40%：架构说明
RIGHT=$(tmux split-window -h -p 40 -t "$LEFT" -P -F '#{pane_id}' "bash -c '$RIGHT_CMD'")

tmux select-pane -t "$LEFT"  -T "App"
tmux select-pane -t "$RIGHT" -T "Architecture"

cat <<EOF
tmux 会话 '$SESSION' 已创建：

  左 (60%) = 平台运行日志 (${DURATION}s)
  右 (40%) = 架构说明

  分离: Ctrl+b d    关闭: tmux kill-session -t $SESSION
EOF

if [ "${TMUX_DEMO_NOATTACH:-0}" = "1" ]; then
  echo "(TMUX_DEMO_NOATTACH=1，跳过 attach)"
else
  sleep 0.5
  exec tmux attach -t "$SESSION"
fi
