# Makefile —— 管理 cross-process SOME/IP pub/sub 测试的启动与退出。
#
# 本文件位于: tinySOA/examples/cross_process_someip/Makefile
# 两个包（someip / tinysoa）均从源码解析，无需 pip 安装。
#
# 常用：
#   make            # = make help
#   make run        # 前台跑一次编排器（完整跨进程测试，推荐）
#   make start      # 后台常驻启动 publisher + subscriber
#   make stop       # 停止后台进程
#   make status     # 查看后台进程状态
#   make logs       # 实时查看后台日志（Ctrl+C 退出查看，进程不停）
#   make pytest     # 跑 pytest（含真实网络的慢测试）
#   make pytest-fast# 只跑无网络的快速测试
#   make clean      # 停止后台进程并清理 .pid/.log

.DEFAULT_GOAL := help
SHELL := /bin/bash

# --- 路径（相对本 Makefile 定位）---
SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
REPO_ROOT   := $(abspath $(SELF_DIR)../../..)

# someip(pysomeip) 与 tinysoa 都从源码导入
PYTHONPATH := $(REPO_ROOT)/src:$(TINYSOA_DIR)/src

# 优先用项目自带 .venv（含 someip+pytest），否则退回 python3
PYTHON ?= $(shell [ -x "$(REPO_ROOT)/.venv/bin/python" ] && echo "$(REPO_ROOT)/.venv/bin/python" || echo python3)

MOD := examples.cross_process_someip
PID_PUB := $(SELF_DIR).pub.pid
PID_SUB := $(SELF_DIR).sub.pid
LOG_PUB := $(SELF_DIR).pub.log
LOG_SUB := $(SELF_DIR).sub.log

# 后台常驻模式参数：大 count/want + 慢节奏，靠 make stop 终止。
PUB_COUNT   ?= 100000
PUB_INTERVAL ?= 1.0
SUB_WANT    ?= 100000
SUB_TIMEOUT ?= 100000

.PHONY: help run start stop status logs logs-pub logs-sub pytest pytest-fast tmux tmux-kill clean

help: ## 显示帮助
	@echo "cross-process SOME/IP pub/sub —— Makefile"
	@echo ""
	@echo "  make run           前台跑一次编排器（完整跨进程测试，推荐）"
	@echo "  make start         后台常驻启动 publisher + subscriber"
	@echo "  make stop          停止后台 publisher / subscriber"
	@echo "  make status        查看后台进程状态"
	@echo "  make logs          实时 tail 后台日志（publisher + subscriber）"
	@echo "  make logs-pub      只看 publisher 日志"
	@echo "  make logs-sub      只看 subscriber 日志"
	@echo "  make pytest        跑 pytest（含真实网络的慢测试，约 15s）"
	@echo "  make pytest-fast   只跑无网络的快速测试"
	@echo "  make tmux          tmux 三窗格可视化（上=SD监控 下左=pub 下右=sub）"
	@echo "  make tmux-kill     关闭 tmux 演示会话"
	@echo "  make clean         停止后台进程并清理 .pid/.log 产物"
	@echo ""
	@echo "  python:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

run: ## 前台跑一次编排器（publisher 进程 + subscriber 进程）
	@echo ">> 启动跨进程编排器 ..."
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) $(PYTHON) $(SELF_DIR)run_cross_process.py

start: ## 后台常驻启动 publisher + subscriber
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) -m $(MOD).publisher $(PUB_COUNT) $(PUB_INTERVAL) > $(LOG_PUB) 2>&1 & echo $$! > $(PID_PUB)
	@echo ">> publisher 已启动 (pid $$(cat $(PID_PUB)))，日志 $(LOG_PUB)"
	@echo ">> 等待 4s 让 SD Offer 收敛 ..."
	@sleep 4
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) -m $(MOD).subscriber $(SUB_WANT) $(SUB_TIMEOUT) > $(LOG_SUB) 2>&1 & echo $$! > $(PID_SUB)
	@echo ">> subscriber 已启动 (pid $$(cat $(PID_SUB)))，日志 $(LOG_SUB)"
	@echo "   观察: make logs    停止: make stop"

stop: ## 停止后台 publisher / subscriber（先 INT 干净退出，再 TERM 兜底）
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

logs: ## 实时查看后台日志（publisher + subscriber）
	@echo "（Ctrl+C 退出查看，后台进程继续运行）"
	@tail -F $(LOG_PUB) $(LOG_SUB) 2>/dev/null

logs-pub: ## 只看 publisher 日志
	@tail -F $(LOG_PUB) 2>/dev/null

logs-sub: ## 只看 subscriber 日志
	@tail -F $(LOG_SUB) 2>/dev/null

pytest: ## 跑 pytest（含真实网络的慢测试）
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_cross_process_someip.py -v

pytest-fast: ## 只跑无网络的快速测试
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_cross_process_someip.py -v -m "not slow"

tmux: ## tmux 三窗格可视化（上=SD监控 下左=Publisher 下右=Subscriber）
	@bash $(SELF_DIR)tmux_demo.sh

tmux-kill: ## 关闭 tmux 演示会话
	@tmux kill-session -t tinysoa-someip 2>/dev/null && echo ">> 已关闭 tmux 会话 tinysoa-someip" || echo ">> 无会话"

clean: stop ## 停止后台进程并清理 .pid/.log
	@rm -f $(PID_PUB) $(PID_SUB) $(LOG_PUB) $(LOG_SUB)
	@echo ">> 已清理 pid/log 产物"
