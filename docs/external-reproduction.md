# External reproduction protocol

This checklist is for a researcher who did not author the benchmark. A successful reproduction
means a clean machine reconstructs the reference world, executes the published task protocol, and
regenerates reported tables from independently obtained model outputs.

## 1. Verify the source release

Clone the tagged release, confirm its Git tag and archival DOI, and record the commit. Build the
container from the repository root:

```bash
docker build --tag decision-agent-bench:<version> .
docker run --rm decision-agent-bench:<version>
```

The default container command verifies the logical reference-world hash. Also run `make check` in
an isolated Python 3.11 or 3.12 environment. Report the OS, architecture, Docker implementation,
Python version, and any deviation from the dependency lock.

## 2. Recreate the experiment

Copy the published experiment configuration and update only credential locations. Planning should
reproduce the same cell grid and budgets; the run ID may differ because the code/environment
metadata are newly recorded.

```bash
decision-agent-bench plan-experiment reproduction.json --output runs
decision-agent-bench run-experiment runs/<run-id>/manifest.json
```

Inspect the dry run before accepting provider cost. Execute only after confirming current model
availability and spending limits. If an exact hosted model snapshot is unavailable, stop calling
the run an exact reproduction and label it a model-update replication.

## 3. Regenerate analysis

```bash
decision-agent-bench analyze-results runs/<run-id>/logs results/reproduction \
  --manifest runs/<run-id>/manifest.json
```

Compare task coverage, failures, group means, paired robustness effects, and uncertainty intervals.
Do not expect bitwise-identical stochastic model outputs. Investigate whether differences exceed
the preregistered tolerance or materially change a conclusion.

## 4. Publish a reproduction card

Include source release and commit, environment digest, model IDs and dates, manifest hash, complete
and failed cells, deviations, results with uncertainty, and links to sanitized artifacts. Never
publish credentials, raw model API payloads, private annotation keys, or hidden oracle fields.

Open a GitHub discussion or issue with the reproduction card. Maintainers should link independent
reproductions—successful or not—from the relevant release and report.
