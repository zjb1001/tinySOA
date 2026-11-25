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
#   make tmux-pubsub-one-pub-many-subs            = TCP broker 一发多收
#   make tmux-someip-one-pub-many-subs= SOME/IP 一发多收
#   make tmux-someip-many-pubs-one-sub            = SOME/IP 多传感器
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
LOCAL_DEP_EVENTS := $(SELF_DIR)local_dependency_events/
TCP_ONE_PUB_MANY_SUBS := $(SELF_DIR)tcp_pubsub_one_pub_many_subs/
SOMEIP_ONE_PUB_ONE_SUB := $(SELF_DIR)someip_pubsub_one_pub_one_sub/
SOMEIP_ONE_PUB_MANY_SUBS := $(SELF_DIR)someip_pubsub_one_pub_many_subs/
SOMEIP_MANY_PUBS_ONE_SUB := $(SELF_DIR)someip_pubsub_many_pubs_one_sub/
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
	@echo "  make topologies                 1 pub→1 sub / 1 pub→N subs / N pubs→1 sub"
	@echo "  make dependency-events          依赖排序 + 控制面事件 + 远程依赖等待"
	@echo ""
	@echo "=== TCP broker（BROKER 拓扑） ==="
	@echo "  make tmux-pubsub-one-pub-many-subs                tmux：1 pub → N subs"
	@echo "  make smoke-pubsub-one-pub-many-subs               冒烟：1 pub → N subs"
	@echo ""
	@echo "=== SOME/IP（PEER 拓扑） ==="
	@echo "  make tmux-someip-one-pub-one-sub     tmux：1 pub → 1 sub"
	@echo "  make smoke-someip-one-pub-one-sub    冒烟：1 pub → 1 sub"
	@echo "  make tmux-someip-one-pub-many-subs    tmux：1 pub → N subs"
	@echo "  make smoke-someip-one-pub-many-subs   冒烟：1 pub → N subs"
	@echo "  make tmux-someip-many-pubs-one-sub                tmux：N pubs → 1 sub"
	@echo "  make smoke-someip-many-pubs-one-sub               冒烟：N pubs → 1 sub"
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
.PHONY: echo interceptors vdp topologies dependency-events \
        smoke-vdp smoke-dependency-events tmux-vdp tmux-dependency-events
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

dependency-events: ## 依赖排序 + 控制面事件 + 远程依赖等待
	@$(MAKE) -C $(LOCAL_DEP_EVENTS) run

smoke-vdp: ## 车辆数据平台冒烟
	@$(MAKE) -C $(LOCAL_VDP) smoke

smoke-dependency-events: ## 依赖事件案例冒烟
	@$(MAKE) -C $(LOCAL_DEP_EVENTS) smoke

tmux-vdp: ## tmux 可视化车辆数据平台
	@$(MAKE) -C $(LOCAL_VDP) tmux

tmux-dependency-events: ## tmux 可视化依赖事件案例
	@$(MAKE) -C $(LOCAL_DEP_EVENTS) tmux

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
.PHONY: tmux-pubsub-one-pub-many-subs smoke-pubsub-one-pub-many-subs start-pubsub-one-pub-many-subs stop-pubsub-one-pub-many-subs logs-pubsub-one-pub-many-subs
tmux-pubsub-one-pub-many-subs:
	@$(MAKE) -C $(TCP_ONE_PUB_MANY_SUBS) tmux
smoke-pubsub-one-pub-many-subs:
	@$(MAKE) -C $(TCP_ONE_PUB_MANY_SUBS) smoke
start-pubsub-one-pub-many-subs:
	@$(MAKE) -C $(TCP_ONE_PUB_MANY_SUBS) start
stop-pubsub-one-pub-many-subs:
	@$(MAKE) -C $(TCP_ONE_PUB_MANY_SUBS) stop
logs-pubsub-one-pub-many-subs:
	@$(MAKE) -C $(TCP_ONE_PUB_MANY_SUBS) logs

# =========================================================================
# SOME/IP pub/sub
# =========================================================================
.PHONY: tmux-someip-one-pub-one-sub smoke-someip-one-pub-one-sub \
        start-someip-one-pub-one-sub stop-someip-one-pub-one-sub logs-someip-one-pub-one-sub \
        tmux-someip-one-pub-many-subs smoke-someip-one-pub-many-subs \
        start-someip-one-pub-many-subs stop-someip-one-pub-many-subs logs-someip-one-pub-many-subs \
        tmux-someip-many-pubs-one-sub smoke-someip-many-pubs-one-sub start-someip-many-pubs-one-sub stop-someip-many-pubs-one-sub logs-someip-many-pubs-one-sub
tmux-someip-one-pub-one-sub:
	@$(MAKE) -C $(SOMEIP_ONE_PUB_ONE_SUB) tmux
smoke-someip-one-pub-one-sub:
	@$(MAKE) -C $(SOMEIP_ONE_PUB_ONE_SUB) smoke
start-someip-one-pub-one-sub:
	@$(MAKE) -C $(SOMEIP_ONE_PUB_ONE_SUB) start
stop-someip-one-pub-one-sub:
	@$(MAKE) -C $(SOMEIP_ONE_PUB_ONE_SUB) stop
logs-someip-one-pub-one-sub:
	@$(MAKE) -C $(SOMEIP_ONE_PUB_ONE_SUB) logs

tmux-someip-one-pub-many-subs:
	@$(MAKE) -C $(SOMEIP_ONE_PUB_MANY_SUBS) tmux
smoke-someip-one-pub-many-subs:
	@$(MAKE) -C $(SOMEIP_ONE_PUB_MANY_SUBS) smoke
start-someip-one-pub-many-subs:
	@$(MAKE) -C $(SOMEIP_ONE_PUB_MANY_SUBS) start
stop-someip-one-pub-many-subs:
	@$(MAKE) -C $(SOMEIP_ONE_PUB_MANY_SUBS) stop
logs-someip-one-pub-many-subs:
	@$(MAKE) -C $(SOMEIP_ONE_PUB_MANY_SUBS) logs

tmux-someip-many-pubs-one-sub:
	@$(MAKE) -C $(SOMEIP_MANY_PUBS_ONE_SUB) tmux
smoke-someip-many-pubs-one-sub:
	@$(MAKE) -C $(SOMEIP_MANY_PUBS_ONE_SUB) smoke
start-someip-many-pubs-one-sub:
	@$(MAKE) -C $(SOMEIP_MANY_PUBS_ONE_SUB) start
stop-someip-many-pubs-one-sub:
	@$(MAKE) -C $(SOMEIP_MANY_PUBS_ONE_SUB) stop
logs-someip-many-pubs-one-sub:
	@$(MAKE) -C $(SOMEIP_MANY_PUBS_ONE_SUB) logs

# =========================================================================
# 全局
# =========================================================================
.PHONY: start-all stop-all status-all smoke-all clean-all
start-all: start-someip-one-pub-one-sub start-someip-one-pub-many-subs start-pubsub-one-pub-many-subs start-someip-many-pubs-one-sub ## 后台启动所有常驻组
	@echo ">> 所有常驻示例组已后台启动"

stop-all: ## 停止全部示例组
	@$(MAKE) -C $(SOMEIP_ONE_PUB_ONE_SUB) stop 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_ONE_PUB_MANY_SUBS) stop 2>/dev/null || true
	@$(MAKE) -C $(TCP_ONE_PUB_MANY_SUBS) stop 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_MANY_PUBS_ONE_SUB) stop 2>/dev/null || true
	@echo ">> 所有示例组已停止"

status-all: ## 查看全部示例组状态
	@echo "=== tcp_pubsub_one_pub_many_subs ==="; $(MAKE) --no-print-directory -C $(TCP_ONE_PUB_MANY_SUBS) status
	@echo "=== someip_pubsub_one_pub_one_sub ==="; $(MAKE) --no-print-directory -C $(SOMEIP_ONE_PUB_ONE_SUB) status
	@echo "=== someip_pubsub_one_pub_many_subs ==="; $(MAKE) --no-print-directory -C $(SOMEIP_ONE_PUB_MANY_SUBS) status
	@echo "=== someip_pubsub_many_pubs_one_sub ==="; $(MAKE) --no-print-directory -C $(SOMEIP_MANY_PUBS_ONE_SUB) status

smoke-all: echo interceptors topologies smoke-pubsub-one-pub-many-subs smoke-someip-one-pub-one-sub smoke-someip-one-pub-many-subs smoke-someip-many-pubs-one-sub smoke-vdp smoke-dependency-events smoke-calc ## 顺序跑稳定冒烟组
	@echo ">> 所有冒烟测试完成"

clean-all: stop-all ## 停止全部进程并清理产物
	@$(MAKE) -C $(LOCAL_ECHO) clean 2>/dev/null || true
	@$(MAKE) -C $(LOCAL_INTERCEPTORS) clean 2>/dev/null || true
	@$(MAKE) -C $(LOCAL_VDP) clean 2>/dev/null || true
	@$(MAKE) -C $(LOCAL_TOPOLOGIES) clean 2>/dev/null || true
	@$(MAKE) -C $(LOCAL_DEP_EVENTS) clean 2>/dev/null || true
	@$(MAKE) -C $(TCP_ONE_PUB_MANY_SUBS) clean 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_ONE_PUB_ONE_SUB) clean 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_ONE_PUB_MANY_SUBS) clean 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_MANY_PUBS_ONE_SUB) clean 2>/dev/null || true
	@$(MAKE) -C $(SOMEIP_CALL) clean 2>/dev/null || true
	@rm -f $(SELF_DIR)*.pid $(SELF_DIR)*.log
	@echo ">> 全局清理完成"
