ifneq ($(OS),Windows_NT)
	# On Unix-based systems, use ANSI codes
	BLUE = \033[36m
	BOLD_BLUE = \033[1;36m
	BOLD_GREEN = \033[1;32m
	RED = \033[31m
	YELLOW = \033[33m
	BOLD = \033[1m
	NC = \033[0m
endif

.PHONY: help setup format lint test coverage
.DEFAULT_GOAL := help

PYTEST_ARGS ?= --numprocesses=auto

escape = $(subst $$,\$$,$(subst ",\",$(subst ',\',$(1))))

define exec
	@printf '$(BOLD_BLUE)%s$(NC)\n' '$(call escape,$(1))'
	@$(1)
endef

help:
	@echo "$(BOLD_GREEN)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?# .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?# "}; \
		{printf "  $(BOLD_BLUE)%-20s$(NC) %s\n", $$1, $$2}'

setup:  # Setup the development environment
	$(call exec,uv sync)

format:  # Format code
	$(call exec,uv run ruff format)
	$(call exec,uv run ruff check --fix)
	$(call exec,uv run taplo fmt)
	$(call exec,uv run mdformat $$(git ls-files *.md))
	$(call exec,uv run yamlfix $$(git ls-files *.yml *.yaml))

lint:  # Lint code
	$(call exec,uv run ruff format --check)
	$(call exec,uv run ruff check)
	$(call exec,uv run ty check --no-progress)
	$(call exec,uv run taplo fmt --check)
	$(call exec,uv run mdformat --check $$(git ls-files *.md))
	$(call exec,uv run yamlfix --check $$(git ls-files *.yml *.yaml))

test:  # Run tests
	$(call exec,uv run pytest -v tests/ $(PYTEST_ARGS))

coverage:  # Run tests with coverage
	$(MAKE) test PYTEST_ARGS="--cov=git_hunk --cov-report=term-missing"
