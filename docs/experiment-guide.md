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
its SHA-256 check. A publishable plan also requires a clean Git working tree; development plans
record the dirty state but remain ineligible as release evidence.

## 3. Execute with an explicit cost gate

```bash
decision-agent-bench run-experiment runs/<run-id>/manifest.json \
  --execute --acknowledge-costs
```

Inspect model API request bodies are not logged. Per-cell stdout and stderr tails are credential-
redacted before the execution report is written. The runner stops after the first failed cell so a
bad credential, model ID, or rate limit does not multiply costs. Re-running the same manifest
preserves the failed attempt, retries that cell, and skips cells already marked successful. A
completed manifest cannot be executed again.

## 4. Analyze and publish

```bash
decision-agent-bench analyze-results runs/<run-id>/logs results/generated/<run-id> \
  --manifest runs/<run-id>/manifest.json
```

The analyzer emits:

- `samples.sanitized.jsonl`: scores and resource telemetry without prompts, targets, transcripts,
  tool results, temporary paths, or raw provider payloads;
- `summary.json` and `summary.csv`: means, sample standard deviations, task-family cluster-bootstrap
  intervals, Wilson safety intervals, and calibration diagnostics by model, baseline, and variant;
- `paired-effects.csv`: clean-to-perturbed score and resource deltas with family-cluster intervals;
- `calibration.csv`: fixed-bin confidence, accuracy, and absolute-gap data;
- `failure-counts.csv`: public taxonomy counts;
- `robustness-matrix.csv` and `failure-matrix.csv`: category/perturbation outcomes and
  model-baseline-variant error profiles;
- `leaderboard.md`: publishable runs only, ranked by composite score; and
- `analysis-manifest.json`: SHA-256 and byte-size evidence for every source log and generated
  artifact, the immutable experiment-manifest identity, coverage, and sanitization provenance.

The analyzer refuses to mix a new run into a non-empty output directory and verifies that source
logs did not change during analysis. Verify a downloaded shareable bundle without raw logs:

```bash
decision-agent-bench verify-analysis results/generated/<run-id>
```

For a full local provenance check, require the exact source logs and experiment manifest:

```bash
decision-agent-bench verify-analysis results/generated/<run-id> \
  --logs runs/<run-id>/logs \
  --manifest runs/<run-id>/manifest.json \
  --require-sources
```

The first form proves that the published files match their content-addressed manifest. The strict
form also proves that the bundle was derived from the declared complete raw-log set and content-
hashed experiment plan. Any missing, added, or changed file fails verification.

The analysis manifest also counts successful and failed source logs so operational retries remain
visible in a public run card.

Clean and perturbed samples are paired by run, model, baseline, seeded instance, and epoch. The
paired robustness effect is reported as perturbed minus clean for all score dimensions, tool calls,
tokens, and latency. Reliability is computed across repeated epochs of the same instance. The
analyzer resamples whole task families because four v0.2 instances from one family are not
independent concepts. See the [statistical analysis protocol](statistical-analysis.md).

The leaderboard requires a verified immutable manifest and complete coverage of every publishable
cell. Partial runs remain useful diagnostics but are excluded from ranking. Confidence intervals are
descriptive and should not be treated as proof of model superiority without a preregistered
comparison and multiplicity-aware analysis.
