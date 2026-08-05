# Changelog

All notable result-affecting changes to DecisionAgentBench will be documented here. The project uses semantic versioning for software and explicit versions for task contracts.

## [Unreleased]

## [0.7.0] - 2026-08-05

### Added

- Add a deterministic action-sensitive retail episode engine coupling purchase orders and delivery
  delays, lot inventory, shelf capacity, store-specific prices, promotions, demand and substitution,
  sales and lost sales, spoilage, returns, operational events, and cash across 14-to-180-day runs.
- Add bounded public SQL and typed state-changing actions while keeping simulator demand parameters,
  keyed random draws, and metadata evaluator-only.
- Add structured approval-required, requested, approved/rejected, resumed, and aborted events for
  high-stakes promotion decisions.
- Add normal, held-out supply, demand-shift, cold-chain, and mixed-stress regimes with heterogeneous
  stores, seasonality, shocks, exact same-seed replay, and a content-addressed reference manifest.
- Add random, fixed, reorder-point, newsvendor, pricing, and information-matched public policies plus
  a clearly leaderboard-ineligible privileged diagnostic policy.
- Add matched causal scenarios for replenishment, pricing, shelf allocation, and promotion approval,
  each requiring a later observable state and realized-outcome difference.
- Add conservation, accounting, inventory-flow, capacity, temporal, authorization, approval-state,
  deterministic replay, multi-week, multi-month, and stress-regime tests.
- Add a content-addressed public-source grounding and one-at-a-time sensitivity report with explicit
  synthetic-mechanism and external-validity boundaries.

### Changed

- Raise the transitive aiohttp floor to 3.14.3 and refresh the hash lock, removing the known
  advisories that caused the v0.6 dependency and release-audit checks to fail.

### Documentation

- Publish the v0.7 world contract, calibration interpretation, baseline information boundaries,
  data-card additions, security boundary, reproducibility commands, and release evidence.
- Keep discriminating tasks assigned to v0.8 and branching/human-time horizon validation assigned
  to v0.9; v0.7 makes no model leaderboard or general long-horizon claim.

## [0.6.0] - 2026-08-05

### Added

- Add a separate construct-valid task registration with 25 public typed construct definitions,
  world-derived answer functions, task-specific field contracts, and a machine-readable
  `show-constructs` command.
- Add claim-level semantic evidence validation, behavioral action and safety grading, independent
  regret/utility measures where applicable, non-compensatory score gates, and exact run-specific
  score breakdowns.
- Add a portable causal trace contract with deterministic root/tool/terminal spans, parent-child
  lineage, payload integrity hashes, capture-time secret minimization, and trace-completeness
  eligibility.
- Add adversarial validity fixtures covering keyword stuffing, paraphrase invariance, fabricated
  citations, evidence mutation, unsafe action intent, complete construct coverage, and public-target
  leakage.
- Add the v0.6 scoring protocol and custom-agent migration guide, and make the built-in finalizer
  and both LangGraph examples compatible with the typed contract.

### Changed

- Report per-sample calibration and robustness as null, retain Brier telemetry for group analysis,
  and make analysis schema 4.0 preserve metric applicability instead of coercing null to zero.
- Keep v0.1-v0.3 task and scorer behavior frozen for historical reproduction while selecting v0.6
  for current development-evaluation examples.

### Documentation

- Rebase the post-v0.5 release plan around an explicit v0.6 construct-valid scorer, v0.7
  closed-loop retail world, v0.8 discriminating task suite, v0.9 horizon validation, v0.10 external
  validation, and v0.11 empirical beta before stable v1 contracts.
- Preserve the completed v0.5 statistical and agent-integration work while clarifying that it does
  not close the measurement-validity or long-horizon gates.
- Incorporate the Google *Agent Quality* review by adding an outside-in score hierarchy, portable
  causal traces, operational-versus-quality observability, evaluator triangulation, context-rich
  review, and a governed feedback-to-regression loop to the v0.6-v0.10 gates.

## [0.5.7] - 2026-07-31

### Added

- Add a complete in-process LangGraph store assistant that runs independently on a simulated daily
  store snapshot and uploads directly into the Lab through a LangChain-tool/Inspect adapter.
- Add a complete FastAPI-based remote LangGraph replenishment service with a bounded HTTP tool
  broker that keeps every benchmark tool call inside the active Inspect sample.
- Add simulated recall and replenishment datasets, standalone CLIs, service endpoints, two detailed
  integration guides, direct Lab downloads, and end-to-end scoring tests for both examples.
- Add an optional `agents` dependency extra for LangGraph, LangChain Core, FastAPI, Uvicorn, and
  HTTPX, and exercise it in CI and release verification.

### Changed

- Expand the main agent-evaluation and Lab guides from placeholder adapter patterns to two runnable
  convenience-retail reference integrations with explicit trust, usage-accounting, and production
  hardening boundaries.

## [0.5.6] - 2026-07-31

### Added

- Add a guided **Connect your own agent** workflow to the Lab with a single-file Python adapter
  upload, non-executing syntax validation, automatic `@solver` entrypoint detection, process-local
  staging, a trusted-local solver alternative, a starter adapter download, and in-product setup and
  safety guidance.
- Add regression coverage for uploaded-adapter validation, entrypoint resolution, non-execution
  during staging, both custom-agent connection modes, and the Lab's dual-theme contract.

### Fixed

- Introduce explicit light-theme tokens and component overrides for the Lab's custom panels,
  traces, score workbench, status surfaces, labels, help text, and onboarding controls while
  preserving the established dark theme.

## [0.5.5] - 2026-07-29

### Added

- Add scorer-authored audit metadata for every weighted dimension, including concept and selection
  coverage, oracle regret, policy checks, recovery conditions, citation precision and sufficiency,
  calibration arithmetic, and the tool-call efficiency budget.
- Make every dimension scorecard interactive so a user can open the exact formula, run-specific
  inputs, and plain-language reason for its score without leaving the score workbench.
- Replace the generic trace score-impact note with event-specific citation status, evidence credit,
  tool-budget impact, recovery role, and final-submission lineage.

### Changed

- Allow the complete evaluation-target prompt to wrap in the context strip instead of truncating it
  to a single line.

## [0.5.4] - 2026-07-29

### Fixed

- Replace the sample-limit-driven built-in ReAct loop with an explicitly bounded tool loop that
  disables parallel tool bursts, then performs up to two internal tool-free JSON finalization
  attempts before Inspect can terminate the sample.
- Publish the complete queryable retail schema in the SQL tool contract and return actionable
  public-table guidance after unknown-table or blocked-catalog queries, preventing repeated guesses
  such as `sales`, `shelf`, `product_metrics`, and `sqlite_master`.
- Preserve exact SQL arguments and returned payloads on both tool-call and tool-result trace rows,
  so the Lab inspector no longer displays an empty payload for a successful call or hides the query
  that caused a warning.

## [0.5.3] - 2026-07-28

### Fixed

- Reserve a separate tool-free finalization turn for every built-in agent after its exploration
  loop, so reaching the message boundary cannot silently discard an otherwise recoverable decision.
- Treat a run with no final JSON decision as incomplete and unscored instead of reporting a
  misleading all-zero composite. Inspect now excludes that sample from score aggregates while the
  Lab preserves its trace, evidence, and provisional scorer diagnostics for troubleshooting.
- Bottom-align the Agent, Model, Task, Condition, and Run controls in one equal-height toolbar and
  rebalance their responsive widths so labels and inputs no longer form staggered rows.
- Stop forcing `temperature=0.0` in every built-in planning, verifier, specialist, and feedback
  generation. Reasoning models that reject sampling controls now run with provider-safe defaults
  instead of failing before tool execution.
- Replace the Lab's dense two-row setup form with a single evaluation toolbar and compact context
  strip, increase trace and inspector legibility, select the first useful model/tool event by
  default, and keep failed traces proportional to the events that were actually recorded.
- Replace raw provider exception and traceback dumps with classified, actionable error cards while
  retaining the original Inspect log for complete diagnostics.

## [0.5.2] - 2026-07-28

### Added

- Rebuild DecisionAgentBench Lab as a full-width evaluation studio with real one-sample Inspect
  execution, editable model selection, eight built-in architectures, trusted custom-solver loading,
  all registered v0.2 task pairs, selectable traces, and portable Lab and Inspect logs.
- Add a transparent score workbench that reconstructs the historical weighted equation, dimension
  contributions, format/evidence/safety gates, failure effects, robustness diagnostic, contribution
  ledger, and evidence-to-dimension lineage.
- Add a dedicated Lab guide covering model credentials, real execution, custom-agent import, trace
  interpretation, exact scoring, export behavior, and current research claim limits.

### Fixed

- Make Lab styling compatible with both pre-6 and 6.x Gradio placement rules so the supported
  Gradio 6 launch no longer relies on obsolete `Blocks` arguments and older local installs do not
  receive unsupported `launch()` keywords.
- Validate every client-provided Lab selection at the callback boundary and generate world/report
  paths independently of client values, preventing path traversal through direct Gradio requests.
- Remove the narrow page cap, decorative stage strip, native spreadsheet trace, and preloaded
  completed replay; runs now start empty and visibly populate from a finalized Inspect log.

## [0.5.1] - 2026-07-28

### Added

- Add a tested bring-your-own-agent solver example and an end-to-end guide covering Inspect-native
  solvers, external-system adapters, matched runs, trace inspection, sanitization, and current
  research claim limits.

### Changed

- Preserve an explicit custom `system_name` in task logs, sanitized analysis, and blinded
  annotation keys when an external solver overrides a reference baseline.

## [0.5.0] - 2026-07-27

### Added

- Add a strict, deterministic `simulate-power` workflow for the exact candidate study grid, with
  hierarchical family/instance/trajectory variance, clean/perturbed correlation, missingness,
  family-level contrasts, Monte Carlo max-|t| family-wise error control, MDEs, interval widths,
  effective-family counts, cost exposure, and upstream validity authorization.
- Add content-addressed power-design/report verification and commit both the failed initial
  three-confirmatory-contrast preflight and the revised 4,000-draw v0.5 candidate result: 25
  independent families, 100 seeded instances, 200 paired samples, three repetitions, four
  architectures, three fixed model-family blocks, 7,200 executions, and a $1,800 ceiling.
- Add a structural and empirical `metric-dependence` audit with Pearson and tie-aware Spearman
  correlations, identical-value rates, whole-family bootstrap intervals, source hashes, and an
  explicit high-correlation review rule.
- Publish the power-analysis and metric-dependence protocols, including assumptions, initial
  underpowered results, the confirmatory/exploratory decision, pilot-update rules, and claim limits.

### Changed

- Reduce the candidate architecture grid from eight historical baselines to four. Retain only the
  adequately powered memory-feedback recovery contrast as confirmatory; planner effectiveness and
  verifier explainability are exploratory, while prompt/context ablations remain validation probes.
- Keep paid publication-scale execution blocked because the merged v0.4 audit did not implement
  the typed measurement-validity contract required by the roadmap.

## [0.4.0] - 2026-07-27

### Documentation

- Record the independently reproduced scorer-validity exploits and correct version-specific counts
  for lexical scoring, economic oracles, decision-quality duplication, tests, and workflow topology.
- Replace the staged milestone plan with a validity-first v0.4.0-v1.0.0 roadmap that blocks
  publication-scale runs on construct validity, power, task discrimination, branching workflows,
  external grader validation, and red teaming.
- Correct documentation that overstated semantic evidence support or decision-sensitive workflow
  grading in the historical v0.1-v0.3 contracts.

## [0.3.1] - 2026-07-27

### Fixed

- Make the Inspect mock-model integration tests independent of the remote tiktoken encoding CDN,
  so all four advanced architectures execute in clean and network-restricted environments.
- Include the baseline name and underlying Inspect error in architecture-test failures. The v0.3.0
  task, scoring, workflow, and catalog contracts remain unchanged.

## [0.3.0] - 2026-07-22

### Added

- A separate dependency-enforced workflow preview with 3 concepts, 12 seeded instances, and 24
  paired samples; the frozen v0.1 and v0.2 suites remain unchanged.
- Twenty persisted, prerequisite-gated transitions per workflow, a target dependency span of 19,
  and delayed checkpoints across at least 15 simulated days.
- Typed workflow inspection, execution, time-advance, and rollback tools backed by private SQLite
  state, mutation, event, and trace tables.
- Clean/stressed pairs for regional turnaround, vendor-product pilot, and recall recovery. Stressed
  samples block downstream progress until a revealed mutable action is rolled back.
- Trace-derived effectiveness and decision quality plus sanitized workflow telemetry for
  completion, span, time, invalid attempts, delayed events, rollback, and terminal-state digest.
- A machine-readable workflow catalog, experiment templates, archival release coverage, and an
  explicit “dependency-enforced horizon preview” claim boundary.
- Analysis schema 3.0 adds nullable workflow completion, transition, dependency-span, simulated-
  time, rollback, and invalid-attempt telemetry while preserving nulls for v0.1/v0.2 samples.

### Changed

- v0.3 uses the strict, evidence-gated submission contract. A narrative-only answer or incomplete
  execution receives zero effectiveness and decision quality and cannot earn a composite score.
- The Inspect registration audit now targets the v0.3 task entry by default.

## [0.2.1] - 2026-07-21

### Fixed

- Make valid tool evidence a v0.2.1 eligibility condition: unsupported or partially grounded
  answers receive zero task effectiveness, decision quality, and composite while safety remains
  separately observable. Preserve frozen v0.1 and v0.2.0 scoring behavior for reproducibility.
- Cycle all family perturbations across four seeds, activating all 53 named perturbations instead of
  only the first perturbation in each family, with executable state or transient-failure coverage
  tests for every perturbation.
- Correct the evaluation-unit claim to **25 concepts, 100 seeded instances, and 200 paired
  samples**, explicitly documenting that many answer keys repeat across seeds.
- Remove the unsupported long-horizon claim. Publish legacy step estimates, optimal tool counts,
  enforced dependency depth, and horizon-claim status as separate fields; rename the expanded
  workflow category to `workflow_planning`.

## [0.2.0] - 2026-07-21

- Distinguish preview bundles from package-version prereleases so an explicitly assembled stable
  research preview can pass independent verification without being mistaken for a final release.
- Remove a polynomial fenced-JSON regular expression, normalize namespaced Inspect tool identities,
  and make the GitHub dependency-audit artifact path explicit.

### Added

- Tamper-evident experiment manifests and matched-budget Inspect command grids.
- Double-confirmed, cost-capped provider execution with isolated runtime state and redacted logs.
- Sanitized sample telemetry, deterministic bootstrap intervals, within-task reliability, paired
  robustness deltas, failure summaries, and publishable-only leaderboard generation.
- Independent-verifier, multi-agent, memory-and-feedback, and corrupted-context research baselines,
  plus no-policy and no-evidence prompt ablations.
- A v0.2 task registration with 100 seeded scenario instances, 200 paired evaluation samples, and a
  generated machine-readable instance catalog.
- A local Gradio evaluation Lab with real one-sample Inspect execution, editable model selection,
  trusted custom-solver loading, selectable trace inspection, and transparent score reconstruction.
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
- Release audits and provenance checks support allow-listed Docker or Podman runtimes and record the
  selected engine, preserving identical image verification in CI and local OCI environments.
- The v0.2 scoring contract adds an exhaustive information-matched replacement-product oracle while
  retaining frozen v0.1 semantics; manifests now reject benchmark/scoring version mismatches and
  the instance catalog records both v0.2 contract and inherited family-spec versions.
- Analysis schema 2.1 preserves oracle applicability, utility units, candidate and feasible-optimal
  utility, and absolute and normalized regret in sanitized records and group summaries instead of
  reducing executable economic outcomes to one composite input.
- The versioned v0.2 scorer now rejects duplicate JSON keys, non-standard numeric constants, invalid
  field types, and out-of-range confidence; repeated citations no longer inflate evidence
  sufficiency, and missing distinct evidence receives `F-EVID`. Frozen v0.1 behavior is preserved.

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
