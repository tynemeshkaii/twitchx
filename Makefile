.PHONY: run debug lint fmt test check push

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

push:
	git add .
	git commit -m "update $$(date '+%Y-%m-%d %H:%M')"
	git push
