#!/bin/bash
# tinySOA examples — 统一启动菜单。
#
# 从这里选择要运行的示例组，或直接使用各组内的 Makefile / tmux_demo.sh。
# 各组 Makefile 支持: make start/stop/smoke/logs/tmux/clean
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo " tinySOA examples — 示例快速启动"
echo "============================================================"
echo ""
echo " 1) echo_service         单进程自包含 demo (InMemory + 策略链)"
echo " 2) interceptor_auth     单进程自包含 demo (自定义拦截器 + Auth)"
echo " 3) TCP pub/sub          4 窗格 tmux 可视化"
echo " 4) TCP pub/sub          端到端冒烟测试 (make smoke)"
echo " 5) SOME/IP 多传感器     4 窗格 tmux 可视化"
echo " 6) Cross-process SOME/IP 编排器一次测试"
echo " 7) Cross-process SOME/IP tmux 三窗格"
echo " 8) 多发布者/单订阅者    端到端冒烟"
echo " 9) 全部冒烟测试 (smoke-all)"
echo "10) 查看各组 Makefile 帮助"
echo ""
echo "  每个示例组均可独立管理:"
echo "    make -C pubsub_multi {start|stop|smoke|logs|tmux|clean}"
echo "    make -C someip_multi_publishers {start|stop|smoke|logs|tmux|clean}"
echo "    make -C cross_process_someip {run|start|stop|pytest|tmux|clean}"
echo "    make -C multi_publishers_single_sub {start|stop|smoke|logs|clean}"
echo ""

read -rp "请选择 (1-10): " choice

case $choice in
    1)
        echo ">> 启动 echo_service ..."
        make -C "$SCRIPT_DIR" echo
        ;;
    2)
        echo ">> 启动 interceptor_auth (自定义拦截器 + Auth) ..."
        make -C "$SCRIPT_DIR" interceptors
        ;;
    3)
        echo ">> tmux 可视化 TCP pub/sub ..."
        make -C "$SCRIPT_DIR" tmux-pubsub
        ;;
    4)
        echo ">> TCP pub/sub 冒烟 ..."
        make -C "$SCRIPT_DIR" smoke-pubsub
        ;;
    5)
        echo ">> tmux 可视化 SOME/IP 多传感器 ..."
        make -C "$SCRIPT_DIR" tmux-someip
        ;;
    6)
        echo ">> Cross-process SOME/IP 编排器 ..."
        make -C "$SCRIPT_DIR" run-xprocess
        ;;
    7)
        echo ">> tmux 可视化 cross-process SOME/IP ..."
        make -C "$SCRIPT_DIR" tmux-xprocess
        ;;
    8)
        echo ">> 多发布者/单订阅者 冒烟 ..."
        make -C "$SCRIPT_DIR" smoke-multipub
        ;;
    9)
        echo ">> 全部冒烟 ..."
        make -C "$SCRIPT_DIR" smoke-all
        ;;
    10)
        echo ""
        make -C "$SCRIPT_DIR" help
        echo ""
        echo "---"
        echo "各组独立 Makefile:"
        echo "  pubsub_multi/Makefile"
        echo "  someip_multi_publishers/Makefile"
        echo "  cross_process_someip/Makefile"
        echo "  multi_publishers_single_sub/Makefile"
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac
