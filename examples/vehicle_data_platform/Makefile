# Makefile —— 车辆数据平台（Vehicle Data Platform）工程实践案例。
#
# 本文件位于: tinySOA/examples/vehicle_data_platform/Makefile
# tinysoa 从源码解析，无需 pip 安装。（不依赖 pysomeip）
#
# 常用：
#   make                 = make help
#   make start           = 后台启动车辆数据平台
#   make stop            = 停止后台进程
#   make status          = 查看进程状态
#   make logs            = 实时查看日志
#   make smoke           = 冒烟测试 (dry-run + 5s run 验证完整生命周期)
#   make tmux            = tmux 双窗格可视化 (左: 平台运行, 右: 说明)
#   make clean           = 停止进程并清理产物

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
PYTHONPATH  := $(TINYSOA_DIR)/src
PYTHON      ?= python3

# ---- 可调参数 -----------------------------------------------------------
DURATION        ?= 15
HEALTH_INTERVAL ?= 3.0
LOG_LEVEL       ?= INFO

# ---- 产物路径 -----------------------------------------------------------
PID_FILE := $(SELF_DIR).vdp.pid
LOG_FILE := $(SELF_DIR).vdp.log

.PHONY: help start stop status logs smoke tmux tmux-kill clean

help: ## 显示帮助
	@echo "车辆数据平台 (Vehicle Data Platform) —— Makefile"
	@echo ""
	@echo "  这是一个单进程应用，展示 Container + LifecycleManager + EventBus 工程用法。"
	@echo "  4 个车载服务按依赖顺序启停，诊断仪周期健康检查。"
	@echo ""
	@echo "  make start           后台启动平台 (常驻)"
	@echo "  make stop            停止后台进程"
	@echo "  make status          查看进程状态"
	@echo "  make logs            实时 tail 日志"
	@echo "  make smoke           冒烟测试: dry-run → 5s 运行 → 验证完整生命周期"
	@echo "  make tmux            tmux 双窗格可视化 (左: 运行, 右: 架构说明)"
	@echo "  make tmux-kill        关闭 tmux 会话"
	@echo "  make clean            停止进程并删除产物"
	@echo ""
	@echo "  可调:  DURATION=$(DURATION) HEALTH_INTERVAL=$(HEALTH_INTERVAL)"
	@echo "         LOG_LEVEL=$(LOG_LEVEL)"
	@echo "  PYTHON:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

# ---- 后台常驻 -----------------------------------------------------------

start: stop ## 后台启动车辆数据平台
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) $(SELF_DIR)app.py \
	    --duration $(DURATION) --health-interval $(HEALTH_INTERVAL) \
	    --log-level $(LOG_LEVEL) > $(LOG_FILE) 2>&1 & echo $$! > $(PID_FILE)
	@echo ">> 车辆数据平台已启动 (pid $$(cat $(PID_FILE)))，日志 $(LOG_FILE)"
	@echo "   观察: make logs    停止: make stop"

stop: ## 停止后台进程 (先 INT 干净退出，再 TERM 兜底)
	@if [ -f "$(PID_FILE)" ]; then \
	  pid=$$(cat "$(PID_FILE)"); \
	  if kill -0 "$$pid" 2>/dev/null; then \
	    kill -INT "$$pid" 2>/dev/null || true; \
	    sleep 0.6; \
	    kill -0 "$$pid" 2>/dev/null && kill -TERM "$$pid" 2>/dev/null || true; \
	    echo ">> 已停止 pid $$pid"; \
	  else echo ">> pid $$pid 已不在"; fi; \
	  rm -f "$(PID_FILE)"; \
	fi

status: ## 查看后台进程状态
	@if [ -f "$(PID_FILE)" ]; then \
	  pid=$$(cat "$(PID_FILE)"); \
	  if kill -0 "$$pid" 2>/dev/null; then echo "车辆数据平台: 运行中 (pid $$pid)"; \
	  else echo "车辆数据平台: 未运行 (残留 pid $$pid)"; fi; \
	else echo "车辆数据平台: 未启动"; fi

logs: ## 实时 tail 日志
	@echo "(Ctrl+C 退出查看，进程继续运行)"
	@tail -F $(LOG_FILE) 2>/dev/null

# ---- 冒烟测试 -----------------------------------------------------------

smoke: ## 冒烟测试: dry-run → 运行 → 验证完整生命周期
	@echo "=== 车辆数据平台冒烟开始 ==="; \
	echo "  Phase 1: dry-run (验证注册 + 拓扑排序)"; \
	cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) $(SELF_DIR)app.py --dry-run --log-level INFO; \
	echo ""; \
	echo "  Phase 2: 运行 5s (完整启停 + 健康检查)"; \
	cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) $(SELF_DIR)app.py --duration 5 --health-interval 2.0 --log-level INFO \
	  > $(LOG_FILE) 2>&1; EXIT=$$?; \
	echo ""; \
	echo "  Phase 3: 验证"; \
	if grep -q "Ordered startup" $(LOG_FILE); then echo "  ✓ Phase 1: Ordered startup"; else echo "  ✗ Phase 1: MISSING"; fi; \
	if grep -q "Health report: 4/4 healthy" $(LOG_FILE); then echo "  ✓ Phase 2: Health check 4/4"; else echo "  ✗ Phase 2: MISSING"; fi; \
	if grep -q "shutdown complete" $(LOG_FILE); then echo "  ✓ Phase 3: Ordered shutdown"; else echo "  ✗ Phase 3: MISSING"; fi; \
	if grep -q "\[AUDIT\]" $(LOG_FILE); then echo "  ✓ Lifecycle hooks (AUDIT log)"; else echo "  ✗ Lifecycle hooks: MISSING"; fi; \
	if [ $$EXIT -eq 0 ]; then echo "=== 冒烟 PASS ==="; else echo "=== 冒烟 FAIL (exit=$$EXIT) ==="; fi; \
	rm -f $(LOG_FILE)

# ---- tmux ---------------------------------------------------------------

tmux: ## tmux 双窗格可视化 (左: 平台运行, 右: 架构说明)
	@bash $(SELF_DIR)tmux.sh

tmux-kill: ## 关闭 tmux 会话
	@tmux kill-session -t tinysoa-vdp 2>/dev/null && echo ">> 已关闭" || echo ">> 无会话"

# ---- 清理 ---------------------------------------------------------------

clean: stop
	@rm -f $(PID_FILE) $(LOG_FILE)
	@echo ">> 已清理 pid/log 产物"
