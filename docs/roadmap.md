# Staged roadmap

The original calendar is treated as a sequence of evidence-bearing releases. Each milestone gets its own reviewed commit; result-affecting changes after a release require a task-version or changelog entry.

## Milestone 0 — Design foundation

**Status:** complete in `v0.0.1`.

**Exit evidence:** research questions, architecture, scoring methodology, failure taxonomy, first 25 task contracts, repository standards, CI, and schema validation.

## Milestone 1 — Synthetic retail environment

**Status:** complete in `v0.0.2`.

Build a seeded company generator, relational schema, policies, documents, transaction histories, demand process, inventory and vendor constraints, action ledger, and economic outcome simulator.

**Exit evidence:** invariant tests, deterministic fixture hashes, data cards, provenance manifest, and a complete world regenerated from one command.

## Milestone 2 — Executable benchmark v0.1

**Status:** complete in `v0.1.0`.

Implement the 25 task families as Inspect AI tasks. Add SQL, analytics, forecasting, retrieval, communication, approval, and state-changing tools. Implement a single tool-using agent and planner-executor baseline.

**Exit evidence:** deterministic graders, tested oracles, failure injection, mock-model end-to-end tests, task cards, and pinned Docker execution.

## Milestone 3 — Reproducible experiments

**Status:** in progress. The immutable planning, cost-gated launcher, sanitized analysis,
uncertainty, paired-robustness, and leaderboard pipeline are implemented; paid multi-model runs are
pending current model selection and explicit cost authorization.

Run at least three model families with matched budgets and repeated trials. Analyze task success, regret, safety, robustness, calibration, efficiency, recovery, evidence quality, and variability.

**Exit evidence:** immutable run manifests, sanitized raw logs, reproducible analysis, confidence intervals, leaderboard, and a technical article.

## Milestone 4 — Research expansion

**Status:** in progress. Four advanced architectures, two prompt ablations, a 100-instance/200-
sample registered expansion, seed-level contract checks, and preregistered comparisons are
implemented. Full ablation runs, human agreement, and error-matrix analysis await model execution.

Add independent-verifier, multi-agent, memory-and-feedback, and corrupted-context baselines. Expand to 100–200 calibrated instances or task families based on empirical coverage gaps. Conduct ablations and human agreement studies.

**Exit evidence:** preregistered hypotheses, robustness matrices, error taxonomy analysis, judge-versus-deterministic comparison, and draft technical report.

## Milestone 5 — Public research release

**Status:** in progress. The interactive demo, technical report draft, three article drafts,
presentation deck, citation/archive metadata, blinded annotation workflow, leaderboard governance,
external reproduction protocol, and current Inspect Evals registration package are implemented.
Public repository identity, paid empirical runs, human ratings, independent reproduction, arXiv,
DOI, release tag, and accepted register entry remain external evidence gates.

Ship the interactive demo, archival dataset release, reproducible Docker images, technical report or preprint, three research-oriented articles, presentation materials, contributor onboarding, and upstream contribution packages.

**Exit evidence:** tagged release, DOI or archival identifier, public leaderboard governance, security review, external reproduction, and Inspect Evals register proposal when eligibility is established.

## Commit policy

- Commit only a complete, verified milestone or a coherent reviewable slice within a large milestone.
- Use imperative subjects and explain result-affecting decisions in commit bodies.
- Never rewrite published benchmark results; issue a new version and correction note.
- Do not push secrets, provider responses containing sensitive data, or unreviewed large artifacts.
