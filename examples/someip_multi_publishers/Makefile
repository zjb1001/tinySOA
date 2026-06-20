# Makefile —— 管理 SOME/IP 多传感器发布者 + 聚合订阅者演示的启动与退出。
#
# 本文件位于: tinySOA/examples/someip_multi_publishers/Makefile
# tinysoa + someip(pysomeip) 从源码解析，无需 pip 安装。
#
# 常用：
#   make                 = make help
#   make start           = 后台启动 3 传感器 + aggregator
#   make stop            = 停止全部后台进程
#   make status          = 查看进程状态
#   make logs            = 实时 tail 全部日志
#   make logs-agg        = 只看 aggregator 日志
#   make smoke           = bounded 冒烟 (每传感器 N 条，聚合后退出)
#   make tmux            = tmux 四窗格可视化
#   make clean           = 停止进程并清理产物

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
PYTHONPATH  := $(TINYSOA_DIR)/src:$(TINYSOA_DIR)/third_party/pysomeip/src
PYTHON      ?= python3

# ---- 可调参数 -----------------------------------------------------------
LOG_LEVEL     ?= INFO
SMOKE_COUNT   ?= 20     # 每个传感器的采样数
SMOKE_INTERVAL ?= 0.3
SMOKE_TIMEOUT  ?= 45    # aggregator 最长等待时间 (WSL2 上 SD 可能不投递)
AGG_PORT      ?= 30510
AGG_COUNT     ?= 9      # aggregator 停止前累积的总读数

# ---- 产物路径 -----------------------------------------------------------
PID_TEMP := $(SELF_DIR).temp.pid
PID_HUMID:= $(SELF_DIR).humid.pid
PID_PRESS:= $(SELF_DIR).press.pid
PID_AGG  := $(SELF_DIR).agg.pid
LOG_TEMP := $(SELF_DIR).temp.log
LOG_HUMID:= $(SELF_DIR).humid.log
LOG_PRESS:= $(SELF_DIR).press.log
LOG_AGG  := $(SELF_DIR).agg.log

.PHONY: help start stop status logs logs-agg logs-pub smoke tmux tmux-kill clean

help: ## 显示帮助
	@echo "SOME/IP 多传感器发布者 + 聚合订阅者 —— Makefile"
	@echo ""
	@echo "  make start           后台启动全部 (3 传感器 + aggregator)"
	@echo "  make stop            停止全部后台进程"
	@echo "  make status          查看进程状态"
	@echo "  make logs            实时 tail 全部日志"
	@echo "  make logs-agg        只看 aggregator 日志"
	@echo "  make logs-pub        只看传感器日志 (3 个)"
	@echo "  make smoke           bounded 冒烟：每传感器 $(SMOKE_COUNT) 次采样 → 聚合退出"
	@echo "  make tmux            tmux 四窗格可视化"
	@echo "  make tmux-kill        关闭 tmux 会话"
	@echo "  make clean            停止进程并删除产物"
	@echo ""
	@echo "  可调:  LOG_LEVEL=$(LOG_LEVEL) SMOKE_COUNT=$(SMOKE_COUNT)"
	@echo "         SMOKE_INTERVAL=$(SMOKE_INTERVAL) AGG_COUNT=$(AGG_COUNT)"
	@echo "  PYTHON:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

# ---- 后台常驻 -----------------------------------------------------------

start: stop ## 后台启动 3 传感器 + aggregator (常驻)
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) publisher1_temperature.py --log-level $(LOG_LEVEL) \
	    > $(LOG_TEMP) 2>&1 & echo $$! > $(PID_TEMP)
	@echo ">> temperature sensor 已启动 (pid $$(cat $(PID_TEMP)))，日志 $(LOG_TEMP)"
	@sleep 0.3
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) publisher2_humidity.py --log-level $(LOG_LEVEL) \
	    > $(LOG_HUMID) 2>&1 & echo $$! > $(PID_HUMID)
	@echo ">> humidity sensor    已启动 (pid $$(cat $(PID_HUMID)))，日志 $(LOG_HUMID)"
	@sleep 0.3
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) publisher3_pressure.py --log-level $(LOG_LEVEL) \
	    > $(LOG_PRESS) 2>&1 & echo $$! > $(PID_PRESS)
	@echo ">> pressure sensor    已启动 (pid $$(cat $(PID_PRESS)))，日志 $(LOG_PRESS)"
	@sleep 1.0
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) subscriber_aggregator.py --port $(AGG_PORT) \
	    --log-level $(LOG_LEVEL) > $(LOG_AGG) 2>&1 & echo $$! > $(PID_AGG)
	@echo ">> aggregator         已启动 (pid $$(cat $(PID_AGG)))，日志 $(LOG_AGG)"
	@echo "   SD 收敛需 ~5s；观察: make logs    停止: make stop"

stop: ## 停止全部后台进程 (先 INT，再 TERM 兜底)
	@for kv in "temp:$(PID_TEMP)" "humid:$(PID_HUMID)" "press:$(PID_PRESS)" "agg:$(PID_AGG)"; do \
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
	@for kv in "temperature:$(PID_TEMP)" "humidity:$(PID_HUMID)" "pressure:$(PID_PRESS)" "aggregator:$(PID_AGG)"; do \
	  name=$${kv%%:*}; pidf=$${kv#*:}; \
	  if [ -f "$$pidf" ]; then \
	    pid=$$(cat "$$pidf"); \
	    if kill -0 "$$pid" 2>/dev/null; then echo "$$name: 运行中 (pid $$pid)"; \
	    else echo "$$name: 未运行 (残留 pid $$pid)"; fi; \
	  else echo "$$name: 未启动"; fi; \
	done

logs: ## 实时 tail 全部日志
	@echo "(Ctrl+C 退出查看，进程继续运行)"
	@tail -F $(LOG_TEMP) $(LOG_HUMID) $(LOG_PRESS) $(LOG_AGG) 2>/dev/null

logs-agg: ## 只看 aggregator 日志
	@tail -F $(LOG_AGG) 2>/dev/null

logs-pub: ## 只看传感器日志
	@tail -F $(LOG_TEMP) $(LOG_HUMID) $(LOG_PRESS) 2>/dev/null

# ---- Bounded 冒烟 -------------------------------------------------------

smoke: ## bounded 冒烟 (每传感器 N 条，聚合收集)
	@echo "=== SOME/IP 传感器冒烟 ==="
	@echo "  每传感器 $(SMOKE_COUNT) 次采样, aggregator 收到 $(AGG_COUNT) 条后退出"
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) publisher1_temperature.py --count $(SMOKE_COUNT) \
	    --interval $(SMOKE_INTERVAL) --log-level $(LOG_LEVEL) \
	    > $(LOG_TEMP) 2>&1 & echo $$! > $(PID_TEMP)
	@sleep 0.3
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) publisher2_humidity.py --count $(SMOKE_COUNT) \
	    --interval $(SMOKE_INTERVAL) --log-level $(LOG_LEVEL) \
	    > $(LOG_HUMID) 2>&1 & echo $$! > $(PID_HUMID)
	@sleep 0.3
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  exec $(PYTHON) publisher3_pressure.py --count $(SMOKE_COUNT) \
	    --interval $(SMOKE_INTERVAL) --log-level $(LOG_LEVEL) \
	    > $(LOG_PRESS) 2>&1 & echo $$! > $(PID_PRESS)
	@sleep 2.0
	@cd $(SELF_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  timeout $(SMOKE_TIMEOUT) $(PYTHON) subscriber_aggregator.py --port $(AGG_PORT) --count $(AGG_COUNT) \
	    --log-level $(LOG_LEVEL) > $(LOG_AGG) 2>&1 || true; AGGEXIT=$$?
	@sleep 0.5
	@TOTAL=$$(grep -c "received " $(LOG_AGG) 2>/dev/null || echo 0); \
	 echo "=== 冒烟完成: aggregator 收到 $$TOTAL 条 (要求 >= $(AGG_COUNT)) ==="; \
	 echo "   查看: head -20 $(LOG_AGG)"
	@$(MAKE) --no-print-directory stop

# ---- tmux ---------------------------------------------------------------

tmux: ## tmux 四窗格可视化 (上: aggregator, 下: temp | humid | pressure)
	@bash $(SELF_DIR)tmux_demo.sh

tmux-kill: ## 关闭 tmux 会话
	@tmux kill-session -t tinysoa-multisensor 2>/dev/null && echo ">> 已关闭" || echo ">> 无会话"

# ---- 清理 ---------------------------------------------------------------

clean: stop
	@rm -f $(PID_TEMP) $(PID_HUMID) $(PID_PRESS) $(PID_AGG) \
	       $(LOG_TEMP) $(LOG_HUMID) $(LOG_PRESS) $(LOG_AGG)
	@echo ">> 已清理 pid/log 产物"
