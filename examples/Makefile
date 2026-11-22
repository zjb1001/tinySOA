# Makefile —— tinySOA examples 统一入口。
#
# 所有案例都以包模块运行：python -m examples.<name>.<module>
# 每个子目录仍有自己的 Makefile（help/run/start/stop/smoke/tmux/clean）。
#
# 命名约定：
#   local_*   进程内（InMemoryEventBus）
#   tcp_*     TCP broker 拓扑
#   someip_*  SOME/IP peer 拓扑
#
# 常用：
#   make                        = make help
#   make echo                   = 本地 echo 服务
#   make interceptors           = 拦截器 + Auth
#   make vdp                    = 车辆数据平台
#   make topologies             = 1v1 / 1vN / Nv1 本地矩阵
#   make tmux-pubsub            = TCP broker 一发多收
#   make tmux-someip-one-to-many= SOME/IP 一发多收
#   make tmux-someip            = SOME/IP 多传感器
#   make smoke-calc             = SOME/IP Calculator RPC
#   make smoke-all              = 顺序跑稳定冒烟组
#   make clean-all              = 停止后台进程并清理产物

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
REPO_ROOT := $(abspath $(SELF_DIR)..)
PYTHONPATH := $(REPO_ROOT):$(REPO_ROOT)/src:$(REPO_ROOT)/third_party/pysomeip/src
PYTHON ?= $(shell [ -x "$(REPO_ROOT)/.venv/bin/python" ] && echo "$(REPO_ROOT)/.venv/bin/python" || echo python3)
LOG_LEVEL ?= INFO

LOCAL_ECHO := $(SELF_DIR)local_echo_service/
LOCAL_INTERCEPTORS := $(SELF_DIR)local_interceptor_auth/
LOCAL_VDP := $(SELF_DIR)local_vehicle_platform/
LOCAL_TOPOLOGIES := $(SELF_DIR)local_pubsub_topologies/
TCP_ONE := $(SELF_DIR)tcp_pubsub_one_to_many/
SOMEIP_ONE_ONE := $(SELF_DIR)someip_pubsub_one_to_one/
SOMEIP_ONE_MANY := $(SELF_DIR)someip_pubsub_one_to_many/
SOMEIP_MULTI := $(SELF_DIR)someip_pubsub_multi_sensor/
SOMEIP_CALL := $(SELF_DIR)someip_method_call/

# =========================================================================
# Help
# =========================================================================
.PHONY: help
help: ## 显示帮助
	@echo "tinySOA examples — 顶层 Makefile"
	@echo ""
	@echo "=== 本地单进程（InMemoryEventBus） ==="
	@echo "  make echo                       本地 echo 服务"
	@echo "  make interceptors               拦截器 + Auth"
	@echo "  make vdp                        车辆数据平台"
	@echo "  make topologies                 1v1 / 1vN / Nv1 本地拓扑矩阵"
	@echo ""
	@echo "=== TCP broker（BROKER 拓扑） ==="
	@echo "  make tmux-pubsub                tmux：一发多收"
	@echo "  make smoke-pubsub               冒烟：一发多收"
	@echo ""
	@echo "=== SOME/IP（PEER 拓扑） ==="
	@echo "  make tmux-someip-one-to-one     tmux：一对一"
	@echo "  make smoke-someip-one-to-one    冒烟：一对一"
	@echo "  make tmux-someip-one-to-many    tmux：一发多收"
	@echo "  make smoke-someip-one-to-many   冒烟：一发多收"
	@echo "  make tmux-someip                tmux：多传感器"
	@echo "  make smoke-someip               冒烟：多传感器"
	@echo ""
	@echo "=== SOME/IP RPC ==="
	@echo "  make smoke-calc                 冒烟：Calculator RPC"
	@echo "  make tmux-calc                  tmux：Calculator RPC"
	@echo ""
	@echo "=== 全局 ==="
	@echo "  make start-all                   后台启动所有常驻示例组"
	@echo "  make stop-all                    停止全部示例组"
	@echo "  make status-all                  查看全部示例组状态"
	@echo "  make smoke-all                   顺序跑稳定冒烟组"
	@echo "  make clean-all                   停止进程并清理产物"
	@echo ""
	@echo "  PYTHON:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

# =========================================================================
# 本地单进程
# =========================================================================
.PHONY: echo interceptors vdp topologies smoke-vdp tmux-vdp
echo: ## 本地 echo 服务
	@cd $(REPO_ROOT) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) -m examples.local_echo_service.app

interceptors: ## 拦截器 + Auth
	@cd $(REPO_ROOT) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) -m examples.local_interceptor_auth.app

vdp: ## 车辆数据平台
	@cd $(REPO_ROOT) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) -m examples.local_vehicle_platform.app \
	  --duration 15 --health-interval 3.0 --log-level $(LOG_LEVEL)

topologies: ## 1v1 / 1vN / Nv1 本地拓扑矩阵
	@$(MAKE) -C $(LOCAL_TOPOLOGIES) run

smoke-vdp: ## 车辆数据平台冒烟
	@$(MAKE) -C $(LOCAL_VDP) smoke

tmux-vdp: ## tmux 可视化车辆数据平台
	@$(MAKE) -C $(LOCAL_VDP) tmux

# =========================================================================
# SOME/IP RPC
# =========================================================================
.PHONY: smoke-calc tmux-calc
smoke-calc: ## SOME/IP Calculator RPC 冒烟
	@$(MAKE) -C $(SOMEIP_CALL) smoke

tmux-calc: ## tmux 可视化 Calculator RPC
	@$(MAKE) -C $(SOMEIP_CALL) tmux

# =========================================================================
# TCP broker
# =========================================================================
.PHONY: tmux-pubsub smoke-pubsub start-pubsub stop-pubsub logs-pubsub
tmux-pubsub:
	@$(MAKE) -C $(TCP_ONE) tmux
smoke-pubsub:
	@$(MAKE) -C $(TCP_ONE) smoke
start-pubsub:
	@$(MAKE) -C $(TCP_ONE) start
stop-pubsub:
	@$(MAKE) -C $(TCP_ONE) stop
logs-pubsub:
	@$(MAKE) -C $(TCP_ONE) logs

# =========================================================================
# SOME/IP pub/sub
# =========================================================================
.PHONY: tmux-someip-one-to-one smoke-someip-one-to-one \
        start-someip-one-to-one stop-someip-one-to-one logs-someip-one-to-one \
        tmux-someip-one-to-many smoke-someip-one-to-many \
        start-someip-one-to-many stop-someip-one-to-many logs-someip-one-to-many \
        tmux-someip smoke-someip start-someip stop-someip logs-someip
tmux-someip-one-to-one:
	@$(MAKE) -C $(SOMEIP_ONE_ONE) tmux
smoke-someip-one-to-one:
	@$(MAKE) -C $(SOMEIP_ONE_ONE) smoke
start-someip-one-to-one:
	@$(MAKE) -C $(SOMEIP_ONE_ONE) start
stop-someip-one-to-one:
	@$(MAKE) -C $(SOMEIP_ONE_ONE) stop
logs-someip-one-to-one:
	@$(MAKE) -C $(SOMEIP_ONE_ONE) logs

tmux-someip-one-to-many:
	@$(MAKE) -C $(SOMEIP_ONE_MANY) tmux
smoke-someip-one-to-many:
	@$(MAKE) -C $(SOMEIP_ONE_MANY) smoke
start-someip-one-to-many:
	@$(MAKE) -C $(SOMEIP_ONE_MANY) start
stop-someip-one-to-many:
	@$(MAKE) -C $(SOMEIP_ONE_MANY) stop
logs-someip-one-to-many:
	@$(MAKE) -C $(SOMEIP_ONE_MANY) logs

tmux-someip:
	@$(MAKE) -C $(SOMEIP_MULTI) tmux
smoke-someip:
	@$(MAKE) -C $(SOMEIP_MULTI) smoke
start-someip:
	@$(MAKE) -C $(SOMEIP_MULTI) start
stop-someip:
	@$(MAKE) -C $(SOMEIP_MULTI) stop
logs-someip:
	@$(MAKE) -C $(SOMEIP_MULTI) logs

# =========================================================================
# 全局
# =========================================================================
.PHONY: start-all stop-all status-all smoke-all clean-all
start-all: start-someip-one-to-one start-someip-one-to-many start-pubsub start-someip ## 后台启动所有常驻组
	@echo ">> 所有常驻示例组已后台启动"

stop-all: ## 停止全部示例组
	@$(MAKE) -C $(SOMEIP_ONE_ONE) stop 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_ONE_MANY) stop 2>/dev/null || true
	@$(MAKE) -C $(TCP_ONE) stop 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_MULTI) stop 2>/dev/null || true
	@echo ">> 所有示例组已停止"

status-all: ## 查看全部示例组状态
	@echo "=== tcp_pubsub_one_to_many ==="; $(MAKE) --no-print-directory -C $(TCP_ONE) status
	@echo "=== someip_pubsub_one_to_one ==="; $(MAKE) --no-print-directory -C $(SOMEIP_ONE_ONE) status
	@echo "=== someip_pubsub_one_to_many ==="; $(MAKE) --no-print-directory -C $(SOMEIP_ONE_MANY) status
	@echo "=== someip_pubsub_multi_sensor ==="; $(MAKE) --no-print-directory -C $(SOMEIP_MULTI) status

smoke-all: echo interceptors topologies smoke-pubsub smoke-someip-one-to-one smoke-someip-one-to-many smoke-someip smoke-vdp smoke-calc ## 顺序跑稳定冒烟组
	@echo ">> 所有冒烟测试完成"

clean-all: stop-all ## 停止全部进程并清理产物
	@$(MAKE) -C $(LOCAL_ECHO) clean 2>/dev/null || true
	@$(MAKE) -C $(LOCAL_INTERCEPTORS) clean 2>/dev/null || true
	@$(MAKE) -C $(LOCAL_VDP) clean 2>/dev/null || true
	@$(MAKE) -C $(LOCAL_TOPOLOGIES) clean 2>/dev/null || true
	@$(MAKE) -C $(TCP_ONE) clean 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_ONE_ONE) clean 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_ONE_MANY) clean 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_MULTI) clean 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_CALL) clean 2>/dev/null || true
	@rm -f $(SELF_DIR)*.pid $(SELF_DIR)*.log
	@echo ">> 全局清理完成"
