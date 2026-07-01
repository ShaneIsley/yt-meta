# yt-meta developer tasks. Requires `uv` (https://docs.astral.sh/uv/).
.PHONY: help test contract drift lint format check

help:                ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

test:                ## Run the fast offline suite (default; no network)
	uv run pytest

contract drift:      ## Detect YouTube shape drift via the LIVE contract suite (not CI-able)
	./scripts/check_shape_drift.sh

lint:                ## Lint with ruff
	uv run ruff check .

format:              ## Auto-format with ruff
	uv run ruff format .

check: lint test     ## Lint + offline tests (the pre-commit gate)
