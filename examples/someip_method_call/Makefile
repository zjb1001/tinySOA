# Makefile —— SOME/IP Calculator RPC 示例（双进程 method call）。
#
# 本文件位于: tinySOA/examples/someip_method_call/Makefile
# 依赖 pysomeip 协议栈（需要仓库根 pip install -e .）
#
# 常用：
#   make                 = make help
#   make start           = 后台启动 Server
#   make stop            = 停止后台进程
#   make status          = 查看进程状态
#   make logs            = 实时查看日志
#   make smoke           = 冒烟测试: Server 启动 → Client 调用 → 验证 3 method 全 PASS
#   make tmux            = tmux 双窗格可视化 (左: Server, 右: Client)
#   make clean           = 停止进程并清理产物

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
PYTHONPATH  := $(TINYSOA_DIR):$(TINYSOA_DIR)/src:$(TINYSOA_DIR)/third_party/pysomeip/src
PYTHON      ?= python3
MODULE      := examples.someip_method_call

# ---- 可调参数 -----------------------------------------------------------
LOG_LEVEL ?= INFO

# ---- 产物路径 -----------------------------------------------------------
PID_SRV := $(SELF_DIR).srv.pid
LOG_SRV := $(SELF_DIR).srv.log
LOG_CLI := $(SELF_DIR).cli.log

.PHONY: help start stop status logs smoke tmux tmux-kill clean

help: ## 显示帮助
	@echo "SOME/IP Calculator RPC —— Makefile"
	@echo ""
	@echo "  双进程示例：Server 通过 SD Offer 通告 Calculator 服务。"
	@echo "  Client 通过 SD Find 发现服务，发起 add / sub / mul 三个 RPC 调用。"
	@echo ""
	@echo "  make start           后台启动 Server"
	@echo "  make stop            停止后台进程"
	@echo "  make status          查看进程状态"
	@echo "  make logs            实时 tail Server 日志"
	@echo "  make smoke           冒烟测试: Server → Client(3 calls) → 验证"
	@echo "  make tmux            tmux 双窗格可视化 (左: Server, 右: Client)"
	@echo "  make tmux-kill        关闭 tmux 会话"
	@echo "  make clean            停止进程并删除产物"
	@echo ""
	@echo "  PYTHON:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

# ---- 后台常驻 -----------------------------------------------------------

start: stop ## 后台启动 Server
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) -m $(MODULE).server --log-level $(LOG_LEVEL) \
	    > $(LOG_SRV) 2>&1 & echo $$! > $(PID_SRV)
	@echo ">> Server 已启动 (pid $$(cat $(PID_SRV)))，日志 $(LOG_SRV)"
	@echo "   观察: make logs    运行 Client: make smoke"

stop: ## 停止后台进程 (先 INT，再 TERM 兜底)
	@if [ -f "$(PID_SRV)" ]; then \
	  pid=$$(cat "$(PID_SRV)"); \
	  if kill -0 "$$pid" 2>/dev/null; then \
	    kill -INT "$$pid" 2>/dev/null || true; \
	    sleep 0.6; \
	    kill -0 "$$pid" 2>/dev/null && kill -TERM "$$pid" 2>/dev/null || true; \
	    echo ">> 已停止 pid $$pid"; \
	  else echo ">> pid $$pid 已不在"; fi; \
	  rm -f "$(PID_SRV)"; \
	fi

status: ## 查看后台进程状态
	@if [ -f "$(PID_SRV)" ]; then \
	  pid=$$(cat "$(PID_SRV)"); \
	  if kill -0 "$$pid" 2>/dev/null; then echo "Server: 运行中 (pid $$pid)"; \
	  else echo "Server: 未运行 (残留 pid $$pid)"; fi; \
	else echo "Server: 未启动"; fi

logs: ## 实时 tail Server 日志
	@echo "(Ctrl+C 退出查看，进程继续运行)"
	@tail -F $(LOG_SRV) 2>/dev/null

# ---- 冒烟测试 -----------------------------------------------------------

smoke: ## 冒烟测试: Server 启动 → Client 调用 → 验证 3 method 全部 PASS
	@echo "=== SOME/IP Calculator RPC 冒烟开始 ==="; \
	echo "  Phase 1: 启动 Server ..."; \
	cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) -m $(MODULE).server --log-level INFO \
	    > $(LOG_SRV) 2>&1 & echo $$! > $(PID_SRV); \
	sleep 3; \
	echo "  Phase 2: 运行 Client ..."; \
	cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) -m $(MODULE).client --log-level INFO \
	    > $(LOG_CLI) 2>&1; EXIT=$$?; \
	echo ""; \
	echo "  Phase 3: 验证"; \
	if grep -q "PASS  add" $(LOG_CLI); then echo "  ✓ add(10, 7) = 17"; else echo "  ✗ add FAILED"; fi; \
	if grep -q "PASS  subtract" $(LOG_CLI); then echo "  ✓ subtract(50, 18) = 32"; else echo "  ✗ subtract FAILED"; fi; \
	if grep -q "PASS  multiply" $(LOG_CLI); then echo "  ✓ multiply(6, 8) = 48"; else echo "  ✗ multiply FAILED"; fi; \
	if grep -q "3 passed, 0 failed" $(LOG_CLI); then echo "  ✓ All 3 passed"; else echo "  ✗ Some FAILED"; fi; \
	if [ $$EXIT -eq 0 ]; then echo "=== 冒烟 PASS ==="; else echo "=== 冒烟 FAIL (exit=$$EXIT) ==="; fi; \
	if [ -f "$(PID_SRV)" ]; then \
	  pid=$$(cat "$(PID_SRV)"); \
	  kill -INT "$$pid" 2>/dev/null || true; \
	  sleep 0.3; \
	  kill -TERM "$$pid" 2>/dev/null || true; \
	  rm -f "$(PID_SRV)"; \
	fi; \
	rm -f $(LOG_CLI) $(LOG_SRV)

# ---- tmux ---------------------------------------------------------------

tmux: ## tmux 双窗格可视化 (左: Server, 右: Client)
	@bash $(SELF_DIR)tmux.sh

tmux-kill: ## 关闭 tmux 会话
	@tmux kill-session -t tinysoa-calc 2>/dev/null && echo ">> 已关闭" || echo ">> 无会话"

# ---- 清理 ---------------------------------------------------------------

clean: stop
	@rm -f $(PID_SRV) $(LOG_SRV) $(LOG_CLI)
	@echo ">> 已清理 pid/log 产物"
