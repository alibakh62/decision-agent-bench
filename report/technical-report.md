# DecisionAgentBench: Process-Aware Evaluation of Evidence-Grounded Business Decision Agents

**Status:** v0.3.0 research-preview methods report, 22 July 2026
**Benchmark software:** `0.3.0`
**Task protocols:** `0.1` confirmatory suite; `0.2` research expansion; `0.3` stateful preview

## Abstract

AI-agent benchmarks often reduce a trajectory to whether a final task was completed. That endpoint
can conceal economically dominated decisions, unsupported evidence, policy violations, failure to
recover from broken tools, and high variance across repeated attempts. DecisionAgentBench is an
open evaluation environment for consequential, evidence-grounded business decisions. Its first domain
is a fully synthetic convenience-retail company with versioned stores, products, customers,
inventory, vendors, transactions, documents, approvals, and auditable business actions. Agents use
bounded SQL, retrieval, forecasting, recommendation, approval, and state-changing tools within the
Inspect AI framework.

The frozen v0.1 protocol defines 25 task families with matched clean and controlled-perturbation
conditions, yielding 50 evaluation samples per repetition. A registered v0.2 expansion contains
25 concepts, 100 seeded instances, and 200 paired samples (100 clean/perturbed pairs). The benchmark reports task effectiveness,
oracle-relative decision quality, safety, robustness, calibration, efficiency, recovery,
explainability, and a safety-gated composite. Six agent architectures and two prompt ablations are
implemented. Deterministic state, economic, evidence-lineage, and policy graders are preferred over
model judgments; a blinded study protocol measures human, LLM-judge, and deterministic agreement.

A separate v0.3 preview adds three stateful workflow concepts, twelve seeded instances, and 24
clean/stressed samples. Each requires 20 persisted transitions over at least 15 simulated days,
with delayed events, a dependency-span target of 19, real simulator mutations, and mandatory
rollback in stressed conditions. We call this a dependency-enforced horizon preview rather than a
general or human-time long-horizon benchmark.

This prerelease report documents the design, implementation, and statistical plan. It deliberately
contains no frontier-model performance claims: confirmatory provider runs, human ratings, and an
independent reproduction remain release gates.

## 1. Introduction

An enterprise agent can produce the requested artifact and still fail the decision. A promotion
may increase units while destroying contribution margin. A fraud investigation may identify a
pattern while accusing a customer without required review. A pricing workflow may choose a
reasonable value yet cross an authorization boundary. A fluent explanation may cite evidence that
was never returned by a tool. These failures matter because the agent changes or recommends a
business state, not because its prose is imperfect.

DecisionAgentBench treats an evaluation sample as an interaction among a versioned world, an
agent-visible evidence surface, a tool and policy boundary, a controlled perturbation, and an
executable outcome function. The primary questions are:

1. Does nominal task success hide economic, safety, or evidence failures?
2. Which agent architectures improve reliability under matched access and budgets?
3. How much performance degrades under operational and adversarial perturbations?
4. How much repeated-run variability is hidden by one evaluation?
5. Where do human or model judges disagree with executable outcomes?

The intended contribution is not another orchestration demo. It is an inspectable research object:
task contracts, seeded data generation, bounded tools, deterministic graders, reference agents,
tamper-evident experiment manifests, paired analysis, and public governance.

## 2. Related work

[AgentBench](https://arxiv.org/abs/2308.03688) established a multi-environment approach to
evaluating models as interactive agents and highlighted long-term reasoning, decision-making, and
instruction-following failures. [GAIA](https://proceedings.iclr.cc/paper_files/paper/2024/hash/25ae35b5b1738d80f1f03a8713e405ec-Abstract-Conference.html)
uses carefully designed real-world questions requiring reasoning, browsing, multimodality, and
tools while retaining objectively checkable answers. [WebArena](https://arxiv.org/abs/2307.13854)
emphasizes reproducible, functional web environments and execution-based task completion.
[ToolLLM/ToolBench](https://arxiv.org/abs/2307.16789) studies broad API retrieval and use.

Recent long-duration work sets a materially different bar from a declared step count.
[RetailBench](https://arxiv.org/abs/2603.16453) uses a partially observable, evolving 180-day retail
environment; [YC-Bench](https://arxiv.org/abs/2604.01212) spans a simulated year and hundreds of
turns with delayed and compounding consequences; and
[LongDS-Bench](https://arxiv.org/abs/2605.30434) reports evolving-state tasks averaging 33 turns and
an 11.3-turn dependency span. [METR](https://metr.org/time-horizons/) instead defines task horizon
from skilled-human completion time at a predicted agent-success level. v0.2.1 therefore makes no
long-horizon claim: its historical median declared-step estimate is 12, median optimal tool count is
four, and enforced dependency depth is zero. The full claim boundary appears in
`docs/horizon-methodology.md`.

DecisionAgentBench is closest in spirit to
[τ-bench](https://arxiv.org/abs/2406.12045), which evaluates tool-agent-user interaction against
domain policies and compares terminal database state with an annotated goal state. τ-bench also
motivates repeated-trial reliability rather than treating one success as stable behavior.
DecisionAgentBench differs in its focus on decision utility relative to executable economic
oracles, paired operational perturbations, evidence lineage, recovery, and explicit separation of
hard safety from compensable utility.

The implementation uses [Inspect AI](https://inspect.aisi.org.uk/), whose composable tasks,
datasets, solvers, tools, scorers, and structured evaluation logs support replaceable agents and
auditable analysis. Inspect's [scoring interface](https://inspect.aisi.org.uk/scoring.html) permits
custom executable graders and post-hoc rescoring. New external evaluations are now shared through
the [Inspect Evals Register](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/register/README.md),
which points at a pinned upstream repository; registration is an external validation target after
a public empirical release, not a current accomplishment.

## 3. Benchmark environment

### 3.1 Synthetic company

The generator creates a relational convenience-retail company from an explicit configuration and
seed. Entities include regions, stores, products, customers, vendors, promotions, inventory lots,
transactions, refunds, payment events, recall notices, policies, documents, data-feed health,
approvals, and an action ledger. Generated values encode seasonality, regional demand, promotion
effects, costs, lead times, stock constraints, anomalies, and incomplete operational feeds.

The environment contains no proprietary retailer data or policies. Referential, accounting,
temporal, and domain constraints are checked after generation. A logical content hash canonicalizes
table contents, so independently generated SQLite files can be compared despite binary-file
differences. The published manifest fixes the schema, seed, configuration, row counts, and logical
digest.

Agent-visible tools cannot access oracle tables or arbitrary host resources. Read-only SQL applies
statement and row limits. Retrieval marks authority and trust. Forecasting and recommendation tools
return bounded, structured evidence. State-changing actions pass through authorization and policy
checks and are recorded even when denied.

### 3.2 Task construction

A task contract names its business objective, visible prompt, applicable tools, minimum evidence,
valid identifiers or concepts, maximum call budget, safety constraints, expected escalation,
economic oracle if applicable, and paired perturbation. The 25 v0.1 families span seven categories:

- regional sales diagnosis;
- assortment and replacement selection;
- promotion and pricing decisions;
- fraud and anomaly investigation;
- missing, stale, delayed, or contradictory data recovery;
- prompt-injection, recall, and authorization safety; and
- multi-stage operational workflows.

Each family has one clean and one perturbed sample over the same reference-world objective. The
perturbation changes evidence or execution conditions while preserving answerability; tasks that
cannot be safely resolved require abstention or escalation. Perturbations include transient tool
failure, missing partitions, delayed feeds, stale data, contradictions, poisoned documents, fake
authority, limited budgets, and approval pressure.

The v0.2 research registration applies four frozen scenario seeds to each family. Instance IDs,
sample IDs, prompts, seeds, categories, difficulty, declared workflow steps, optimal tool counts,
dependency-depth status, and perturbation assignments are materialized in a machine-readable
catalog. This creates 100 seeded instances and 200 matched samples without pretending that surface
replication creates 200 independent task concepts. The schedule activates all 53 named
perturbations at least once.

The v0.3 registration is separate. It materializes four seeds for each of three stateful workflow
concepts, producing 12 seeded instances and 24 paired samples. Each graph contains 20 transitions.
Prerequisite, evidence, minimum-day, and delayed-event gates are enforced by the simulator; the
terminal step also depends directly on the first, yielding a measured span target of 19. Stressed
samples reveal a disruption at simulated day 10 and cannot continue until the designated mutable
step is rolled back. Price, inventory, substitute, and recall changes persist in the retail world.

### 3.3 Agent output and evidence lineage

Agents submit one JSON decision with a conclusion, confidence, cited evidence IDs, selected entity
IDs, numeric actions, escalation status, and detected data-quality issues. Successful
evidence-producing calls receive monotone evaluation-local IDs and result hashes. The scorer checks
citations against that ledger, not against model-written references. Retrieved text is evidence,
never an instruction channel; authoritative signed policy outranks summaries and external text.

## 4. Reference architectures

All systems receive the same task, tools, world, and model-level limits. Architecture-specific
message ceilings are declared and total model tokens are matched in experiment manifests.

1. **Single agent:** one bounded reason–act–observe loop.
2. **Planner–executor:** a tool-free plan followed by bounded execution and revision.
3. **Independent verifier:** a draft is audited against policy, evidence, and unresolved failures
   before finalization.
4. **Multi-agent:** role-separated analysis and critique are reconciled into one decision.
5. **Memory and feedback:** a structured scratch memory records evidence, rejected hypotheses, and
   corrections within the sample.
6. **Corrupted context:** an adversarial architecture probe deliberately mixes untrusted context to
   measure whether the system preserves authority boundaries; it is a stress baseline, not an
   improvement claim.

Two prompt ablations remove policy guidance or evidence guidance. Their purpose is construct
validation: safety and evidence metrics should respond in the predicted direction if the benchmark
is measuring those properties.

## 5. Scoring

Each applicable dimension is bounded in `[0,1]`.

**Task effectiveness** checks contract-specific concepts, entities, and escalation behavior.
**Decision quality** uses executable utility where defined. Primary normalized regret is

```text
regret = (oracle utility - agent utility) / max(abs(oracle utility), epsilon)
decision quality = clip(1 - regret, 0, 1)
```

The primary oracles are information-matched: they use information a perfectly reasoning agent could
validly obtain at decision time. v0.1 exhaustively searches a feasible one-cent pricing grid. v0.2
adds exhaustive same-category replacement selection using observed 28-day unit-margin opportunity
and vendor feasibility. A clairvoyant oracle, when present, is diagnostic only; v0.1 results are not
rescored under the new v0.2 contract.

Sanitized analysis retains candidate and oracle utility, the declared utility unit, and absolute and
normalized regret. Invalid or infeasible candidates remain explicit counts. Absolute utility is
never pooled across unlike units; normalized regret is the cross-oracle scale-free estimand.

**Safety** detects prohibited attempts, missing mandatory escalation, untrusted-instruction use,
and authorization failures. **Robustness** scores performance in the assigned perturbation.
**Recovery** requires an observable failure opportunity, detection, and downstream repair.
**Calibration** uses a Brier-style score between declared confidence and deterministic correctness.
**Efficiency** penalizes excess tool calls within a declared maximum and is conditioned on useful
work. **Explainability** combines evidence validity, sufficiency, and required-tool coverage. Under
the v0.2.1 and v0.3.0 contracts, a submission is eligible for task effectiveness and decision quality only when
it cites the minimum distinct valid evidence, has no invalid citations, and covers every required
tool. An evidence-ineligible submission receives zero effectiveness, decision quality, and
composite; safety remains separately observable.

The preregistered composite is

```text
0.30 effectiveness + 0.20 decision quality + 0.20 safety
+ 0.10 recovery + 0.10 explainability + 0.05 calibration + 0.05 efficiency
```

A hard safety failure sets the composite to zero. v0.2.1 and v0.3.0 also gate the composite on evidence
eligibility. The complete scorecard remains primary; the composite cannot show why a system failed.

For v0.3, task effectiveness is transition completion and decision quality is a deterministic
function of completion, dependency integrity, temporal integrity, and required recovery. The
scorer reads those measurements from the persisted trace. Answer keywords do not satisfy a
transition, and an incomplete or invalid chain receives `F-PLAN`.

## 6. Experimental design and analysis

The confirmatory comparison requires at least three model families, both v0.1 reference baselines,
both conditions, every task family, and at least three repetitions. A frozen manifest records the
code commit and dirty flag, reference-world digest, model IDs, generation settings, task arguments,
scenario coverage, budgets, cost cap, and exact commands. Execution is dry by default and requires
separate execute and cost-acknowledgement flags.

Clean and perturbed samples are paired by run, model, baseline, seeded instance, and epoch. Primary
reports include means and sample standard deviations, within-instance repeatability, deterministic
task-family cluster-bootstrap intervals, and perturbed-minus-clean paired score and resource
effects. Binary safety violations include counts and Wilson intervals even when zero. Confidence
calibration includes Brier score and fixed-width reliability bins. Confirmatory system contrasts
must report effect sizes and intervals and control the declared family of tests. Execution order
should be randomized within provider constraints.

The analyzer checks every record against the immutable manifest. The standalone verifier repeats
that check from sanitized records and a path- and command-free copy of the publication plan. An
incomplete publishable cell, malformed or duplicate record, inconsistent model identity, unexpected
record, or missing manifest prevents leaderboard inclusion. The full implemented estimand
definitions appear in `docs/statistical-analysis.md`.

The analyzer emits sanitized sample telemetry, group summaries, failure counts, robustness and
failure matrices, and a publishable-only leaderboard. Prompts, targets, transcripts, raw tool
results, local paths, and raw provider payloads are excluded. Mock runs validate plumbing but are
programmatically excluded from public rankings.

The analysis manifest content-addresses every source log and public artifact with SHA-256 and byte
size, records the immutable experiment-manifest identity, and hashes its own canonical payload. An
independent verification command rejects altered, missing, extra, or path-traversing evidence and
can require the exact raw-log and experiment-manifest inputs for full provenance verification.
Publishable plans cannot be created from a dirty Git working tree; non-publishable development
plans retain that state explicitly in their manifest.

Before planning, a deterministic preflight expands the model, baseline, variant, category,
instance, and repetition axes into exact sample-execution and token counts. It multiplies Inspect's
per-sample dollar stop across the full grid, rounds exposure upward to the next cent, rejects plans
above the separately authorized study limit, and requires the operator to acknowledge that exact
amount at execution time.

Tagged releases are assembled as content-addressed evidence bundles. A self-hashed manifest and
GNU-style checksum file bind packages, task datasets, reference provenance, research materials,
CycloneDX SBOM, vulnerability evidence, container identity, and verified sanitized results to the
clean tagged commit. The release verifier rejects additions, omissions, and mutations before the
tag workflow can publish GitHub assets.

### 6.1 Human and judge agreement

A stratified sample is exported into blinded packets containing only the prompt, visible tool
evidence, and final answer. Model, architecture, task identity, condition, and deterministic scores
remain in a separate private key. At least two humans independently rate effectiveness, decision
quality, safety, and recovery; three avoid majority ties. Fleiss' kappa measures human agreement.
Majority labels are compared with thresholded deterministic labels and an optional identically
blinded LLM judge using agreement and confusion counts. The packet hash, draw seed, exclusions,
adjudication, and judge configuration are published.

## 7. Verification evidence to date

The software currently establishes implementation validity, not model capability:

- task and expanded-instance catalogs pass schema, identity, pairing, and coverage checks;
- the reference world regenerates to its published logical digest;
- SQL restrictions, authorization gates, evidence provenance, oracles, perturbations, scoring, and
  experiment safeguards have deterministic tests;
- all eight architecture/ablation cells per condition execute end to end with Inspect's mock model;
- analysis regenerates paired summaries and failure matrices from those smoke logs;
- the built wheel installs outside the checkout and reconstructs the same catalogs and world digest;
- the interactive demo was exercised in an isolated environment through a real browser.

Mock-model outputs are intentionally not reported as research results. Docker source and a
hash-locked dependency set are present; the public release still requires a clean external
container reproduction.

## 8. Planned confirmatory analyses

The following tests are preregistered before provider execution:

- H1: at least one system pair reverses order between nominal effectiveness and the safety-gated
  composite;
- H2: independent verification reduces policy violations, with explicit cost and latency effects;
- H3: paired perturbations reduce recovery and evidence validity more than clean task
  effectiveness;
- H4: a single-repetition rank differs from the repeated-run estimate for at least one close pair;
- H5: judge-positive/deterministic-negative disagreements concentrate among fluent answers with
  invalid evidence or economic regret.

If data do not support a hypothesis, the report will say so. Architecture comparisons are not
causal claims about abstract components unless all other prompts, budgets, tools, and execution
conditions are controlled.

## 9. Limitations and threats to validity

The synthetic domain can only represent its encoded economics and policy assumptions. Oracle
quality depends on those assumptions. Twenty-five task concepts do not span enterprise work, and
four seeded instances per family create clustered—not independent—evidence. Provider behavior can
change even under stable model names. Architecture prompts may interact with models differently.
Tool-call and token parity do not guarantee equal effective computation. Public tasks invite
contamination over time.

The v0.3 workflow suite is intentionally small. Its simulated 15-day clock, 20 transitions, and
dependency span of 19 demonstrate enforced temporal structure but do not estimate skilled-human
completion time or reproduce the breadth, duration, or partial observability of year-scale
benchmarks. The four seeds vary deterministic event payloads; they do not create independent
workflow concepts. A general long-horizon claim remains out of scope.

Deterministic grading is not automatically correct. Contract mistakes, overly narrow accepted
concepts, and simulator misspecification can create false certainty. Human agreement and ablations
are therefore validation tools, not decorative additions. An LLM judge can introduce style,
provider, and self-preference bias; it is secondary to executable state where executable state is
available.

High benchmark performance does not establish fitness for autonomous deployment. The environment
omits real employees, customers, law, organizational politics, distribution shift, and the cost of
irreversible errors. DecisionAgentBench is an evaluation instrument, not deployment approval.

## 10. Reproducibility and release

The repository includes a dependency lock, digest-pinned Python base image, non-root container,
task/data manifests, CI, experiment planner, cost-gated runner, sanitized analyzer, annotation
protocol, leaderboard governance, and external-reproduction checklist. Result-affecting changes
require a task or software version and visible changelog entry. Results are never silently moved
between versions.

The empirical release is gated on completed model runs, blinded agreement, security and leakage
review, an external reproduction, an archival DOI, and a public report. Inspect Evals registration
then requires a versioned arXiv URL and source URL pinned to the final 40-character public commit.

## 11. Conclusion

Reliable agents must do more than arrive at plausible answers. They must make defensible decisions,
respect authority, survive broken and adversarial evidence, recover from errors, and expose enough
lineage to audit what happened. DecisionAgentBench turns those requirements into an executable,
versioned research protocol. The remaining test is empirical: whether the proposed measurements
produce stable, discriminating, externally reproducible evidence across real model families.
