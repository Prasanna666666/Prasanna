.PHONY: install lint format type test check
install:
	pip install -e ".[ui,dev]"
lint:
	ruff check .
format:
	ruff format .
type:
	mypy src
test:
	pytest -q
check: lint type test
