# Versioned roadmap

DecisionAgentBench now follows a validity-first release sequence. The completed releases established
useful engineering infrastructure, but the v0.1-v0.3 decision scorer is not sufficiently
construct-valid for a public model leaderboard. Publication-scale provider runs are blocked until
the measurement, power, and task-discrimination gates below are satisfied.

This roadmap supersedes earlier milestone descriptions that did not reserve a distinct phase for
grader validity. It does not retroactively rename released software or rewrite historical task
contracts.

## Release principles

- Every release is a reviewed, evidence-bearing increment. The next version starts only after the
  previous version is merged and explicitly approved.
- Published task and scorer contracts remain reproducible. Result-affecting changes receive a new
  task-contract and analysis-schema version.
- A larger sample count cannot substitute for more independent task concepts.
- A metric is reported only when its construct is independently measurable. Structurally
  inapplicable values are null, not copies of another metric.
- Publication-scale model spending requires construct-valid scoring, a documented power analysis,
  and an immutable cost-authorized experiment manifest.
- A leaderboard is an output of a validated study, not evidence that the study is valid.

## Completed foundation and audit releases: v0.0.1-v0.4.0

| Release | Completed scope | Claim boundary |
| --- | --- | --- |
| `v0.0.1` | Research design, first 25 task specifications, repository standards, CI | Design foundation only |
| `v0.0.2` | Seeded SQLite retail company, tools, policies, manifests, invariant tests | Synthetic world, not real-company validity |
| `v0.1.0` | 25 executable Inspect task families and two reference baselines | Historical lexical/evidence-lineage scorer retained for reproducibility |
| `v0.2.0-v0.2.1` | Strict JSON contract, evidence-ID eligibility, 100 seeded instances, 200 paired samples, second economic oracle | 25 concepts, not 200 independent tasks; evidence existence is not semantic support |
| `v0.3.0` | Three dependency-enforced workflow concepts with persisted transitions, delayed events, and rollback | Workflow preview with a linear shared topology, not general long-horizon planning |
| `v0.3.1` | Offline Inspect test fix and documentation consolidation | No empirical model-performance claim |
| `v0.4.0` | Independently reproduced measurement audit and validity-first roadmap | The audit specified the scorer redesign but did not implement it; the validity gate remains open |

The experiment planner, cost gates, sanitizer, cluster bootstrap, annotation tooling, demo, release
audit, and governance materials are implemented infrastructure. They are not substitutes for the
validation work below.

## v0.4 measurement-validity implementation gate

**Status:** blocking. The v0.4.0 audit release is merged; the implementation below is not.

Replace the v0.1-v0.3 lexical grading surface with a separate versioned contract whose primary
scores come from typed, world-derived outcomes and audited behavior. The frozen historical tasks
remain runnable but become ineligible for new leaderboard claims.

### Deliverables

1. **Task-by-task construct map.** For all 25 retail concepts, publish the intended construct,
   observable ground truth, applicable metrics, tolerances, evidence requirements, safety rules,
   and known ambiguity. No metric may silently fall back to another metric.
2. **Computed answer keys.** Replace `expected_concepts` as a primary grader with deterministic
   functions over the seeded world. Grade typed fields such as region, driver, direction,
   magnitude, chosen entities, abstention, and bounded numeric decisions.
3. **Structured claims and actions.** Extend the submission contract with typed claims and proposed,
   attempted, and completed actions. Grade authorization and policy against these fields and the
   action ledger; prose is never the authoritative safety signal.
4. **Evidence support.** Bind each machine-checkable claim to evidence IDs and retain the canonical
   facts needed to verify that cited results support the claim. ID existence and required-tool
   coverage remain provenance checks, not semantic-support checks.
5. **Independent decision quality.** Implement regret, dominance, constraint satisfaction, or
   another independent utility measure for every task where decision quality is applicable. Return
   null where it is not independently defined and reweight aggregates only over applicable
   dimensions.
6. **Metric redesign.** Remove per-sample calibration and duplicated robustness from the composite.
   Retain confidence and Brier loss as raw sample telemetry; report calibration curves and summary
   calibration error only over groups of predictions. Publish the new composite rationale before
   model runs.
7. **Behavioral safety grading.** Determine injection resistance from trusted-source use, structured
   actions, approvals, and the ledger. Remove keyword-presence safety rules.
8. **Adversarial validity tests.** Add `tests/test_grader_validity.py` with keyword stuffing,
   correct paraphrases, fabricated-but-existing evidence, unsupported claims, unsafe stated intent,
   and injection-compliance cases for every relevant construct.
9. **Public validity report.** Publish the fixtures, expected outcomes, test results, and remaining
   constructs that still require human review.

### Exit gate

- The three reproduced exploits in the
  [measurement-validity audit](measurement-validity-review.md) satisfy these bounds:
  keyword stuffing `composite <= 0.30`, supported correct paraphrase `effectiveness >= 0.80`, and
  injection compliance `safety = 0` and `composite = 0`.
- Every one of the 25 concepts has a typed world-derived answer or an explicit, reviewed reason it
  is human-scored; no primary score depends on free-text substring matching.
- Changing only conclusion wording while holding typed claims fixed cannot change primary outcome
  scores.
- Mutating cited facts produces the expected claim-support failure.
- `decision_quality` never defaults to `task_effectiveness`; applicability and coverage are public.
- All automated checks, adversarial fixtures, contract migration tests, and a small blinded human
  spot-check pass.
- No publication-scale paid comparison is authorized before this gate is reviewed and merged.

## v0.5.0 - Statistical design and metric audit

**Status:** implemented statistical layer; publication authorization remains blocked by v0.4.

Determine whether the registered task-family population can answer the proposed model and
architecture questions before paying for a full grid.

### Deliverables

- Add a deterministic `simulate-power` command and `docs/power-analysis.md`.
- Simulate the exact candidate grid under documented family variance, instance variance,
  trajectory variance, clean/perturbed correlation, missingness, and plausible effect sizes.
- Report effective independent family count, minimum detectable effect (MDE), interval width,
  family-wise error plan, and power for every preregistered primary contrast.
- Use a small, explicitly non-publishable pilot only if needed to estimate variance; update the
  simulation without promoting pilot outcomes to benchmark claims.
- Reduce the primary architecture set, increase distinct task families, or label comparisons
  exploratory when the target effect cannot be estimated with adequate precision.
- Add a metric-dependence report using structural definitions plus empirical Pearson/Spearman
  correlations and uncertainty. High correlation triggers investigation; it is not an automatic
  instruction to merge constructs.

### Implemented outcome

- `simulate-power` executes a strict, content-addressed 4,000-draw hierarchical simulation with
  task-family inference, clean/perturbed correlation, missingness, MDEs, simultaneous interval
  widths, and single-step max-|t| control.
- The candidate grid has 25 independent families, 100 seeded instances, 200 paired samples, three
  repetitions, three fixed model-family blocks, four architectures, and 7,200 executions under a
  $1,800 ceiling.
- The initial three-contrast max-|t| design placed all three effects below 80% power. Planner
  effectiveness and verifier explainability were therefore labeled exploratory. With the smaller
  confirmatory family, memory-feedback perturbed recovery remains the sole confirmatory contrast,
  with 90.03% simulated power at its 0.10 smallest effect and an 80% MDE of 0.0849 under the stated
  assumptions.
- `metric-dependence` publishes Pearson/Spearman correlations, identical-value rates, and whole-
  family bootstrap intervals after a sanitized pilot. The structural audit is public; no empirical
  report is fabricated before a valid typed-score pilot exists.
- The report keeps `publication_scale_run_authorized` and `grid_frozen` false because the upstream
  measurement-validity implementation has not passed. See [the power analysis](power-analysis.md)
  and [metric-dependence audit](metric-dependence.md).

### Exit gate

- Every confirmatory contrast has a prespecified smallest effect of interest and either at least 80%
  simulated power or an explicit exploratory label.
- Every planned table states task-family count, seeded-instance count, sample count, repetitions,
  and MDE.
- The final architecture and ablation grid is frozen before the empirical run and fits within an
  explicit study-cost ceiling.

The first two exit conditions are satisfied by the candidate design. The cost ceiling is satisfied,
but the grid cannot become execution-frozen until the v0.4 endpoint contract exists and any required
non-publishable pilot has checked the variance assumptions.

## v0.6.0 - Richer retail world and discriminating tasks

**Status:** next after v0.5.0 review, but still blocked on the v0.4 implementation gate.

Create a new retail-world and task-contract version without modifying the historical reference
world. Increase construct diversity only where the power and validity audits show a need.

### Deliverables

- Replace single-cause diagnostic fixtures with composed causes, store-level heterogeneity,
  countervailing effects, red-herring correlations, and independently recoverable magnitudes.
- Vary decision-relevant answers across seeds while preserving deterministic ground truth and
  matched clean/perturbed objectives.
- Add distinct task families—not cosmetic seed copies—until the power target or a documented scope
  limit is met.
- Add held-out surface forms and generator regimes for leakage and shortcut testing.
- Extend regret/dominance oracles to every quantitative action-selection task identified as
  applicable in the v0.4 construct map.
- Add weak shortcut baselines, deliberately degenerate agents, and ablations that test whether the
  suite rewards intended reasoning rather than answer-frequency or entity memorization.

### Exit gate

- All new worlds reproduce from manifests and pass accounting, policy, answerability, and
  perturbation-preservation checks.
- A model-free shortcut cannot pass the typed validity suite by returning frequent labels or fixed
  entity IDs.
- A limited discrimination pilot reports ceiling/floor behavior, item difficulty, failure modes,
  and family-level variance without making leaderboard claims.
- The v0.5 power analysis is rerun with the final family count and pilot variance.

## v0.7.0 - Decision-sensitive branching workflows

**Status:** planned after v0.6.0 approval.

Replace the linear v0.3 preview as the primary workflow research surface. Preserve v0.3.0 for
historical reproduction.

### Deliverables

- Dependency DAGs with genuine branches, optional paths, concurrency constraints, and alternative
  feasible action orders.
- At least one choice in every workflow where two policy-compliant paths have different measurable
  utility, risk, cost, or recovery consequences.
- Workflow-specific topology and outcome logic rather than one shared 20-step scaffold with renamed
  steps.
- Delayed observations whose content depends on earlier choices, not only elapsed simulated time.
- Trace-derived planning metrics that distinguish correct adaptation from rote transition
  completion.
- A skilled-human protocol for task completion time; the unqualified “long-horizon” label remains
  prohibited until that study and non-mock trace audits exist.

### Exit gate

- Graph tests demonstrate reachable alternatives, optional-path validity, decision-dependent
  outcomes, rollback integrity, and no single fixed sequence that maximizes every instance.
- Workflow decision quality comes from outcome utility or dominance, not completion percentage.
- Dependency span is measured from nontrivial graph paths and reported with human time, agent turns,
  and tool calls as separate quantities.

## v0.8.0 - External grader validation and red team

**Status:** planned after v0.7.0 approval.

Validate the benchmark itself before treating deterministic scores as reference labels.

### Deliverables

- Blind multiple human raters to deterministic scores and oversample high-scoring, low-scoring,
  threshold, safety-critical, and disagreement cases.
- Report agreement separately for typed task correctness, decision quality, evidence support,
  safety, and failure taxonomy.
- Treat deterministic-human disagreement as a possible grader defect first, not automatically as
  human or model-judge noise.
- Invite an external contributor to build a deliberately degenerate high-scoring agent and publish
  the attack, result, and remediation.
- Complete leakage, ambiguous-task, tool-boundary, and oracle-information audits.
- Freeze a release-candidate dataset, scorer, analysis schema, and correction policy.

### Exit gate

- No unresolved high-severity grader exploit remains.
- Prespecified human-agreement thresholds pass for hard safety and typed correctness, and all
  material disagreement strata are documented.
- The red-team agent cannot reach leaderboard eligibility through keyword stuffing, unsupported
  citations, fixed answers, or unsafe narrated intent.
- One independent reviewer reproduces the validity suite from a clean checkout.

## v0.9.0 - Empirical benchmark beta

**Status:** blocked on v0.4.0-v0.8.0.

Run the first evidence-bearing comparative study. The exact grid is determined by the v0.5 power
analysis rather than by preserving an arbitrary number of architectures.

### Deliverables

- At least three current publishable model families under matched tool, token, time, and cost
  budgets, with repeated trials sufficient for the prespecified precision target.
- Complete eligible clean/perturbed coverage, frozen manifests, sanitized logs, paired effects,
  family-cluster uncertainty, calibration, safety events, cost, latency, and metric-dependence
  analysis.
- Every result table reports independent family count, instances, samples, repetitions, MDE, and
  applicable-metric denominators.
- A provisional leaderboard that ranks only complete verified runs and keeps hard safety events
  visible alongside any composite.
- An empirical technical report and updated articles containing only results regenerated from the
  verified analysis bundle.

### Exit gate

- Construct-validity, power, world-discrimination, workflow, human-validation, red-team, leakage,
  cost, and release audits all pass.
- Confirmatory and exploratory results are labeled separately; effect sizes and uncertainty are
  published even when no architecture separates from another.
- The complete study is reproducible from its immutable manifest and content-addressed artifacts.

## v1.0.0 - Stable public research release

**Status:** blocked on v0.9.0 review.

### Deliverables and exit gate

- Publish the benchmark, versioned datasets, validated scorer, reproducible container, empirical
  report or preprint, presentation, and contributor materials.
- Publish construct-validity evidence: adversarial grader fixtures, paraphrase/structured-claim
  invariance, evidence-support checks, human agreement, red-team results, metric dependence, and
  correction history.
- Obtain an archival DOI, independent reproduction, security review, and upstream Inspect Evals
  registration when eligibility is established.
- Freeze semantic contracts for the v1 line. v1.x permits compatible maintenance and transparent
  corrections; result-affecting redesigns require a new task version and may require v2.

## After v1.0.0

- **v1.x:** compatible maintenance, new externally contributed instances under frozen semantics,
  updated model runs, and visible corrections.
- **v2.0.0:** a second application domain and any cross-domain contract changes justified by the v1
  evidence. Cross-domain scores will not be pooled unless metric comparability is demonstrated.

## Commit and review policy

- Commit only a complete, verified version or a coherent reviewable slice within a large version.
- Use imperative subjects and explain result-affecting decisions in commit bodies.
- Do not start the next version until the prior pull request is reviewed, merged, and explicitly
  approved.
- Never rewrite published results; issue a versioned correction with retained provenance.
- Do not push secrets, unsanitized provider traces, or unreviewed large artifacts.
