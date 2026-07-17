.PHONY: check test validate

check:
	python -m ruff check .
	python -m pytest
	python -m decision_agent_bench validate-specs

test:
	python -m pytest

validate:
	python -m decision_agent_bench validate-specs
