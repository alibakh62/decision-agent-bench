# Changelog

All notable result-affecting changes to DecisionAgentBench will be documented here. The project uses semantic versioning for software and explicit versions for task contracts.

## [Unreleased]

## [0.1.1] - 2026-07-21

### Fixed

- Restored clean-runner CI compatibility without changing generated worlds or oracle outcomes,
  pinned the verified Ruff version so release checks do not drift as new lint rules are published,
  and upgraded the workflow to the supported Node 24-based GitHub actions.

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
