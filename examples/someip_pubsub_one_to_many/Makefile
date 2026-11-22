# Makefile —— SOME/IP 一发多收示例。
#
# 一个 publisher 通过 SD Offer 通告服务，两个独立 subscriber 进程分别订阅
# 同一个 eventgroup，接收 unicast notification。
#
# 常用：
#   make                 = help
#   make start           = 后台启动 publisher + 2 subscribers
#   make stop            = 停止全部后台进程
#   make status          = 查看进程状态
#   make logs            = tail 全部日志
#   make smoke           = 端到端冒烟（两个 subscriber 都收到）
#   make tmux            = tmux 三窗格可视化
#   make clean           = 停止并清理产物

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
PYTHONPATH  := $(TINYSOA_DIR):$(TINYSOA_DIR)/src:$(TINYSOA_DIR)/third_party/pysomeip/src
PYTHON      ?= $(shell [ -x "$(TINYSOA_DIR)/.venv/bin/python" ] && echo "$(TINYSOA_DIR)/.venv/bin/python" || echo python3)
MODULE      := examples.someip_pubsub_one_to_many

# ---- 可调参数 -----------------------------------------------------------
LOG_LEVEL     ?= INFO
PUB_COUNT     ?= 20
PUB_INTERVAL  ?= 1.0
SUB_WANT      ?= 3
SUB_TIMEOUT   ?= 40
SUB1_PORT     ?= 30930
SUB2_PORT     ?= 30940
SMOKE_PUB_COUNT ?= 12
SMOKE_WAIT      ?= 18

# ---- 产物路径 -----------------------------------------------------------
PID_PUB  := $(SELF_DIR).pub.pid
PID_SUB1 := $(SELF_DIR).sub1.pid
PID_SUB2 := $(SELF_DIR).sub2.pid
LOG_PUB  := $(SELF_DIR).pub.log
LOG_SUB1 := $(SELF_DIR).sub1.log
LOG_SUB2 := $(SELF_DIR).sub2.log

.PHONY: help start stop status logs logs-pub logs-sub smoke tmux tmux-kill clean

help: ## 显示帮助
	@echo "SOME/IP one-to-many —— Makefile"
	@echo ""
	@echo "  make start       后台启动 publisher + 2 subscribers"
	@echo "  make stop        停止后台进程"
	@echo "  make status      查看进程状态"
	@echo "  make logs        实时 tail 全部日志"
	@echo "  make logs-pub    只看 publisher 日志"
	@echo "  make logs-sub    只看 subscriber 日志"
	@echo "  make smoke       端到端冒烟"
	@echo "  make tmux        tmux 三窗格可视化"
	@echo "  make tmux-kill   关闭 tmux 会话"
	@echo "  make clean       停止并清理产物"
	@echo ""
	@echo "  PUB_COUNT=$(PUB_COUNT) PUB_INTERVAL=$(PUB_INTERVAL)"
	@echo "  SUB_WANT=$(SUB_WANT) SUB1_PORT=$(SUB1_PORT) SUB2_PORT=$(SUB2_PORT)"
	@echo "  PYTHON:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

# ---- 后台常驻 -----------------------------------------------------------

start: stop ## 后台启动 publisher + 2 subscribers
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) -m $(MODULE).publisher --count $(PUB_COUNT) --interval $(PUB_INTERVAL) \
	    --log-level $(LOG_LEVEL) > $(LOG_PUB) 2>&1 & echo $$! > $(PID_PUB)
	@echo ">> publisher 已启动 (pid $$(cat $(PID_PUB)))"
	@sleep 2.5
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) -m $(MODULE).subscriber sub-1 --want $(SUB_WANT) --timeout $(SUB_TIMEOUT) \
	    --local-port $(SUB1_PORT) --log-level $(LOG_LEVEL) > $(LOG_SUB1) 2>&1 & echo $$! > $(PID_SUB1)
	@echo ">> subscriber sub-1 已启动 (pid $$(cat $(PID_SUB1)))"
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) -m $(MODULE).subscriber sub-2 --want $(SUB_WANT) --timeout $(SUB_TIMEOUT) \
	    --local-port $(SUB2_PORT) --log-level $(LOG_LEVEL) > $(LOG_SUB2) 2>&1 & echo $$! > $(PID_SUB2)
	@echo ">> subscriber sub-2 已启动 (pid $$(cat $(PID_SUB2)))"
	@echo "   观察: make logs    停止: make stop"

stop: ## 停止后台进程
	@for kv in "publisher:$(PID_PUB)" "sub-1:$(PID_SUB1)" "sub-2:$(PID_SUB2)"; do \
	  name=$${kv%%:*}; pidf=$${kv#*:}; \
	  if [ -f "$$pidf" ]; then \
	    pid=$$(cat "$$pidf"); \
	    if kill -0 "$$pid" 2>/dev/null; then \
	      kill -INT "$$pid" 2>/dev/null || true; \
	      sleep 0.3; \
	      kill -0 "$$pid" 2>/dev/null && kill -TERM "$$pid" 2>/dev/null || true; \
	      echo ">> 已停止 $$name (pid $$pid)"; \
	    else echo ">> $$name 已不在 (pid $$pid)"; fi; \
	    rm -f "$$pidf"; \
	  fi; \
	done

status: ## 查看进程状态
	@for kv in "publisher:$(PID_PUB)" "sub-1:$(PID_SUB1)" "sub-2:$(PID_SUB2)"; do \
	  name=$${kv%%:*}; pidf=$${kv#*:}; \
	  if [ -f "$$pidf" ]; then \
	    pid=$$(cat "$$pidf"); \
	    if kill -0 "$$pid" 2>/dev/null; then echo "$$name: 运行中 (pid $$pid)"; \
	    else echo "$$name: 未运行 (残留 pid $$pid)"; fi; \
	  else echo "$$name: 未启动"; fi; \
	done

logs: ## 实时 tail 全部日志
	@echo "(Ctrl+C 退出查看，进程继续运行)"
	@tail -F $(LOG_PUB) $(LOG_SUB1) $(LOG_SUB2) 2>/dev/null

logs-pub: ## 只看 publisher 日志
	@tail -F $(LOG_PUB) 2>/dev/null

logs-sub: ## 只看 subscriber 日志
	@tail -F $(LOG_SUB1) $(LOG_SUB2) 2>/dev/null

# ---- 冒烟 ---------------------------------------------------------------

smoke: ## 端到端冒烟
	@echo "=== SOME/IP one-to-many 冒烟 ==="
	@echo "  publisher $(SMOKE_PUB_COUNT) 条, 两个 subscriber 各期望 $(SUB_WANT) 条"
	@$(MAKE) --no-print-directory start PUB_COUNT=$(SMOKE_PUB_COUNT)
	@echo "  等待 SD 收敛与消息投递 ..."
	@sleep $(SMOKE_WAIT)
	@S1=$$(grep -c "RECEIVED" $(LOG_SUB1) 2>/dev/null || echo 0); \
	 S2=$$(grep -c "RECEIVED" $(LOG_SUB2) 2>/dev/null || echo 0); \
	 echo "=== sub-1 收到 $$S1 条, sub-2 收到 $$S2 条 ==="; \
	 $(MAKE) --no-print-directory stop; \
	 test "$$S1" -ge "$(SUB_WANT)" && test "$$S2" -ge "$(SUB_WANT)"

# ---- tmux ---------------------------------------------------------------

tmux: ## tmux 三窗格可视化
	@bash $(SELF_DIR)tmux.sh

tmux-kill: ## 关闭 tmux 会话
	@tmux kill-session -t tinysoa-someip-one-to-many 2>/dev/null && echo ">> 已关闭" || echo ">> 无会话"

# ---- 清理 ---------------------------------------------------------------

clean: stop
	@rm -f $(PID_PUB) $(PID_SUB1) $(PID_SUB2) $(LOG_PUB) $(LOG_SUB1) $(LOG_SUB2)
	@echo ">> 已清理 pid/log 产物"
