# Reproducible experiment guide

DecisionAgentBench separates benchmark implementation from paid model execution. The experiment
layer creates a content-hashed plan before any provider is contacted, applies the same sample-level
budgets to every model, and requires two explicit CLI flags before execution.

## 1. Configure

Copy `configs/experiments/v0.1.template.json`, replace the current model identifiers, review
provider pricing, set `cost_limit_usd`, and enable the intended models. The template names three
provider families without freezing model recommendations that will become stale. Credentials must
come from provider environment variables and are rejected in `model_args`.

Official v0.1 results require both baselines, both variants, all 25 task families, and at least
three repetitions. `configs/experiments/smoke.json` is deliberately limited and non-publishable.

## 2. Plan

```bash
decision-agent-bench plan-experiment my-experiment.json --output runs
decision-agent-bench run-experiment runs/<run-id>/manifest.json
```

The first command records the Git commit, task entrypoint, reference-world digest, Python and
Inspect versions, matched budgets, every grid cell, and the exact argument-vector command. The
second command is a dry run by default and prints those commands. Editing the manifest invalidates
its SHA-256 check.

## 3. Execute with an explicit cost gate

```bash
decision-agent-bench run-experiment runs/<run-id>/manifest.json \
  --execute --acknowledge-costs
```

Inspect model API request bodies are not logged. Per-cell stdout and stderr tails are credential-
redacted before the execution report is written. The runner stops after the first failed cell so a
bad credential, model ID, or rate limit does not multiply costs.

## 4. Analyze and publish

```bash
decision-agent-bench analyze-results runs/<run-id>/logs results/generated/<run-id> \
  --manifest runs/<run-id>/manifest.json
```

The analyzer emits:

- `samples.sanitized.jsonl`: scores and resource telemetry without prompts, targets, transcripts,
  tool results, temporary paths, or raw provider payloads;
- `summary.json` and `summary.csv`: means, sample standard deviations, and deterministic 95%
  bootstrap intervals by model, baseline, and variant;
- `failure-counts.csv`: public taxonomy counts;
- `leaderboard.md`: publishable runs only, ranked by composite score; and
- `analysis-manifest.json`: source-log and sanitization provenance.

Clean and perturbed samples are paired by model, baseline, task, and epoch. The paired robustness
effect is reported as perturbed minus clean composite score. Reliability is shown through repeated-
run variability; confidence intervals are descriptive and should not be treated as proof of model
superiority without a preregistered comparison and multiplicity-aware analysis.
