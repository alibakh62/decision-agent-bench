.PHONY: check test validate verify-reference docker-build docker-verify

check:
	python -m ruff check .
	PYTHONPATH=src python -m pytest
	PYTHONPATH=src python -m decision_agent_bench validate-specs
	PYTHONPATH=src python -m decision_agent_bench generate-world /tmp/decision-agent-bench-ci --overwrite
	PYTHONPATH=src python -m decision_agent_bench validate-world /tmp/decision-agent-bench-ci/world.sqlite
	PYTHONPATH=src python -m decision_agent_bench verify-reference

test:
	PYTHONPATH=src python -m pytest

validate:
	PYTHONPATH=src python -m decision_agent_bench validate-specs

verify-reference:
	PYTHONPATH=src python -m decision_agent_bench verify-reference

docker-build:
	docker build --tag decision-agent-bench:0.1.1 .

docker-verify:
	docker run --rm decision-agent-bench:0.1.1
