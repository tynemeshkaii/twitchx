.PHONY: run debug lint fmt test cov cov-html check check-linux preview push

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

# Linux (cloud sessions): pyobjc cannot be built there, so run the tools in a
# throwaway env with the project deps minus pyobjc. Ranges follow
# pyproject.toml; ruff and pyright are pinned to the uv.lock versions.
LINUX_PY := uv run --no-project --python 3.12 \
	--with "pytest>=9.0.2,<10" --with "pytest-asyncio>=1.3.0,<2" \
	--with "pytest-httpx>=0.35.0,<1" --with "pytest-cov>=7.1.0,<8" \
	--with "httpx>=0.27.0,<1" --with "curl-cffi>=0.14.0,<1" \
	--with "pillow>=11.0.0,<12" --with "websockets>=16,<17" \
	--with "pywebview>=5,<6"

check-linux:
	uvx ruff@0.15.6 check .
	$(LINUX_PY) --with pyright==1.1.408 python tools/pyright_linux.py
	$(LINUX_PY) python -m pytest tests/ -q -p no:cacheprovider

preview:
	@if command -v node >/dev/null 2>&1; then \
		node tools/ui_preview/build.js && node tools/ui_preview/shoot.js $(ARGS); \
	else \
		echo "node not found — skipping UI preview (install Node.js to use make preview)"; \
	fi

push:  # commits tracked files only: new files must be `git add`-ed explicitly
	git add -u
	git commit -m "update $$(date '+%Y-%m-%d %H:%M')" || true
	git push
