IMAGE ?= decision-agent-bench:0.5.2

.PHONY: check test validate verify-reference audit audit-inspect demo docker-build docker-verify docker-audit

check:
	python -m ruff check .
	PYTHONPATH=src python -m pytest
	PYTHONPATH=src python -m decision_agent_bench validate-specs
	PYTHONPATH=src python -m decision_agent_bench generate-world /tmp/decision-agent-bench-ci --overwrite
	PYTHONPATH=src python -m decision_agent_bench validate-world /tmp/decision-agent-bench-ci/world.sqlite
	PYTHONPATH=src python -m decision_agent_bench verify-reference
	PYTHONPATH=src python -m decision_agent_bench verify-power results/design/v0.5-initial-power.json --design configs/power/v0.5-initial.json
	PYTHONPATH=src python -m decision_agent_bench verify-power results/design/v0.5-power.json --design configs/power/v0.5.json

test:
	PYTHONPATH=src python -m pytest

validate:
	PYTHONPATH=src python -m decision_agent_bench validate-specs

verify-reference:
	PYTHONPATH=src python -m decision_agent_bench verify-reference

audit:
	PYTHONPATH=src python -m decision_agent_bench audit-release --output build/release-audit.json

audit-inspect:
	PYTHONPATH=src python -m decision_agent_bench audit-inspect-registration

demo:
	PYTHONPATH=src python -m decision_agent_bench demo --host 127.0.0.1 --port 7860

docker-build:
	docker build --tag $(IMAGE) .

docker-verify:
	docker run --rm $(IMAGE)
	docker run --rm --entrypoint sh $(IMAGE) -c 'test "$$(id -u)" = "10001"'

docker-audit:
	PYTHONPATH=src python -m decision_agent_bench audit-release --container-image $(IMAGE)
