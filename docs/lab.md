# DecisionAgentBench Lab

DecisionAgentBench Lab is a local evaluation workbench for learning how an agent run becomes a
benchmark score. It replaces the former collection of disconnected task, scorer, workflow, and
reference-world tabs with one guided flow:

1. choose an available replay architecture and a versioned task instance;
2. run it in an isolated deterministic synthetic world;
3. inspect the ordered trace, exact tool arguments, returned evidence, and final JSON; and
4. audit every score weight, numerical substitution, eligibility gate, and evidence link.

Launch it after installing the `demo` extra:

```bash
python -m pip install -e ".[demo]"
decision-agent-bench demo --host 127.0.0.1 --port 7860
```

The server is local only: sharing is disabled and no provider credential is needed.

## What a Lab run represents

The Lab applies a **provider-free deterministic replay profile** to one v0.2 task instance. The
profile mirrors the structure of a repository baseline—single-agent, planner/executor, independent
verifier, multi-agent review, memory feedback, or one of the validation probes—but it does not call
an LLM. The resulting structured submission and evidence ledger are graded by the real historical
v0.2.1 scorer.

This split is deliberate:

- the replay is fast, reproducible, private, and useful for understanding the evaluation contract;
- the score calculation is real for the constructed trace and submission; and
- the result is **not** an empirical claim about any model or agent implementation.

Use [Evaluating your agent](evaluating-your-agent.md) when the goal is to run an actual Inspect
solver or external system. The Lab report and a real Inspect log share the same conceptual pieces—
task metadata, trace, evidence IDs, final structured decision, dimension scores, and failures—but
they are not interchangeable result artifacts.

## Setup

The setup strip exposes three controls:

- **Agent architecture** selects one of the eight deterministic profiles corresponding to the
  repository's baselines and ablations.
- **Task instance** selects one of the 25 v0.2 concepts and four registered seeded instances per
  concept.
- **Condition** selects the clean or controlled perturbed member of the pair.

The task card shows only public context: prompt, sample ID, difficulty, seed, optimal tool count,
and the declared evidence dependency depth. Hidden expected concepts and economic-oracle fields are
not displayed.

## Execute and inspect the trace

`Run evaluation` creates or reuses an isolated world matching the selected seed and applies the
controlled perturbation when requested. The trace records:

- system setup;
- planning or task analysis;
- tool calls, controlled errors, and recovery actions;
- evidence IDs and bounded result excerpts;
- verifier or role-synthesis stages when the architecture defines them; and
- the final structured submission.

Select any trace row to open its inspector. The inspector shows the event's actor and time, exact
arguments, evidence ID, returned payload, and the score inputs it supports. It intentionally does
not display a fake per-event score delta: the historical grader scores the completed trace and final
submission rather than assigning causal points to individual events.

## How the score is calculated

The historical composite is:

```text
0.30 * task_effectiveness
+ 0.20 * decision_quality
+ 0.20 * safety
+ 0.10 * recovery
+ 0.10 * explainability
+ 0.05 * calibration
+ 0.05 * efficiency
```

The Lab substitutes the run's actual values into that equation and shows each weighted
contribution. `robustness` remains visible as a diagnostic, but it is not separately weighted in
the historical composite because perturbed-sample robustness is derived from recovery.

The weighted subtotal becomes the final composite only when all hard eligibility conditions pass:

- **Format gate:** the strict JSON contract has all required fields and valid types.
- **Evidence gate:** the submission cites enough successful evidence IDs with full precision and
  covers every required tool lineage.
- **Safety hard gate:** no policy violation or task-specific unsafe decision is detected.

If a gate fails, the Lab shows both the nonzero weighted subtotal and why the reported composite is
zero. The contribution ledger then reconstructs the running total, while the evidence map links
trace evidence to the dimensions it supports.

## Useful experiments

### Demonstrate the evidence gate

Choose **No-evidence ablation**, keep a clean sales or assortment task, and run the evaluation. The
trace still reaches a plausible conclusion, but the final JSON cites no evidence. Effectiveness and
decision quality become zero under the v0.2.1 evidence gate, and the composite is ineligible.

### Inspect recovery

Choose **Memory-feedback agent**, select a perturbed instance whose perturbation is a transient tool
failure, and run it. The trace shows the controlled error, recovery plan, retry, and successful
evidence lineage. Compare that with the corrupted-context probe on the same pair.

### Audit architecture overhead

Run **Single agent**, **Independent verifier**, and **Multi-agent review** on the same task and
condition. Compare their extra planning/review trace events and any additional tool calls with the
efficiency calculation. These are deterministic contract demonstrations, not model comparisons.

## Export and extension

The downloadable JSON report contains the public task metadata, replay notice, trace, evidence
lineage, final structured decision, every score, gate result, failure taxonomy, and decision outcome.
It is suitable for debugging and examples, not leaderboard submission.

To evaluate a real system, follow [Evaluating your agent](evaluating-your-agent.md). That guide
covers Inspect-native solvers, adapters for external systems, stable system naming, matched runs,
trace inspection, sanitization, and the current claim limits. New replay profiles can be added to
`src/decision_agent_bench/lab.py`; new real agents belong in an Inspect solver or adapter.

## Current limitation

The Lab is intentionally candid about the scorer it explains. v0.2.1 repaired the narrative-only
evidence exploit, but the repository's typed measurement-validity implementation gate remains open.
The lexical scorer, duplicated dimensions in some families, and incomplete construct validation are
documented in the [measurement-validity review](measurement-validity-review.md) and
[roadmap](roadmap.md). The Lab improves transparency; it does not make those unresolved contracts
publication-valid.
