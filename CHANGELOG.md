# Changelog

All notable result-affecting changes to DecisionAgentBench will be documented here. The project uses semantic versioning for software and explicit versions for task contracts.

## [Unreleased]

### Added

- Tamper-evident experiment manifests and matched-budget Inspect command grids.
- Double-confirmed, cost-capped provider execution with isolated runtime state and redacted logs.
- Sanitized sample telemetry, deterministic bootstrap intervals, within-task reliability, paired
  robustness deltas, failure summaries, and publishable-only leaderboard generation.
- Independent-verifier, multi-agent, memory-and-feedback, and corrupted-context research baselines,
  plus no-policy and no-evidence prompt ablations.
- A v0.2 task registration with 100 seeded scenario instances, 200 paired evaluation samples, and a
  generated machine-readable instance catalog.
- A provider-free Gradio research lab for task exploration, deterministic decision scoring, and
  allow-listed reference-world inspection.
- Blinded annotation export, private re-identification keys, strict rating validation, Fleiss'
  kappa, and human/LLM-judge/deterministic agreement reports.
- A methods-complete technical report draft, three preregistered research article drafts, and an
  editable, speaker-noted research-talk deck.
- Citation and archive metadata, leaderboard governance, external reproduction, current Inspect
  Evals registration guidance, and an evidence-gated release checklist.
- Analysis schema 2.0: seeded-instance identity, correct 100-pair v0.2 matching,
  within-instance reliability, task-family cluster bootstrap intervals, Wilson safety intervals,
  calibration tables, paired resource effects, and manifest-completeness leaderboard gating.
- Resumable execution schema 2.0 preserves failed cell attempts, skips completed paid cells, and
  prevents a completed immutable plan from being executed twice.
- Release audit CLI, oracle-boundary and provenance checks, OpenVEX policy, CodeQL, Gitleaks,
  hash-locked dependency audit, and Dependabot coverage for Python, Actions, and Docker.
- Content-addressed analysis bundles bind every sanitized result artifact to exact source-log and
  experiment-manifest hashes, with an independent verifier and strict source-provenance mode.
- Whole-grid preflight reports sample, token, and dollar exposure; publishable execution requires
  clean-source planning, a whole-study ceiling, and acknowledgement of the exact planned amount.
- Deterministic archival release assembly binds packages, datasets, research artifacts, SBOM,
  vulnerability evidence, container identity, and admitted results under exact checksums.
- A provenance-documented, audit-checked 1280×640 project banner is ready for GitHub social preview
  and is preserved in archival release bundles.
- Release assembly now binds CycloneDX and `pip-audit` dependency inventories to the exact universal
  requirements lock and rejects empty, incomplete, duplicate, unexpected, or mismatched evidence.
- Independent release verification now recomputes benchmark claims, security inventories, current
  OpenVEX coverage, embedded analysis integrity, publishable-result state, and final-release gates;
  a self-consistently rehashed but semantically altered bundle fails verification.
- Publishable studies now require three distinct model families, and portable analysis bundles carry
  a sanitized study plan so independent verification can parse records and recompute coverage and
  release eligibility instead of trusting a self-declared publication flag.

## [0.1.0] - 2026-07-17

### Added

- Twenty-five executable Inspect task families with paired clean and controlled-perturbation
  samples across seven business-decision categories.
- Single-agent and planner-executor reference baselines with bounded SQL, retrieval, forecasting,
  inventory, approval, and policy-gated action tools.
- Deterministic multidimensional scoring for effectiveness, economic decision quality, safety,
  robustness, calibration, efficiency, recovery, explainability, and a gated composite.
- Public failure taxonomy, benchmark protocol, mock-model end-to-end tests, dependency lock, and
  non-root Docker reproduction check.
- Refund, payment-event, feed-health, competitor-price, inventory-lot, and recall evidence in the
  synthetic world to support the full v0.1 task set.

## [0.0.2] - 2026-07-17

### Added

- Deterministic synthetic retail world with stores, products, customers, inventory, sales,
  promotions, vendor constraints, documents, approvals, and an action ledger.
- Reproducible generator CLI, canonical content hashing, published reference manifest, and data card.
- Read-only SQL, document retrieval, forecasting, inventory recommendation, approval, and
  policy-gated price-action APIs.
- Integrity, reproducibility, tool-safety, provenance, and authorization tests.

## [0.0.1] - 2026-07-17

### Added

- Initial research design, evaluation methodology, and failure taxonomy.
- Machine-readable contracts for the first 25 task families.
- Task-spec validation CLI, tests, packaging, and continuous integration.
- Open-source contribution, security, licensing, and release roadmap documents.
