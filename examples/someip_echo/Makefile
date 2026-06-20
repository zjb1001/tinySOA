# Makefile —— 管理 SOME/IP Echo 双进程示例的启动、测试与退出。
#
# 本文件位于: tinySOA/examples/someip_echo/Makefile
#
# 常用：
#   make             = make help
#   make start       = 后台启动 publisher + subscriber
#   make stop        = 停止后台进程
#   make status      = 查看进程状态
#   make logs        = 实时查看日志
#   make smoke       = bounded 冒烟（publisher N 条，subscriber 验证入站）
#   make clean       = 停止进程并清理产物

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
PYTHONPATH  := $(TINYSOA_DIR)/src:$(TINYSOA_DIR)/third_party/pysomeip/src
PYTHON      ?= python3

# ---- 可调参数 -----------------------------------------------------------
LOG_LEVEL     ?= INFO
PUB_COUNT     ?= 100000
PUB_INTERVAL  ?= 1.0
SUB_WANT      ?= 100000
SUB_TIMEOUT   ?= 100000
SMOKE_COUNT   ?= 3
SMOKE_INTERVAL ?= 0.5
SMOKE_WANT    ?= 3
SMOKE_TIMEOUT ?= 40

# ---- 产物路径 -----------------------------------------------------------
PID_PUB := $(SELF_DIR).pub.pid
PID_SUB := $(SELF_DIR).sub.pid
LOG_PUB := $(SELF_DIR).pub.log
LOG_SUB := $(SELF_DIR).sub.log

.PHONY: help start stop status logs logs-pub logs-sub smoke tmux tmux-kill clean

help: ## 显示帮助
	@echo "SOME/IP Echo 双进程示例 —— Makefile"
	@echo ""
	@echo "  make start       后台启动 publisher + subscriber (常驻)"
	@echo "  make stop        停止后台进程"
	@echo "  make status      查看进程状态"
	@echo "  make logs        实时 tail 日志 (publisher + subscriber)"
	@echo "  make logs-pub    只看 publisher 日志"
	@echo "  make logs-sub    只看 subscriber 日志"
	@echo "  make smoke       bounded 冒烟：publisher $(SMOKE_COUNT) 条 → subscriber 验证入站"
	@echo "  make tmux        tmux 双窗格可视化"
	@echo "  make tmux-kill   关闭 tmux 会话"
	@echo "  make clean       停止进程并删除产物"
	@echo ""
	@echo "  可调:  PUB_COUNT=$(PUB_COUNT) PUB_INTERVAL=$(PUB_INTERVAL)"
	@echo "         SUB_WANT=$(SUB_WANT) SUB_TIMEOUT=$(SUB_TIMEOUT)"
	@echo "         SMOKE_COUNT=$(SMOKE_COUNT) SMOKE_WANT=$(SMOKE_WANT)"
	@echo "  python:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

# ---- 后台常驻 -----------------------------------------------------------

start: stop ## 后台启动 publisher + subscriber
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) publisher.py --count $(PUB_COUNT) --interval $(PUB_INTERVAL) \
	    > $(LOG_PUB) 2>&1 & echo $$! > $(PID_PUB)
	@echo ">> publisher 已启动 (pid $$(cat $(PID_PUB)))，日志 $(LOG_PUB)"
	@sleep 2.5  # 等 SD Offer 收敛
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) subscriber.py --want $(SUB_WANT) --timeout $(SUB_TIMEOUT) \
	    > $(LOG_SUB) 2>&1 & echo $$! > $(PID_SUB)
	@echo ">> subscriber 已启动 (pid $$(cat $(PID_SUB)))，日志 $(LOG_SUB)"
	@echo "   观察: make logs    停止: make stop"

stop: ## 停止后台进程
	@for pidf in $(PID_PUB) $(PID_SUB); do \
	  if [ -f "$$pidf" ]; then \
	    pid=$$(cat "$$pidf"); \
	    if kill -0 "$$pid" 2>/dev/null; then \
	      kill -INT "$$pid" 2>/dev/null || true; \
	      sleep 0.4; \
	      kill -0 "$$pid" 2>/dev/null && kill -TERM "$$pid" 2>/dev/null || true; \
	      echo ">> 已停止 pid $$pid ($$pidf)"; \
	    else echo ">> pid $$pid 已不在 ($$pidf)"; fi; \
	    rm -f "$$pidf"; \
	  fi; \
	done

status: ## 查看后台进程状态
	@for pair in "publisher:$(PID_PUB)" "subscriber:$(PID_SUB)"; do \
	  name=$${pair%%:*}; pidf=$${pair#*:}; \
	  if [ -f "$$pidf" ]; then \
	    pid=$$(cat "$$pidf"); \
	    if kill -0 "$$pid" 2>/dev/null; then echo "$$name: 运行中 (pid $$pid)"; \
	    else echo "$$name: 未运行 (残留 pid $$pid)"; fi; \
	  else echo "$$name: 未启动"; fi; \
	done

logs: ## 实时 tail 日志
	@echo "(Ctrl+C 退出查看，进程继续运行)"
	@tail -F $(LOG_PUB) $(LOG_SUB) 2>/dev/null

logs-pub: ## 只看 publisher 日志
	@tail -F $(LOG_PUB) 2>/dev/null

logs-sub: ## 只看 subscriber 日志
	@tail -F $(LOG_SUB) 2>/dev/null

# ---- 端到端冒烟 ---------------------------------------------------------

smoke: ## bounded 冒烟
	@echo "=== SOME/IP Echo 冒烟 ==="
	@echo "  publisher $(SMOKE_COUNT) 条, subscriber 期望 $(SMOKE_WANT) 条"
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) publisher.py --count $(SMOKE_COUNT) --interval $(SMOKE_INTERVAL) \
	    > $(LOG_PUB) 2>&1 & echo $$! > $(PID_PUB)
	@sleep 2.5
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  timeout $(SMOKE_TIMEOUT) $(PYTHON) subscriber.py --want $(SMOKE_WANT) \
	    > $(LOG_SUB) 2>&1 || true
	@sleep 0.5
	@RECEIVED=$$(grep -c "RECEIVED" $(LOG_SUB) 2>/dev/null || echo 0); \
	 echo "=== 冒烟完成: subscriber 收到 $$RECEIVED 条 ==="
	@$(MAKE) --no-print-directory stop

# ---- tmux ---------------------------------------------------------------

tmux: ## tmux 双窗格可视化 (上: Publisher, 下: Subscriber)
	@bash $(SELF_DIR)tmux_demo.sh

tmux-kill: ## 关闭 tmux 会话
	@tmux kill-session -t tinysoa-echo 2>/dev/null && echo ">> 已关闭" || echo ">> 无会话"

# ---- 清理 ---------------------------------------------------------------

clean: stop
	@rm -f $(PID_PUB) $(PID_SUB) $(LOG_PUB) $(LOG_SUB)
	@echo ">> 已清理 pid/log 产物"
