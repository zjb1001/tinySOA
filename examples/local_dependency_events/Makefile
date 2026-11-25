# Makefile —— 本地依赖事件 / 控制面协调案例。
#
# 本文件位于: tinySOA/examples/local_dependency_events/Makefile
# tinysoa 从源码解析，无需 pip 安装。（不依赖 pysomeip）
#
# 常用：
#   make                 = make help
#   make run             = 前台运行完整流程
#   make start           = 后台启动
#   make stop            = 停止后台进程
#   make status          = 查看进程状态
#   make logs            = 实时查看日志
#   make smoke           = 冒烟测试 (dry-run + 事件序列校验)
#   make tmux            = tmux 双窗格可视化
#   make clean           = 停止进程并清理产物

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
PYTHONPATH  := $(TINYSOA_DIR):$(TINYSOA_DIR)/src:$(TINYSOA_DIR)/third_party/pysomeip/src
PYTHON      ?= $(shell [ -x "$(TINYSOA_DIR)/.venv/bin/python" ] && echo "$(TINYSOA_DIR)/.venv/bin/python" || echo python3)
MODULE      := examples.local_dependency_events

# ---- 可调参数 -----------------------------------------------------------
DURATION        ?= 30
DISCOVERY_DELAY ?= 0.5
WAIT_TIMEOUT    ?= 2.0
LOG_LEVEL       ?= INFO

# ---- 产物路径 -----------------------------------------------------------
PID_FILE := $(SELF_DIR).dependency-events.pid
LOG_FILE := $(SELF_DIR).dependency-events.log

.PHONY: help run start stop status logs smoke tmux tmux-kill clean

help: ## 显示帮助
	@echo "local_dependency_events —— 控制面事件 + 依赖协调案例"
	@echo ""
	@echo "  DatabaseService → SensorGatewayService → DashboardService"
	@echo "  Dashboard 还等待一个远程依赖（模拟 SD INSTANCE_DISCOVERED）。"
	@echo ""
	@echo "  make run             前台运行完整流程"
	@echo "  make start           后台启动"
	@echo "  make stop            停止后台进程"
	@echo "  make status          查看进程状态"
	@echo "  make logs            实时 tail 日志"
	@echo "  make smoke           冒烟测试: dry-run + 1s 运行 + 事件序列校验"
	@echo "  make tmux            tmux 双窗格可视化"
	@echo "  make tmux-kill       关闭 tmux 会话"
	@echo "  make clean           停止进程并删除产物"
	@echo ""
	@echo "  可调:  DURATION=$(DURATION) DISCOVERY_DELAY=$(DISCOVERY_DELAY)"
	@echo "         WAIT_TIMEOUT=$(WAIT_TIMEOUT) LOG_LEVEL=$(LOG_LEVEL)"
	@echo "  PYTHON:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

# ---- 前台 / 后台 --------------------------------------------------------

run: ## 前台运行完整流程
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) -m $(MODULE).app \
	    --duration $(DURATION) --discovery-delay $(DISCOVERY_DELAY) \
	    --wait-timeout $(WAIT_TIMEOUT) --log-level $(LOG_LEVEL)

start: stop ## 后台启动
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) -m $(MODULE).app \
	    --duration $(DURATION) --discovery-delay $(DISCOVERY_DELAY) \
	    --wait-timeout $(WAIT_TIMEOUT) --log-level $(LOG_LEVEL) \
	    > $(LOG_FILE) 2>&1 & echo $$! > $(PID_FILE)
	@echo ">> 已启动 (pid $$(cat $(PID_FILE)))，日志 $(LOG_FILE)"
	@echo "   观察: make logs    停止: make stop"

stop: ## 停止后台进程
	@if [ -f "$(PID_FILE)" ]; then \
	  pid=$$(cat "$(PID_FILE)"); \
	  if kill -0 "$$pid" 2>/dev/null; then \
	    kill -INT "$$pid" 2>/dev/null || true; \
	    sleep 0.4; \
	    kill -0 "$$pid" 2>/dev/null && kill -TERM "$$pid" 2>/dev/null || true; \
	    echo ">> 已停止 pid $$pid"; \
	  else echo ">> pid $$pid 已不在"; fi; \
	  rm -f "$(PID_FILE)"; \
	fi

status: ## 查看后台进程状态
	@if [ -f "$(PID_FILE)" ]; then \
	  pid=$$(cat "$(PID_FILE)"); \
	  if kill -0 "$$pid" 2>/dev/null; then echo "local_dependency_events: 运行中 (pid $$pid)"; \
	  else echo "local_dependency_events: 未运行 (残留 pid $$pid)"; fi; \
	else echo "local_dependency_events: 未启动"; fi

logs: ## 实时 tail 日志
	@echo "(Ctrl+C 退出查看，进程继续运行)"
	@tail -F $(LOG_FILE) 2>/dev/null

# ---- 冒烟测试 -----------------------------------------------------------

smoke: ## 冒烟测试: dry-run + 运行 + 事件序列校验
	@echo "=== local_dependency_events 冒烟开始 ==="; \
	echo "  Phase 1: dry-run (依赖计划)"; \
	cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) -m $(MODULE).app --dry-run --log-level INFO; \
	echo ""; \
	echo "  Phase 2: 运行 1s"; \
	cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) -m $(MODULE).app \
	    --duration 1 --discovery-delay 0.2 --wait-timeout 2.0 \
	    --log-level INFO > $(LOG_FILE) 2>&1; EXIT=$$?; \
	echo ""; \
	echo "  Phase 3: 验证"; \
	if grep -q "dependency.satisfied" $(LOG_FILE); then echo "  ✓ DEPENDENCY_SATISFIED"; else echo "  ✗ DEPENDENCY_SATISFIED: MISSING"; fi; \
	if grep -q "instance.discovered" $(LOG_FILE); then echo "  ✓ INSTANCE_DISCOVERED"; else echo "  ✗ INSTANCE_DISCOVERED: MISSING"; fi; \
	if grep -q "check: remote telemetry discovered before dashboard READY" $(LOG_FILE); then echo "  ✓ dependency wait ordering"; else echo "  ✗ dependency wait ordering: MISSING"; fi; \
	if grep -q "dependency.lost" $(LOG_FILE); then echo "  ✓ DEPENDENCY_LOST"; else echo "  ✗ DEPENDENCY_LOST: MISSING"; fi; \
	if grep -q "event summary:" $(LOG_FILE); then echo "  ✓ event summary"; else echo "  ✗ event summary: MISSING"; fi; \
	if [ $$EXIT -eq 0 ]; then echo "=== 冒烟 PASS ==="; else echo "=== 冒烟 FAIL (exit=$$EXIT) ==="; fi; \
	rm -f $(LOG_FILE)

# ---- tmux ---------------------------------------------------------------

tmux: ## tmux 双窗格可视化
	@bash $(SELF_DIR)tmux.sh

tmux-kill: ## 关闭 tmux 会话
	@tmux kill-session -t tinysoa-dependency-events 2>/dev/null && echo ">> 已关闭" || echo ">> 无会话"

# ---- 清理 ---------------------------------------------------------------

clean: stop
	@rm -f $(PID_FILE) $(LOG_FILE)
	@echo ">> 已清理 pid/log 产物"
