.PHONY: setup test eval lint

setup:
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -r requirements-dev.txt

test:
	./.venv/bin/pytest tests/ -v

eval:
	./.venv/bin/python scripts/eval_fixtures.py

lint:
	./.venv/bin/ruff check .
