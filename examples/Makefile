# Makefile —— tinySOA examples 统一入口。
#
# 每个示例组有自己的 Makefile (含 start/stop/smoke/tmux/clean)；
# 本文件提供顶层聚合命令 (help / clean-all) 与 echo_service 快捷入口。
#
# 常用：
#   make                        = make help
#   make echo                   = 跑 echo_service 自包含 demo
#   make smoke-all              = 顺序跑所有冒烟测试
#   make start-all              = 后台启动所有示例组
#   make stop-all               = 停止所有示例组后台进程
#   make clean-all              = 清理所有产物
#   make tmux-pubsub            = tmux 可视化 TCP pub/sub
#   make tmux-someip            = tmux 可视化 SOME/IP 多传感器
#   make tmux-xprocess          = tmux 可视化 cross-process SOME/IP

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)..)
PYTHONPATH  := $(TINYSOA_DIR)/src:$(TINYSOA_DIR)/third_party/pysomeip/src
PYTHON      ?= python3

LOG_LEVEL ?= INFO

# 各子 Makefile 目录
PUBSUB   := $(SELF_DIR)pubsub_multi/
SOMEIP   := $(SELF_DIR)someip_multi_publishers/
MULTIPUB := $(SELF_DIR)multi_publishers_single_sub/
XPROCESS := $(SELF_DIR)cross_process_someip/

# =========================================================================
# Help
# =========================================================================
.PHONY: help
help: ## 显示帮助
	@echo "tinySOA examples — 顶层 Makefile"
	@echo ""
	@echo "=== 单进程 Demo ==="
	@echo "  make echo                      跑 echo_service 自包含 demo"
	@echo "  make interceptors              跑 interceptor_auth 自包含 demo (拦截器+Auth)"
	@echo ""
	@echo "=== TCPEventBus 发布/订阅 ($(PUBSUB)) ==="
	@echo "  make tmux-pubsub               tmux 四窗格 (server|sub1 / pub|sub2)"
	@echo "  make smoke-pubsub              端到端冒烟 (TCPEventBus)"
	@echo ""
	@echo "=== SOME/IP 多传感器 ($(SOMEIP)) ==="
	@echo "  make tmux-someip               tmux 四窗格 (agg / temp|humid|pressure)"
	@echo "  make smoke-someip              bounded 冒烟"
	@echo ""
	@echo "=== 多发布者 / 单订阅者 ($(MULTIPUB)) ==="
	@echo "  make smoke-multipub            端到端冒烟 (pub-A + pub-B)"
	@echo ""
	@echo "=== Cross-process SOME/IP ($(XPROCESS)) ==="
	@echo "  make run-xprocess              编排器前台一次测试"
	@echo "  make start-xprocess            后台常驻"
	@echo "  make tmux-xprocess             tmux 三窗格 (SD 监控 | pub | sub)"
	@echo ""
	@echo "=== 全局 ==="
	@echo "  make start-all                 后台启动所有示例组"
	@echo "  make stop-all                  停止所有示例组后台进程"
	@echo "  make status-all                查看所有示例组状态"
	@echo "  make clean-all                 停止所有进程并清理全部产物"
	@echo ""
	@echo "  PYTHON:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

# =========================================================================
# echo_service (单进程、自包含、无后台管理)
# =========================================================================
.PHONY: echo
echo: ## 跑 echo_service demo (确定性的自包含示例)
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) $(SELF_DIR)echo_service/app.py
	@echo ">> echo_service 完成"

# =========================================================================
# interceptor_auth (单进程、自包含、自定义拦截器 + Auth)
# =========================================================================
.PHONY: interceptors
interceptors: ## 跑 interceptor_auth demo (自定义拦截器 + Auth, 自包含)
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) $(SELF_DIR)interceptor_auth/app.py
	@echo ">> interceptor_auth 完成"

# =========================================================================
# 子组委托
# =========================================================================

# --- TCP pub/sub ---
tmux-pubsub: ## tmux 可视化 TCP pub/sub
	@$(MAKE) -C $(PUBSUB) tmux

smoke-pubsub: ## TCP pub/sub 端到端冒烟
	@$(MAKE) -C $(PUBSUB) smoke

start-pubsub: ## 后台启动 pubsub_multi
	@$(MAKE) -C $(PUBSUB) start

stop-pubsub: ## 停止 pubsub_multi 后台
	@$(MAKE) -C $(PUBSUB) stop

logs-pubsub: ## tail pubsub_multi 日志
	@$(MAKE) -C $(PUBSUB) logs

# --- SOME/IP 多传感器 ---
tmux-someip: ## tmux 可视化 SOME/IP 多传感器
	@$(MAKE) -C $(SOMEIP) tmux

smoke-someip: ## SOME/IP 多传感器 bounded 冒烟
	@$(MAKE) -C $(SOMEIP) smoke

start-someip: ## 后台启动 SOME/IP 多传感器
	@$(MAKE) -C $(SOMEIP) start

stop-someip: ## 停止 SOME/IP 多传感器后台
	@$(MAKE) -C $(SOMEIP) stop

logs-someip: ## tail SOME/IP 多传感器日志
	@$(MAKE) -C $(SOMEIP) logs

# --- 多发布者 / 单订阅者 ---
smoke-multipub: ## 多发布者 / 单订阅者冒烟
	@$(MAKE) -C $(MULTIPUB) smoke

start-multipub: ## 后台启动多发布者 / 单订阅者
	@$(MAKE) -C $(MULTIPUB) start

stop-multipub: ## 停止多发布者 / 单订阅者后台
	@$(MAKE) -C $(MULTIPUB) stop

logs-multipub: ## tail 多发布者日志
	@$(MAKE) -C $(MULTIPUB) logs

# --- Cross-process SOME/IP ---
run-xprocess: ## 编排器前台一次测试
	@$(MAKE) -C $(XPROCESS) run

tmux-xprocess: ## tmux 可视化 cross-process SOME/IP
	@$(MAKE) -C $(XPROCESS) tmux

start-xprocess: ## 后台启动 cross_process_someip
	@$(MAKE) -C $(XPROCESS) start

stop-xprocess: ## 停止 cross_process_someip 后台
	@$(MAKE) -C $(XPROCESS) stop

logs-xprocess: ## tail cross_process_someip 日志
	@$(MAKE) -C $(XPROCESS) logs

# =========================================================================
# 全局命令
# =========================================================================

.PHONY: start-all stop-all status-all smoke-all clean-all

start-all: start-pubsub start-someip start-multipub ## 后台启动所有示例组
	@echo ">> 所有示例组已后台启动"

stop-all: ## 停止全部示例组
	@$(MAKE) -C $(PUBSUB) stop 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP) stop 2>/dev/null || true
	@$(MAKE) -C $(MULTIPUB) stop 2>/dev/null || true
	@$(MAKE) -C $(XPROCESS) stop 2>/dev/null || true
	@echo ">> 所有示例组已停止"

status-all: ## 查看所有示例组状态
	@echo "=== pubsub_multi ==="; $(MAKE) --no-print-directory -C $(PUBSUB) status
	@echo "=== someip_multi ==="; $(MAKE) --no-print-directory -C $(SOMEIP) status
	@echo "=== multi_pub_sub ==="; $(MAKE) --no-print-directory -C $(MULTIPUB) status
	@echo "=== cross_process  ==="; $(MAKE) --no-print-directory -C $(XPROCESS) status

smoke-all: smoke-pubsub smoke-someip smoke-multipub ## 顺序跑所有冒烟测试
	@echo ">> 所有冒烟测试完成"

clean-all: stop-all ## 停止全部进程并清理产物
	@$(MAKE) -C $(PUBSUB) clean 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP) clean 2>/dev/null || true
	@$(MAKE) -C $(MULTIPUB) clean 2>/dev/null || true
	@$(MAKE) -C $(XPROCESS) clean 2>/dev/null || true
	@rm -f $(SELF_DIR)*.pid $(SELF_DIR)*.log
	@echo ">> 全局清理完成"
