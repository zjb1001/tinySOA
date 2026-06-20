# Makefile —— 多发布者 / 单订阅者示例。
#
# 本示例复用 pubsub_multi 的 TCP server 和 subscriber，只管理
# 带 caller-identity 的多 publisher 进程。
#
# 本文件位于: tinySOA/examples/multi_publishers_single_sub/Makefile
#
# 常用：
#   make                 = make help
#   make start           = 后台启动 server + subscriber + 2 publishers
#   make stop            = 停止全部后台进程
#   make status          = 查看进程状态
#   make logs            = 实时 tail 全部日志
#   make smoke           = 端到端冒烟：pub-A + pub-B 交错发布，sub 验证去重入站
#   make clean           = 停止进程并清理产物

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
PUBSUB_DIR  := $(abspath $(SELF_DIR)../pubsub_multi)/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
REPO_ROOT   := $(abspath $(SELF_DIR)../../..)
PYTHONPATH  := $(REPO_ROOT)/src:$(TINYSOA_DIR)/src
PYTHON      ?= python3

# ---- 可调参数 -----------------------------------------------------------
HOST        ?= 127.0.0.1
PORT        ?= 8765
LOG_LEVEL   ?= INFO
PUB_A_ID    ?= pub-A
PUB_B_ID    ?= pub-B
PUB_COUNT   ?= 8
PUB_INTERVAL ?= 0.4
SUB_ID      ?= sub-collector

# ---- 产物路径 -----------------------------------------------------------
PID_SRV := $(SELF_DIR).srv.pid
PID_SUB := $(SELF_DIR).sub.pid
PID_A   := $(SELF_DIR).pubA.pid
PID_B   := $(SELF_DIR).pubB.pid
LOG_SRV := $(SELF_DIR).srv.log
LOG_SUB := $(SELF_DIR).sub.log
LOG_A   := $(SELF_DIR).pubA.log
LOG_B   := $(SELF_DIR).pubB.log

.PHONY: help start stop status logs logs-sub smoke clean

help: ## 显示帮助
	@echo "多发布者 / 单订阅者 —— Makefile"
	@echo ""
	@echo "  本示例复用 $(PUBSUB_DIR) 的 server + subscriber"
	@echo ""
	@echo "  make start           后台启动全部 (server + sub + pub-A + pub-B)"
	@echo "  make stop            停止全部后台进程"
	@echo "  make status          查看进程状态"
	@echo "  make logs            实时 tail 全部日志"
	@echo "  make logs-sub        只看 subscriber 日志"
	@echo "  make smoke           端到端冒烟：交错发布 → 验证 subscriber 入站"
	@echo "  make clean            停止进程并删除产物"
	@echo ""
	@echo "  可调:  HOST=$(HOST) PORT=$(PORT) LOG_LEVEL=$(LOG_LEVEL)"
	@echo "         PUB_A_ID=$(PUB_A_ID) PUB_B_ID=$(PUB_B_ID)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

# ---- 后台常驻 -----------------------------------------------------------

start: stop ## 后台启动 server + subscriber + 2 publishers
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) $(PUBSUB_DIR)server.py --host $(HOST) --port $(PORT) \
	    --log-level $(LOG_LEVEL) > $(LOG_SRV) 2>&1 & echo $$! > $(PID_SRV)
	@echo ">> server      已启动 (pid $$(cat $(PID_SRV)))"
	@sleep 0.6
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) $(PUBSUB_DIR)subscriber.py $(SUB_ID) --host $(HOST) \
	    --port $(PORT) --log-level $(LOG_LEVEL) > $(LOG_SUB) 2>&1 & echo $$! > $(PID_SUB)
	@echo ">> subscriber  已启动 (pid $$(cat $(PID_SUB)))"
	@sleep 0.4
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) $(SELF_DIR)publisher_with_id.py $(PUB_A_ID) --host $(HOST) \
	    --port $(PORT) --count $(PUB_COUNT) --interval $(PUB_INTERVAL) \
	    --log-level $(LOG_LEVEL) > $(LOG_A) 2>&1 & echo $$! > $(PID_A)
	@echo ">> publisher $(PUB_A_ID) 已启动 (pid $$(cat $(PID_A)))"
	@sleep 0.3
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) $(SELF_DIR)publisher_with_id.py $(PUB_B_ID) --host $(HOST) \
	    --port $(PORT) --count $(PUB_COUNT) --interval $(PUB_INTERVAL) \
	    --log-level $(LOG_LEVEL) > $(LOG_B) 2>&1 & echo $$! > $(PID_B)
	@echo ">> publisher $(PUB_B_ID) 已启动 (pid $$(cat $(PID_B)))"
	@echo "   观察: make logs    停止: make stop"

stop: ## 停止全部后台进程
	@for kv in "server:$(PID_SRV)" "subscriber:$(PID_SUB)" "pubA:$(PID_A)" "pubB:$(PID_B)"; do \
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
	@for kv in "server:$(PID_SRV)" "subscriber:$(PID_SUB)" "pub-A:$(PID_A)" "pub-B:$(PID_B)"; do \
	  name=$${kv%%:*}; pidf=$${kv#*:}; \
	  if [ -f "$$pidf" ]; then \
	    pid=$$(cat "$$pidf"); \
	    if kill -0 "$$pid" 2>/dev/null; then echo "$$name: 运行中 (pid $$pid)"; \
	    else echo "$$name: 未运行 (残留 pid $$pid)"; fi; \
	  else echo "$$name: 未启动"; fi; \
	done

logs: ## 实时 tail 全部日志
	@echo "(Ctrl+C 退出查看，进程继续运行)"
	@tail -F $(LOG_SRV) $(LOG_SUB) $(LOG_A) $(LOG_B) 2>/dev/null

logs-sub: ## 只看 subscriber 日志
	@tail -F $(LOG_SUB) 2>/dev/null

# ---- 端到端冒烟 ---------------------------------------------------------

smoke: ## 冒烟测试：启动全部 → 交错发布 → 验证 subscriber 入站
	@echo "=== 多发布者 / 单订阅者 冒烟 ==="
	@$(MAKE) --no-print-directory start
	@echo "  等待 publisher 完成 ..."
	@sleep $$(echo "$(PUB_COUNT) * $(PUB_INTERVAL) + 2" | bc -l | cut -d. -f1) 2>/dev/null \
	  || sleep $$(($(PUB_COUNT) * 1 + 2))
	@for kv in "pub-A:$(PID_A)" "pub-B:$(PID_B)"; do \
	  pidf=$${kv#*:}; \
	  if [ -f "$$pidf" ]; then \
	    pid=$$(cat "$$pidf"); \
	    kill -0 "$$pid" 2>/dev/null || echo "$${kv%%:*}: 已完成"; \
	  fi; done
	@RECEIVED=$$(grep -c "subscriber=$(SUB_ID)" $(LOG_SUB) 2>/dev/null || echo 0); \
	 FROM_A=$$(grep -c "from.*$(PUB_A_ID)" $(LOG_SUB) 2>/dev/null || echo 0); \
	 FROM_B=$$(grep -c "from.*$(PUB_B_ID)" $(LOG_SUB) 2>/dev/null || echo 0); \
	 echo "=== subscriber 收到: 总计=$$RECEIVED 条 (from $(PUB_A_ID)=$$FROM_A, from $(PUB_B_ID)=$$FROM_B) ==="
	@$(MAKE) --no-print-directory stop

# ---- 清理 ---------------------------------------------------------------

clean: stop
	@rm -f $(PID_SRV) $(PID_SUB) $(PID_A) $(PID_B) \
	       $(LOG_SRV) $(LOG_SUB) $(LOG_A) $(LOG_B)
	@echo ">> 已清理 pid/log 产物"
