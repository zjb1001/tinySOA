# Makefile —— 本地 pub/sub 拓扑矩阵（1p→1s / 1p→Ns / Np→1s）。
#
# 所有场景使用 InMemoryEventBus，单进程、确定性、无网络。
#
# 常用：
#   make                         = help
#   make run                     = 跑全部拓扑
#   make run SCENARIO=1v1
#   make run SCENARIO=1vn SUBSCRIBERS=5
#   make run SCENARIO=nv1 PUBLISHERS=3
#   make smoke                   = 同 run all
#   make clean

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
PYTHONPATH  := $(TINYSOA_DIR):$(TINYSOA_DIR)/src:$(TINYSOA_DIR)/third_party/pysomeip/src
PYTHON      ?= $(shell [ -x "$(TINYSOA_DIR)/.venv/bin/python" ] && echo "$(TINYSOA_DIR)/.venv/bin/python" || echo python3)
MODULE      := examples.local_pubsub_topologies

SCENARIO    ?= all
COUNT       ?= 3
SUBSCRIBERS ?= 3
PUBLISHERS  ?= 3
LOG_LEVEL   ?= INFO

.PHONY: help run smoke clean

help: ## 显示帮助
	@echo "local_pubsub_topologies —— 1p→1s / 1p→Ns / Np→1s 应用观察"
	@echo ""
	@echo "  make run                              跑全部拓扑"
	@echo "  make run SCENARIO=1v1                 1 pub → 1 sub"
	@echo "  make run SCENARIO=1vn SUBSCRIBERS=5   1 pub → N subs"
	@echo "  make run SCENARIO=nv1 PUBLISHERS=3    N pubs → 1 sub"
	@echo "  make smoke                            同 run all"
	@echo "  make clean"
	@echo ""
	@echo "  COUNT=$(COUNT) SUBSCRIBERS=$(SUBSCRIBERS) PUBLISHERS=$(PUBLISHERS)"
	@echo "  PYTHON:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

run: ## 跑指定拓扑场景
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) -m $(MODULE).app \
	  --scenario $(SCENARIO) --count $(COUNT) \
	  --subscribers $(SUBSCRIBERS) --publishers $(PUBLISHERS) \
	  --log-level $(LOG_LEVEL)

smoke: run ## 冒烟（同 run all）

clean: ## 清理日志产物
	@rm -f $(SELF_DIR)*.log $(SELF_DIR)*.pid
	@echo ">> local_pubsub_topologies cleaned"
