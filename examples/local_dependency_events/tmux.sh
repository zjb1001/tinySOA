#!/usr/bin/env bash
# tmux 双窗格可视化：本地依赖事件 / 控制面协调。
#
# 左 (60%)：app 运行日志（启动、事件、等待、关闭）
# 右 (40%)：场景说明 + 预期事件流
#
# 用法：
#   ./tmux.sh
#   Ctrl+b d                              # 分离
#   tmux kill-session -t tinysoa-dependency-events
#   环境变量: SESSION / DURATION / DISCOVERY_DELAY / WAIT_TIMEOUT
#
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TINYSOA_DIR="$(cd "$SELF_DIR/../.." && pwd)"
export PYTHONPATH="$TINYSOA_DIR:$TINYSOA_DIR/src:$TINYSOA_DIR/third_party/pysomeip/src"
PY="python3"
[ -x "$TINYSOA_DIR/.venv/bin/python" ] && PY="$TINYSOA_DIR/.venv/bin/python"

SESSION="${SESSION:-tinysoa-dependency-events}"
DURATION="${DURATION:-20}"
DISCOVERY_DELAY="${DISCOVERY_DELAY:-1.0}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-3.0}"

command -v tmux >/dev/null || { echo "需要先安装 tmux (apt install tmux)"; exit 1; }

# ── 左窗格：app 运行 ──────────────────────────────────────────────
APP_CMD="cd $TINYSOA_DIR && PYTHONPATH=$PYTHONPATH $PY -m examples.local_dependency_events.app \
  --duration $DURATION --discovery-delay $DISCOVERY_DELAY \
  --wait-timeout $WAIT_TIMEOUT --log-level INFO"

# ── 右窗格：场景说明 + 预期事件流 ─────────────────────────────────
RIGHT_CMD=$(cat <<'ASCIIDOC'
clear
while true; do
  tput cup 0 0 2>/dev/null || true

  cat <<'EOF'
[1;36m═══════════════════════════════════════════[0m
  [1mLocal Dependency Events[0m — 控制面案例
[1;36m═══════════════════════════════════════════[0m

  依赖图：

    DatabaseService (0x5000)
      ▲
      │ required
    SensorGatewayService (0x5100)
      ▲
      │ required
    DashboardService (0x5200)
      │ required (remote)
      └── RemoteTelemetryService (0x6000)
            通过 INSTANCE_DISCOVERED 模拟 SD

  可选依赖：
    AnalyticsService (0x5300) — 缺失不阻塞

[1;36m───────────────────────────────────────────[0m
  预期事件流：

    1. SERVICE_READY database
    2. SERVICE_READY sensor_gateway
       DEPENDENCY_SATISFIED sensor_gateway ← database
    3. dashboard 等待 remote_telemetry
    4. INSTANCE_DISCOVERED remote_telemetry
    5. SERVICE_READY dashboard
    6. SERVICE_STOPPED / DEPENDENCY_LOST
       INSTANCE_LOST remote_telemetry

[1;36m───────────────────────────────────────────[0m
  框架组件：

    Container · Service.dependencies
    LifecycleManager.astart_service / astop_all
    InternalEventDispatcher (typed, no ABC)
    DependencyCoordinator (subscribe → snapshot)

  [2mCtrl+b d 分离 · Ctrl+b q 查看编号 · x 关闭窗格[0m
EOF

  sleep 1
done
ASCIIDOC
)

tmux kill-session -t "$SESSION" 2>/dev/null || true

LEFT=$(tmux new-session -d -s "$SESSION" -x 200 -y 44 -P -F '#{pane_id}' "$APP_CMD")
tmux set-option -t "$SESSION:0" remain-on-exit on

RIGHT=$(tmux split-window -h -p 40 -t "$LEFT" -P -F '#{pane_id}' "bash -c '$RIGHT_CMD'")

tmux select-pane -t "$LEFT" -T "App"
tmux select-pane -t "$RIGHT" -T "Scenario"

cat <<EOF
tmux 会话 '$SESSION' 已创建：

  左 (60%) = 运行日志 (${DURATION}s)
  右 (40%) = 场景说明 + 预期事件流

  分离: Ctrl+b d    关闭: tmux kill-session -t $SESSION
EOF

if [ "${TMUX_DEMO_NOATTACH:-0}" = "1" ]; then
  echo "(TMUX_DEMO_NOATTACH=1，跳过 attach)"
else
  sleep 0.5
  exec tmux attach -t "$SESSION"
fi
