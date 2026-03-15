.PHONY: run debug lint fmt test check

run:
	uv run python main.py

debug:
	TWITCHX_DEBUG=1 uv run python main.py

lint:
	uv run ruff check .
	uv run pyright .

fmt:
	uv run ruff format .

test:
	uv run pytest tests/ -v

check: lint test
