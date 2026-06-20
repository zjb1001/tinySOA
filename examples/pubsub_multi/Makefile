# Makefile —— 管理 TCP pub/sub 多进程示例的启动、测试与退出。
#
# 本文件位于: tinySOA/examples/pubsub_multi/Makefile
# tinysoa + someip 从源码解析，无需 pip 安装。
#
# 常用：
#   make                 = make help
#   make start           = 后台启动 server + subscriber
#   make stop            = 停止后台进程
#   make status          = 查看进程状态
#   make logs            = 实时查看日志
#   make smoke           = 端到端冒烟：server→subscriber→publisher→验证入站
#   make tmux            = tmux 四窗格可视化
#   make clean           = 停止进程并清理产物

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
REPO_ROOT   := $(abspath $(SELF_DIR)../../..)
PYTHONPATH  := $(REPO_ROOT)/src:$(TINYSOA_DIR)/src
PYTHON      ?= python3

# ---- 可调参数 -----------------------------------------------------------
HOST        ?= 127.0.0.1
PORT        ?= 8765
LOG_LEVEL   ?= INFO
PUB_COUNT   ?= 5
PUB_INTERVAL ?= 0.5
SUB_ID_1    ?= sub-1
SUB_ID_2    ?= sub-2

# ---- 产物路径 -----------------------------------------------------------
PID_SRV := $(SELF_DIR).srv.pid
PID_SUB := $(SELF_DIR).sub.pid
LOG_SRV := $(SELF_DIR).srv.log
LOG_SUB := $(SELF_DIR).sub.log
LOG_PUB := $(SELF_DIR).pub.log

.PHONY: help start stop status logs logs-srv logs-sub smoke tmux tmux-kill clean

help: ## 显示帮助
	@echo "TCP pub/sub 多进程示例 —— Makefile"
	@echo ""
	@echo "  make start           后台启动 server + subscriber (常驻)"
	@echo "  make stop            停止后台进程"
	@echo "  make status          查看进程状态"
	@echo "  make logs            实时 tail 日志 (server+subscriber)"
	@echo "  make logs-srv        只看 server 日志"
	@echo "  make logs-sub        只看 subscriber 日志"
	@echo "  make smoke           端到端冒烟：启动→订阅→发布→验证→停止"
	@echo "  make tmux            tmux 四窗格可视化"
	@echo "  make tmux-kill        关闭 tmux 会话"
	@echo "  make clean            停止进程并删除产物"
	@echo ""
	@echo "  可调:  HOST=$(HOST) PORT=$(PORT) LOG_LEVEL=$(LOG_LEVEL)"
	@echo "         PUB_COUNT=$(PUB_COUNT) PUB_INTERVAL=$(PUB_INTERVAL)"
	@echo "  PYTHON:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

# ---- 后台常驻 -----------------------------------------------------------

start: stop ## 后台启动 server + subscriber
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) $(SELF_DIR)server.py --host $(HOST) --port $(PORT) \
	    --log-level $(LOG_LEVEL) > $(LOG_SRV) 2>&1 & echo $$! > $(PID_SRV)
	@echo ">> server 已启动 (pid $$(cat $(PID_SRV)))，日志 $(LOG_SRV)"
	@sleep 0.8
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) $(SELF_DIR)subscriber.py $(SUB_ID_1) --host $(HOST) \
	    --port $(PORT) --log-level $(LOG_LEVEL) > $(LOG_SUB) 2>&1 & echo $$! > $(PID_SUB)
	@echo ">> subscriber $(SUB_ID_1) 已启动 (pid $$(cat $(PID_SUB)))，日志 $(LOG_SUB)"
	@echo "   观察: make logs    停止: make stop"

stop: ## 停止后台进程 (先 INT 干净退出，再 TERM 兜底)
	@for pidf in $(PID_SRV) $(PID_SUB); do \
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
	@rm -f $(LOG_PUB)

status: ## 查看后台进程状态
	@for pair in "server:$(PID_SRV)" "subscriber:$(PID_SUB)"; do \
	  name=$${pair%%:*}; pidf=$${pair#*:}; \
	  if [ -f "$$pidf" ]; then \
	    pid=$$(cat "$$pidf"); \
	    if kill -0 "$$pid" 2>/dev/null; then echo "$$name: 运行中 (pid $$pid)"; \
	    else echo "$$name: 未运行 (残留 pid $$pid)"; fi; \
	  else echo "$$name: 未启动"; fi; \
	done

logs: ## 实时 tail 日志 (server + subscriber)
	@echo "(Ctrl+C 退出查看，进程继续运行)"
	@tail -F $(LOG_SRV) $(LOG_SUB) 2>/dev/null

logs-srv: ## 只看 server 日志
	@tail -F $(LOG_SRV) 2>/dev/null

logs-sub: ## 只看 subscriber 日志
	@tail -F $(LOG_SUB) 2>/dev/null

# ---- 端到端冒烟 ---------------------------------------------------------

smoke: ## 端到端冒烟测试 (自动生命周期)
	@echo "=== TCP pub/sub 冒烟开始 ==="
	@echo "  HOST=$(HOST) PORT=$(PORT) COUNT=$(PUB_COUNT)"
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) $(SELF_DIR)server.py --host $(HOST) --port $(PORT) \
	    --log-level $(LOG_LEVEL) > $(LOG_SRV) 2>&1 & echo $$! > $(PID_SRV)
	@sleep 0.8
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) $(SELF_DIR)subscriber.py $(SUB_ID_1) --host $(HOST) \
	    --port $(PORT) --log-level $(LOG_LEVEL) > $(LOG_SUB) 2>&1 & echo $$! > $(PID_SUB)
	@sleep 0.6
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) $(SELF_DIR)publisher.py --host $(HOST) --port $(PORT) \
	    --count $(PUB_COUNT) --interval $(PUB_INTERVAL) --log-level $(LOG_LEVEL) \
	    > $(LOG_PUB) 2>&1; PEXIT=$$?
	@sleep 0.6
	@RECEIVED=$$(grep -c "subscriber=$(SUB_ID_1)" $(LOG_SUB) 2>/dev/null || echo 0); \
	 if [ "$$RECEIVED" -eq "$(PUB_COUNT)" ]; then \
	   echo "=== 冒烟 PASS: subscriber 收到 $$RECEIVED/$(PUB_COUNT) 条 ==="; \
	 else \
	   echo "=== 冒烟 WARN: subscriber 收到 $$RECEIVED/$(PUB_COUNT) 条 ==="; fi
	@$(MAKE) --no-print-directory stop
	@rm -f $(LOG_PUB) $(LOG_SRV) $(LOG_SUB)

# ---- tmux ---------------------------------------------------------------

tmux: ## tmux 四窗格可视化 (上:server|sub1 / 下:pub|sub2)
	@bash $(SELF_DIR)tmux_demo.sh

tmux-kill: ## 关闭 tmux 会话
	@tmux kill-session -t tinysoa-pubsub 2>/dev/null && echo ">> 已关闭" || echo ">> 无会话"

# ---- 清理 ---------------------------------------------------------------

clean: stop
	@rm -f $(PID_SRV) $(PID_SUB) $(LOG_SRV) $(LOG_SUB) $(LOG_PUB)
	@echo ">> 已清理 pid/log 产物"
