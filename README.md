# DecisionAgentBench

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](https://www.python.org/)

DecisionAgentBench is an open benchmark for measuring how reliably AI agents make consequential, long-horizon business decisions. It evaluates not only whether an agent reaches an answer, but whether the decision is economically sound, policy-compliant, robust to corrupted context and tool failures, calibrated, efficient, and supported by valid evidence.

The first domain is a fully synthetic convenience-retail company. No proprietary company data, policies, or systems are used.

> **Project status:** executable benchmark v0.1. The first 25 task families, paired clean and perturbed variants, deterministic synthetic company, Inspect integration, two reference baselines, and multidimensional graders are implemented. Multi-model empirical results are the next milestone; no model-performance claims have been made.

## Why this benchmark

Task-success rate can conceal costly or unsafe behavior. An agent may reach the nominal goal while destroying margin, violating an approval limit, trusting injected instructions, or citing evidence that does not support its decision. DecisionAgentBench makes those failures measurable.

The benchmark is built around five principles:

1. **Consequential outcomes:** decisions change simulated revenue, margin, service levels, or risk.
2. **Process-aware evaluation:** policy compliance, evidence use, recovery, and tool behavior matter.
3. **Deterministic grading first:** executable state and economic outcomes take priority over model judges.
4. **Controlled perturbations:** the same underlying task can be tested under missing data, failures, and adversarial context.
5. **Reproducible comparisons:** task versions, seeds, environments, model settings, and repeated runs are recorded.

## Benchmark v0.1

- One synthetic convenience-retail domain
- 25 task families spanning diagnosis, assortment, promotion, fraud, recovery, safety, and long-horizon execution
- Single-agent and planner-executor baselines
- Inspect AI integration
- Deterministic graders and a public failure taxonomy
- 25 clean and 25 controlled-perturbation samples
- Nine deterministic score outputs plus a public failure taxonomy
- Repeated multi-model runs and the benchmark report are planned for the next milestone

## Repository map

```text
decision-agent-bench/
├── data/task_specs/          # Versioned benchmark task contracts
├── docs/                     # Protocol, taxonomy, research design, and task catalog
├── src/decision_agent_bench/ # Python package
└── tests/                    # Fast deterministic checks
```

## Development setup

Create an isolated Python 3.11+ environment before installing the benchmark:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
python -m decision_agent_bench validate-specs
python -m decision_agent_bench verify-reference
```

Generate and validate the deterministic synthetic company:

```bash
python -m decision_agent_bench generate-world data/generated/reference
python -m decision_agent_bench validate-world data/generated/reference/world.sqlite
```

Generated worlds are intentionally excluded from source control. Their manifest records the complete generator configuration, table counts, schema version, and a logical content hash.

Run one category with the single-agent baseline:

```bash
inspect eval src/decision_agent_bench/evals/task.py@decision_agent_bench \
  --model openai/<model-name> \
  -T category=sales_diagnosis \
  -T variant=both \
  -T baseline=single_agent
```

Set `baseline=planner_executor` for the two-stage reference baseline. Provider credentials are read by Inspect; never commit them. The [benchmark protocol](docs/benchmark-protocol.md) defines variants, budgets, output fields, scoring, and reporting requirements.

For a dependency-locked reproduction check:

```bash
docker build --tag decision-agent-bench:0.1.0 .
docker run --rm decision-agent-bench:0.1.0
```

See [the research design](docs/research-design.md), [the first 25 tasks](docs/task-catalog.md), [the failure taxonomy](docs/failure-taxonomy.md), [the synthetic-data card](docs/data-card.md), and [the staged roadmap](docs/roadmap.md).

## Contributing

The project welcomes evaluation design, simulation, safety, statistics, and documentation contributions. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a change. Please do not submit real employer data, confidential policies, or proprietary prompts.

## License

Code and original documentation are released under the [MIT License](LICENSE). Generated benchmark datasets will carry explicit provenance and license metadata before their first public release.
