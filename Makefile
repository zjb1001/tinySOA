# tinySOA — repository-level automation.
#
# Examples keep their own Makefile; run those with `make -C examples ...`.
# This file only exposes local CI/CD and agent-flow entry points.

.DEFAULT_GOAL := help
SHELL := /bin/bash

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= $(if $(wildcard $(ROOT)/.venv/bin/python),$(ROOT)/.venv/bin/python,python3)
ARGS ?=

.PHONY: help ci ci-advisory ci-strict ci-coverage test lint typecheck smoke \
        agent-flow agent-flow-dry-run release clean-agent-flow

help: ## 显示帮助
	@echo "tinySOA — 本地 CI / Agent Flow"
	@echo ""
	@echo "=== CI ==="
	@echo "  make ci                  pytest + ruff/black/mypy 全部阻断（默认）"
	@echo "  make ci-advisory         pytest 阻断，ruff/black/mypy 仅告警"
	@echo "  make ci-strict           make ci 的兼容别名"
	@echo "  make ci-coverage         pytest + coverage"
	@echo "  make test                只跑 pytest"
	@echo "  make lint                只跑 ruff + black"
	@echo "  make typecheck           只跑 mypy"
	@echo "  make smoke               跑 examples 稳定冒烟组"
	@echo ""
	@echo "=== Agent Flow (本地 issue/task -> PR) ==="
	@echo "  AGENT_CMD='<your agent>' make agent-flow ARGS=\"--issue 123\""
	@echo "  make agent-flow ARGS=\"--issue 123\"            实现 + CI + review（不推送）"
	@echo "  make agent-flow ARGS=\"--issue 123 --yes\"       推送并开 PR"
	@echo "  make agent-flow ARGS=\"--task '...' --title '...' --yes\""
	@echo "  make agent-flow ARGS=\"--issue 123 --dry-run\"   只打印计划"
	@echo "  make release ARGS=\"--version v0.3.0 --yes\"     跑 CI + 打 tag + GitHub Release"
	@echo "  make clean-agent-flow    清理 .agent-flow 运行产物和 worktree 元数据"
	@echo ""
	@echo "  PYTHON: $(PYTHON)"
	@echo "  文档:   docs/ci-cd.md, docs/agent-flow.md"

ci: ## pytest + lint/类型全部阻断（默认）
	@PYTHON="$(PYTHON)" bash "$(ROOT)/scripts/ci.sh"

ci-advisory: ## pytest 阻断，lint/类型仅告警
	@PYTHON="$(PYTHON)" bash "$(ROOT)/scripts/ci.sh" --advisory

ci-strict: ## make ci 的兼容别名
	@PYTHON="$(PYTHON)" bash "$(ROOT)/scripts/ci.sh" --strict

ci-coverage: ## pytest + coverage
	@PYTHON="$(PYTHON)" bash "$(ROOT)/scripts/ci.sh" --coverage

test: ## 只跑 pytest
	@PYTHON="$(PYTHON)" bash "$(ROOT)/scripts/ci.sh" --tests-only

lint: ## 只跑 ruff + black
	@PYTHON="$(PYTHON)" bash "$(ROOT)/scripts/ci.sh" --lint-only

typecheck: ## 只跑 mypy
	@PYTHON="$(PYTHON)" bash "$(ROOT)/scripts/ci.sh" --typecheck-only

smoke: ## examples 稳定冒烟组
	@PYTHON="$(PYTHON)" bash "$(ROOT)/scripts/ci.sh" --smoke-only

agent-flow: ## 本地 agent flow: issue/task -> worktree -> CI -> review -> PR
	@PYTHON="$(PYTHON)" bash "$(ROOT)/scripts/agent-flow.sh" $(ARGS)

agent-flow-dry-run: ## 只打印 agent flow 计划
	@PYTHON="$(PYTHON)" bash "$(ROOT)/scripts/agent-flow.sh" --dry-run $(ARGS)

release: ## 本地发布：CI + tag + GitHub Release
	@bash "$(ROOT)/scripts/release.sh" $(ARGS)

clean-agent-flow: ## 清理 .agent-flow 产物
	@rm -rf "$(ROOT)/.agent-flow"
	@git -C "$(ROOT)" worktree prune
	@echo ">> .agent-flow cleaned"
