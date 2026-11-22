# Makefile —— 本地拦截器 + Auth 示例（InMemoryEventBus，单进程）。
#
# 常用：
#   make                 = help
#   make run             = 跑全部场景
#   make run SCENARIO=unauthorized
#   make smoke           = 同 run
#   make clean           = 清理日志产物

.DEFAULT_GOAL := help
SHELL := /bin/bash

SELF_DIR    := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/
TINYSOA_DIR := $(abspath $(SELF_DIR)../..)
PYTHONPATH  := $(TINYSOA_DIR):$(TINYSOA_DIR)/src:$(TINYSOA_DIR)/third_party/pysomeip/src
PYTHON      ?= $(shell [ -x "$(TINYSOA_DIR)/.venv/bin/python" ] && echo "$(TINYSOA_DIR)/.venv/bin/python" || echo python3)
MODULE      := examples.local_interceptor_auth

SCENARIO   ?= all
LOG_LEVEL  ?= INFO

.PHONY: help run smoke clean

help: ## 显示帮助
	@echo "local_interceptor_auth —— 拦截器排序 + Auth 短路 + 异常传播"
	@echo ""
	@echo "  make run                         跑全部场景"
	@echo "  make run SCENARIO=unauthorized   只跑指定场景"
	@echo "  make smoke                       同 run"
	@echo "  make clean                       清理日志产物"
	@echo ""
	@echo "  SCENARIO=$(SCENARIO)  LOG_LEVEL=$(LOG_LEVEL)"
	@echo "  PYTHON:     $(PYTHON)"
	@echo "  PYTHONPATH: $(PYTHONPATH)"

run: ## 跑指定场景（默认 all）
	@cd $(TINYSOA_DIR) && PYTHONPATH=$(PYTHONPATH) \
	  $(PYTHON) -m $(MODULE).app --scenario $(SCENARIO) --log-level $(LOG_LEVEL)

smoke: run ## 冒烟（自包含）

clean: ## 清理日志产物
	@rm -f $(SELF_DIR)*.log $(SELF_DIR)*.pid
	@echo ">> local_interceptor_auth cleaned"
