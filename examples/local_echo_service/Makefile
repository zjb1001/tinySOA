# Makefile —— 本地 echo 服务（InMemoryEventBus，单进程）。
#
# 常用：
#   make            = help
#   make run        = 跑一次完整 demo
#   make smoke      = 同 run（自包含、无后台进程）
#   make clean      = 清理日志产物

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
PYTHONPATH  := $(TINYSOA_DIR):$(TINYSOA_DIR)/src:$(TINYSOA_DIR)/third_party/pysomeip/src
PYTHON      ?= $(shell [ -x "$(TINYSOA_DIR)/.venv/bin/python" ] && echo "$(TINYSOA_DIR)/.venv/bin/python" || echo python3)
MODULE      := examples.local_echo_service

.PHONY: help run smoke clean

help: ## 显示帮助
	@echo "local_echo_service —— InMemoryEventBus 单进程示例"
	@echo ""
	@echo "  make run     跑一次 echo 服务（方法调用 + 事件）"
	@echo "  make smoke   同 run"
	@echo "  make clean   清理日志产物"
	@echo ""
	@echo "  PYTHON:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

run: ## 跑一次 echo 服务
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) -m $(MODULE).app

smoke: run ## 冒烟（自包含）

clean: ## 清理日志产物
	@rm -f $(SELF_DIR)*.log $(SELF_DIR)*.pid
	@echo ">> local_echo_service cleaned"
