.PHONY: setup test

setup:
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -r requirements-dev.txt

test:
	./.venv/bin/pytest tests/ -v
