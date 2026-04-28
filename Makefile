.PHONY: run debug lint fmt test cov cov-html check push

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

cov:
	uv run pytest tests/ -v --cov=core --cov=ui --cov-report=term-missing

cov-html:
	uv run pytest tests/ -v --cov=core --cov=ui --cov-report=html

check: lint test

push:
	git add .
	git commit -m "update $$(date '+%Y-%m-%d %H:%M')" || true
	git push
