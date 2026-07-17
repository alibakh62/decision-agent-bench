# DecisionAgentBench

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](https://www.python.org/)

DecisionAgentBench is an open benchmark for measuring how reliably AI agents make consequential, long-horizon business decisions. It evaluates not only whether an agent reaches an answer, but whether the decision is economically sound, policy-compliant, robust to corrupted context and tool failures, calibrated, efficient, and supported by valid evidence.

The first domain is a fully synthetic convenience-retail company. No proprietary company data, policies, or systems are used.

> **Project status:** public research release candidate. The executable v0.1 benchmark, v0.2
> research expansion, six architectures, two ablations, reproducible experiment and analysis
> pipeline, blinded agreement tooling, interactive lab, report draft, and public governance are
> implemented. Multi-model runs, human ratings, an external reproduction, archival DOI, and upstream
> registration remain evidence gates; no frontier-model performance claims have been made.

The research track also includes a registered v0.2 expansion with 100 seeded instances (200 paired
samples), four advanced architectures, and two prompt ablations. These are tested research
infrastructure, not empirical performance claims.

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
├── articles/                 # Three research-oriented article drafts
├── data/task_specs/          # Versioned benchmark task contracts
├── docs/                     # Protocol, taxonomy, governance, and task catalog
├── report/                   # Technical report source
├── src/decision_agent_bench/ # Python package
├── talk/                     # Editable research-talk deck
└── tests/                    # Fast deterministic checks
```

## Development setup

Create an isolated Python 3.11+ environment before installing the benchmark:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,demo]"
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

For the expanded research task, select
`src/decision_agent_bench/evals/task.py@decision_agent_bench_v0_2`. See the
[v0.2 expansion](docs/v0.2-expansion.md) and [research baseline](docs/research-baselines.md)
protocols before comparing architectures.

Launch the local, provider-free research lab:

```bash
decision-agent-bench demo --host 127.0.0.1 --port 7860
```

The task explorer shows all registered paired instances. The decision scorer uses the real
deterministic grader with simulated evidence lineage, and the reference-world tab exposes only
allow-listed read-only views. The demo has no provider calls, arbitrary SQL, state-changing actions,
oracle fields, or public sharing tunnel.

For a dependency-locked reproduction check:

```bash
docker build --tag decision-agent-bench:0.1.0 .
docker run --rm decision-agent-bench:0.1.0
```

Plan a matched-budget experiment without contacting a model provider:

```bash
decision-agent-bench plan-experiment configs/experiments/smoke.json --output runs
decision-agent-bench run-experiment runs/<run-id>/manifest.json
```

Execution requires both `--execute` and `--acknowledge-costs`. A publishable configuration is
rejected unless it covers all tasks, both variants, both baselines, at least three repetitions, and
an explicit per-sample cost cap. See the [experiment guide](docs/experiment-guide.md).

After analysis, verify the shareable result bundle on its own or bind it back to the exact raw logs
and immutable experiment manifest:

```bash
decision-agent-bench verify-analysis results/generated/<run-id>
decision-agent-bench verify-analysis results/generated/<run-id> \
  --logs runs/<run-id>/logs --manifest runs/<run-id>/manifest.json --require-sources
```

Export a blinded human/LLM-judge study after a successful run:

```bash
decision-agent-bench export-annotations runs/<run-id>/logs studies/<study-id>
decision-agent-bench agreement-report \
  studies/<study-id>/ratings-complete.csv \
  studies/<study-id>/annotation-key.private.jsonl \
  studies/<study-id>/agreement.json
```

The [annotation protocol](docs/annotation-protocol.md) defines blinding, rating anchors, Fleiss'
kappa, majority labels, and three-way confusion comparisons.

## Research artifacts

- [Technical report draft](report/technical-report.md)
- [Why task success hides catastrophic failures](articles/01-task-success-hides-catastrophic-failures.md)
- [Measuring recovery after tool errors](articles/02-measuring-recovery-after-tool-errors.md)
- [Business regret and judge disagreement](articles/03-business-regret-and-judge-disagreement.md)
- [Editable research-talk deck](talk/decision-agent-bench-research-talk.pptx)
- [Leaderboard governance](docs/leaderboard-governance.md) and [external reproduction](docs/external-reproduction.md)
- [Current Inspect Evals registration package](docs/inspect-evals-registration.md)

See also [the research design](docs/research-design.md), [the first 25 tasks](docs/task-catalog.md),
[the failure taxonomy](docs/failure-taxonomy.md), [the synthetic-data card](docs/data-card.md),
[the statistical analysis protocol](docs/statistical-analysis.md), [the staged roadmap](docs/roadmap.md),
and the [public-release checklist](docs/release-checklist.md).

Before a release, run `make audit` and review the [security model](docs/security-model.md). The audit
distinguishes failed controls from external evidence that is still pending.

## Contributing

The project welcomes evaluation design, simulation, safety, statistics, and documentation contributions. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a change. Please do not submit real employer data, confidential policies, or proprietary prompts.

## License

Code and original documentation are released under the [MIT License](LICENSE). Generated benchmark datasets will carry explicit provenance and license metadata before their first public release.
