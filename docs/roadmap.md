# Versioned roadmap

DecisionAgentBench follows a validity-first release sequence. Releases through v0.5.x established
substantial benchmark infrastructure, statistical preflight tooling, an interactive evaluation Lab,
and bring-your-own-agent integrations. They did not close the measurement-validity gap discovered
in v0.4.0, and they do not support a public model leaderboard or a general long-horizon claim.

This roadmap incorporates the v0.4 measurement audit, the completed v0.5.x work, the subsequent
comparison with closed-loop retail-agent benchmarks, and the
[Google Agent Quality review](google-agent-quality-review.md). It supersedes the earlier mapping of
v0.6-v0.9 without renaming released software or rewriting historical task contracts.

## Release principles

- Every release is a reviewed, evidence-bearing increment. The next version starts only after the
  previous version is merged and explicitly approved.
- Published task and scorer contracts remain reproducible. Result-affecting changes receive a new
  task-contract and analysis-schema version.
- A larger sample count cannot substitute for more independent task concepts.
- A metric is reported only when its construct is independently measurable. Structurally
  inapplicable values are null, not copies of another metric.
- Evaluation proceeds outside-in: eligibility and safety, then end-to-end business outcomes, then
  trajectory diagnostics. Process quality cannot compensate for a failed outcome or hard safety
  violation.
- Long horizon means dependent state changes and delayed consequences, not metadata, prompt length,
  tool count, or a long linear checklist.
- Official scores require complete, causally linked traces. Public plans and action intent are
  observable; provider-private chain of thought is never required.
- Publication-scale model spending requires construct-valid scoring, a documented power analysis,
  a frozen experiment manifest, and successful external validation.
- A leaderboard is an output of a validated study, not evidence that the study is valid.

## Completed implementation: v0.0.1-v0.7.0 release candidate

| Release | Completed scope | Claim boundary |
| --- | --- | --- |
| `v0.0.1` | Research design, first 25 task specifications, repository standards, CI | Design foundation only |
| `v0.0.2` | Seeded SQLite retail company, tools, policies, manifests, invariant tests | Synthetic snapshot world, not real-company validity |
| `v0.1.0` | 25 executable Inspect task families and two reference baselines | Historical lexical/evidence-lineage scorer retained for reproduction |
| `v0.2.0-v0.2.1` | Strict JSON contract, evidence-ID eligibility, 100 seeded instances, 200 paired samples, second economic oracle | 25 concepts, not 200 independent tasks; evidence existence is not semantic support |
| `v0.3.0-v0.3.1` | Three dependency-enforced workflow concepts with persisted transitions, delayed events, rollback, and offline fixes | Linear workflow preview, not general long-horizon planning |
| `v0.4.0` | Independently reproduced measurement audit and validity-first roadmap | Specified the scorer redesign but did not implement it |
| `v0.5.0` | Hierarchical power/MDE simulation and metric-dependence audit | Statistical preflight only; its assumptions require a valid-score pilot |
| `v0.5.1-v0.5.6` | Agent-evaluation guide, real Inspect-powered Lab, reliable agent finalization, run-specific scoring explanations, dual-theme UI, and custom-agent upload | Evaluation tooling around the historical scorer; not validated model-quality evidence |
| `v0.5.7` | Standalone and Lab-compatible LangGraph examples for an in-process store assistant and remote replenishment service | Integration examples, not benchmark baselines or performance claims |
| `v0.6.0` | Typed world-derived scoring, semantic evidence support, behavioral safety, metric applicability, and portable causal traces | Construct-valid scorer implementation; synthetic-world external validity and publication claims remain gated |
| `v0.7.0` | Coupled closed-loop retail state, partial observability, deterministic replay, structured approvals, held-out regimes, public and privileged policies, causal intervention pairs, and calibration evidence | Validated synthetic world infrastructure; discriminating tasks, external validity, and a general long-horizon claim remain gated |

The experiment planner, cost gates, sanitizer, cluster bootstrap, annotation tooling, Lab, release
audit, security workflows, and governance materials are implemented infrastructure. They are
important strengths, but they do not substitute for the scientific gates below.

## Why the remaining sequence changed

The earlier roadmap left the v0.4 scorer implementation as an unnumbered blocking gate even after
v0.5.x shipped. It also grouped richer data generation with task discrimination and moved directly
from branching workflows to external validation. The revised plan makes each dependency explicit:

1. v0.6 owns the previously unimplemented measurement-validity contract.
2. v0.7 is a dedicated closed-loop retail-world release in which actions cause later outcomes.
3. v0.8 builds discriminating tasks and strong baselines on that validated world.
4. v0.9 establishes decision-sensitive workflows, portable observability, and the long-horizon
   claim.
5. v0.10 validates deterministic and model-based evaluators, adds the governed feedback loop, and
   freezes a release candidate.
6. v0.11 performs the first publication-eligible comparative study.
7. v1.0 publishes stable contracts only after independent reproduction.

## v0.6.0 - Construct-valid scoring and evaluation contract

**Status:** released and approved as the v0.7 prerequisite.

Replace the v0.1-v0.3 lexical grading surface with a separate versioned contract whose primary
scores come from typed, world-derived outcomes and audited behavior. Frozen historical tasks remain
runnable but are ineligible for new leaderboard claims.

### Deliverables

- Publish a task-by-task construct map covering ground truth, applicable metrics, tolerances,
  evidence requirements, safety rules, and known ambiguity.
- Replace `expected_concepts` as a primary grader with deterministic typed answer functions over the
  seeded world.
- Add typed claims and proposed, attempted, completed, and successful actions. Prose is not the
  authoritative safety signal.
- Verify semantic claim support against canonical facts retained with each cited evidence item.
  Evidence-ID existence and required-tool coverage remain provenance checks only.
- Implement regret, dominance, constraint satisfaction, or another independent utility measure for
  every task where decision quality applies; return null elsewhere.
- Remove per-sample calibration and duplicated robustness from the composite. Retain confidence and
  Brier loss as telemetry and calculate calibration only over groups.
- Grade prompt-injection and policy safety from trusted-source use, approvals, structured actions,
  and the action ledger rather than keyword presence.
- Publish an outside-in score contract that separates eligibility and hard safety, end-to-end
  outcome quality, and non-compensatory trajectory diagnostics.
- Define a portable event schema with run, trace, span, and parent IDs; actor and role; public action
  intent; typed model/tool inputs and outputs; errors; evidence; state mutations; approvals; usage;
  latency; and cost.
- Replace the historical failure codes with an observable trajectory taxonomy covering planning,
  tool selection and parameterization, result interpretation, retrieval and evidence, loops,
  recovery, multi-agent handoffs, authorization, privacy, and safety.
- Classify trace fields and apply configurable secret and personal-data minimization before durable
  storage or export where possible; document raw-trace access and retention boundaries.
- Add adversarial fixtures and degenerate baselines for keyword stuffing, fixed answers, correct
  paraphrases, fabricated or irrelevant citations, evidence spam, unsafe narrated intent, and
  injection compliance.
- Publish a scorer-validity report and a migration guide for custom agents and historical logs.

### Exit gate

- Keyword stuffing scores `composite <= 0.30`; a supported correct paraphrase scores
  `effectiveness >= 0.80`; injection compliance scores `safety = 0` and `composite = 0`.
- Every concept has a typed world-derived answer or an explicit reviewed human-scoring reason.
- Wording-only changes cannot alter primary scores while typed claims remain fixed.
- Mutating cited facts produces the expected support or contradiction failure.
- `decision_quality` never defaults to `task_effectiveness`; applicability and coverage are public.
- The final outcome score can be reproduced from versioned state, action, and evidence records;
  trajectory diagnostics cannot inflate a failed outcome.
- Trace completeness and parent-child lineage are machine-validated across built-in, uploaded, and
  remote agents, without requiring hidden chain of thought.
- All validity fixtures, contract migrations, automated checks, and a blinded human spot-check pass.

## v0.7.0 - Closed-loop retail world

**Status:** implementation complete in the v0.7.0 release candidate; pending maintainer review and
merge.

Create a new deterministic retail-world version where agent decisions alter future observations and
business outcomes. Preserve the historical snapshot world for reproduction.

### Deliverables

- Implement coupled daily transitions for inventory, purchase orders and delivery delays, shelf
  allocation, pricing and promotions, demand and substitution, sales and lost sales, aging and
  spoilage, returns and feedback, operational events, and cash flow.
- Enforce partial observability: agents use bounded business tools while the simulator and oracle
  retain clearly documented privileged state.
- Ground or calibrate important distributions with documented public retail data; label every
  synthetic or hand-authored mechanism and publish sensitivity ranges.
- Add held-out generator regimes, store heterogeneity, seasonality, shocks, and independently
  reproducible world manifests.
- Add accounting, inventory-flow, capacity, temporal, authorization, determinism, and causal
  intervention tests.
- Represent high-stakes interruptions as structured approval-required, approval-requested,
  approved/rejected, resumed, and aborted events rather than prose-only escalation claims.
- Provide random, fixed-policy, reorder-point, newsvendor, pricing, and information-matched heuristic
  baselines plus a privileged diagnostic oracle that is never presented as a fair agent baseline.

### Exit gate

- Replaying the same seed and action sequence yields the same state and ledger.
- At least one feasible decision in every benchmark scenario changes a later observable state and
  realized utility relative to an alternative action.
- Conservation, accounting, capacity, and policy invariants hold across stress simulations.
- Simulator distributions and failure modes have a public calibration and sensitivity report.
- Configurable multi-week and multi-month episodes run reproducibly, but the unqualified
  “long-horizon” claim remains blocked until v0.9.

### Release evidence

- The committed v0.7 reference manifest regenerates to the same canonical initial-state digest.
- Same-seed, same-action replays match across multi-week and 60-day episodes.
- Replenishment, pricing, shelf-allocation, and approved-promotion matched pairs each change later
  observable state and realized utility.
- Conservation, accounting, lot-flow, capacity, temporal, authorization, approval-state, and
  causal-intervention tests run across normal, held-out, and mixed-stress regimes.
- The content-addressed calibration report discloses public grounding, synthetic mechanisms,
  parameter ranges, regime summaries, and directional sensitivity.
- Six fair public-state policies and one explicitly ineligible privileged diagnostic policy are
  executable. No policy result is presented as an agent leaderboard result.

## v0.8.0 - Discriminating task suite and baseline validation

**Status:** planned after v0.7.0 approval; no implementation starts before maintainer sign-off.

Build new task families on the closed-loop world and demonstrate that the suite rewards the intended
decision constructs rather than answer frequency, entity memorization, or tool volume.

### Deliverables

- Replace single-cause fixtures with composed causes, countervailing effects, red herrings,
  heterogeneous stores, ambiguity boundaries, and independently recoverable magnitudes.
- Vary correct conclusions and optimal actions across seeds while preserving deterministic ground
  truth and matched clean/perturbed objectives.
- Add distinct task families where power requires them; do not count cosmetic seed copies as new
  concepts.
- Add held-out surface forms and generator regimes for shortcut, leakage, and distribution-shift
  testing.
- Use realized utility, constraint-adjusted regret, or dominance for quantitative decisions.
- Run model-free shortcuts, degenerate agents, classical retail policies, solver ablations, and a
  limited non-leaderboard discrimination pilot.
- Rerun the v0.5 power analysis using final family counts and pilot variance.

### Exit gate

- Fixed-answer, keyword, citation-spam, and entity-frequency baselines cannot pass the suite.
- Strong task-appropriate policies outperform random and weak baselines where the construct predicts
  they should.
- The pilot reports ceiling/floor behavior, item difficulty, failure modes, family variance, metric
  dependence, and applicable denominators without making leaderboard claims.
- Every confirmatory contrast has at least 80% simulated power or is explicitly exploratory.

## v0.9.0 - Decision-sensitive workflows, observability, and horizon validation

**Status:** planned after v0.8.0 approval.

Replace the linear v0.3 preview as the primary workflow surface and determine whether the resulting
episodes justify a long-horizon claim.

### Deliverables

- Add workflow-specific dependency DAGs with real branches, optional paths, concurrency constraints,
  rollback, and multiple feasible action orders.
- Include choices with different measurable utility, risk, cost, service, or recovery consequences.
- Make delayed observations and available future actions depend on earlier choices and evolving world
  state.
- Grade outcome utility and adaptation rather than checklist completion.
- Report simulated days, dependent state transitions, decision points, model turns, tool calls,
  tokens, and wall-clock duration separately.
- Add OpenTelemetry-compatible span export and context propagation across Inspect, the Lab, local
  adapters, remote services, tools, and multi-agent handoffs.
- Separate operational dashboards and exports (latency percentiles, error rate, tokens, cost, tool
  frequency, and trace completeness) from quality dashboards (outcome, utility, evidence support,
  recovery, robustness, and safety).
- Produce run-level root-cause diagnostics for planning, tool selection, tool arguments, tool-result
  interpretation, retrieval, recovery, and multi-agent coordination without assigning invented
  per-event score deltas.
- Require complete traces for official evaluations. Any production-observability sampling policy is
  declared and its sampled traces remain ineligible for benchmark ranking.
- Run a skilled-human completion-time study and audit representative non-mock agent traces using a
  documented time-horizon methodology.

### Exit gate

- Graph tests demonstrate reachable alternatives, decision-dependent outcomes, optional-path
  validity, and no fixed sequence that maximizes every instance.
- Failed or delayed decisions propagate into later state and remain recoverable only through valid
  actions where the scenario permits recovery.
- Workflow decision quality comes from outcome utility or dominance, not completion percentage.
- Local and remote-agent traces preserve one verifiable causal graph, and aggregate operational
  metrics can be reconstructed from its spans.
- Missing causal spans, usage, or required action/evidence lineage make a run incomplete rather than
  silently converting it into a low quality score.
- Any long-horizon label is qualified by human-time evidence and audited dependency depth.

## v0.10.0 - Evaluator validation, feedback flywheel, and red team

**Status:** planned after v0.9.0 approval.

Validate the benchmark itself before treating deterministic scores as reference labels and freeze a
release candidate for the comparative study.

### Deliverables

- Blind multiple human raters to deterministic scores and oversample threshold, safety-critical,
  high/low-scoring, and disagreement cases.
- Report agreement separately for typed correctness, utility, evidence support, safety, recovery,
  and failure taxonomy.
- Treat deterministic-human disagreement as a possible grader defect first.
- Evaluate optional pairwise LLM-as-a-judge and agent-as-a-judge diagnostics against the same
  blinded human packets. Test order, identity, self-preference, verbosity, reference leakage, and
  repeatability effects; model judges cannot override deterministic facts or safety events.
- Extend the Lab and annotation workflow with context-rich review queues, inline trajectory failure
  tags, adjudication status, and optional user or developer feedback ingestion.
- Add a governed promotion pipeline that converts adjudicated, deduplicated, privacy-reviewed
  failures into versioned regression cases while keeping public tasks, private holdouts, and product
  regressions separate.
- Invite an external contributor to build a deliberately degenerate high-scoring agent and publish
  the attack, result, and remediation.
- Complete leakage, ambiguous-task, tool-boundary, oracle-information, privacy, and security audits.
- Freeze release-candidate datasets, worlds, scorers, analysis schemas, budgets, and correction
  policy.

### Exit gate

- No unresolved high-severity grader exploit remains.
- Prespecified human-agreement thresholds pass for safety and typed correctness; material
  disagreement strata are documented.
- Model-judge agreement, consistency, bias probes, and failure strata are public; no subjective
  judge is admitted as an authoritative label without human calibration.
- Every promoted regression case has provenance, adjudication, privacy status, version, and a
  leakage-safe dataset assignment.
- The red-team agent cannot gain eligibility through unsupported citations, fixed answers, keyword
  stuffing, hidden-state access, unsafe narrated intent, or budget abuse.
- One independent reviewer reproduces the validity suite from a clean checkout.

## v0.11.0 - Publication-eligible empirical benchmark beta

**Status:** blocked on v0.8.0-v0.10.0.

Run the first evidence-bearing comparative study. The exact grid is determined by the power analysis
and frozen before execution.

### Deliverables

- Evaluate at least three current publishable model families under matched tool, token, time, and
  cost budgets with repeated paired seeds.
- Analyze all eligible prespecified runs; do not select each model’s best successful rollout as its
  headline result.
- Publish complete clean/perturbed coverage, immutable manifests, sanitized logs, paired effects,
  family-cluster uncertainty, calibration, safety events, cost, latency, missingness, and metric
  dependence.
- State independent family count, instances, samples, repetitions, MDE, uncertainty, and applicable
  denominators in every result table.
- Publish a provisional leaderboard that admits only complete verified runs and keeps hard safety
  events visible beside any composite.

### Exit gate

- All construct-validity, power, world, discrimination, workflow, horizon, human-validation,
  red-team, leakage, cost, and release audits pass.
- Confirmatory and exploratory findings are separated; effect sizes and uncertainty are published
  even when systems do not meaningfully differ.
- The study regenerates from its immutable manifest and content-addressed artifacts.

## v1.0.0 - Stable public research release

**Status:** blocked on v0.11.0 review.

### Deliverables and exit gate

- Publish the benchmark, versioned datasets and worlds, validated scorer, reproducible container,
  empirical report or preprint, presentation, and contributor materials.
- Publish construct-validity evidence, adversarial fixtures, evidence-support tests, human agreement,
  red-team results, calibration, metric dependence, and correction history.
- Obtain an archival DOI, independent end-to-end reproduction, security review, and upstream Inspect
  Evals registration when eligibility is established.
- Freeze semantic contracts for the v1 line. Compatible maintenance and transparent corrections use
  v1.x; result-affecting redesigns require a new task version and may require v2.

## After v1.0.0

- **v1.x:** compatible maintenance, externally contributed instances under frozen semantics,
  updated model runs, and visible corrections.
- **v2.0.0:** additional stores, competition, labor, promotions, multi-agent operations, or a second
  application domain. Cross-domain scores are not pooled unless comparability is demonstrated.

## Commit and review policy

- Commit only a complete, verified version or a coherent reviewable slice within a large version.
- Use imperative subjects and explain result-affecting decisions in commit bodies.
- Do not start the next version until the prior pull request is reviewed, merged, and explicitly
  approved.
- Never rewrite published results; issue a versioned correction with retained provenance.
- Do not push secrets, unsanitized provider traces, or unreviewed large artifacts.
