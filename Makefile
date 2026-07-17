.PHONY: check test validate

check:
	python -m ruff check .
	PYTHONPATH=src python -m pytest
	PYTHONPATH=src python -m decision_agent_bench validate-specs
	PYTHONPATH=src python -m decision_agent_bench generate-world /tmp/decision-agent-bench-ci --overwrite
	PYTHONPATH=src python -m decision_agent_bench validate-world /tmp/decision-agent-bench-ci/world.sqlite

test:
	PYTHONPATH=src python -m pytest

validate:
	PYTHONPATH=src python -m decision_agent_bench validate-specs
