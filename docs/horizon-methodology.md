# Horizon methodology and claim boundary

## Current status

DecisionAgentBench v0.2.1 does **not** claim to measure long-horizon agent ability. The frozen v0.1
family specs contain a field historically named `horizon`, but those values are author-declared
workflow-step estimates. They do not enforce state transitions, measure dependency length, or
estimate how long a skilled human would need to complete the work.

The v0.2.1 instance catalog makes the distinction explicit:

| Field | Median | Interpretation |
| --- | ---: | --- |
| `declared_workflow_steps` | 12 | Historical design estimate inherited from the frozen family spec |
| `optimal_tool_calls` | 4 | Reference call-count target used by the efficiency scorer |
| `enforced_dependency_depth` | 0 | Number of required downstream state transitions that depend on earlier agent actions |
| `horizon_claim` | — | Always `not_established` in v0.2.1 |

The three workflow prompts remain useful process-planning evaluations, so v0.2.1 labels their
category `workflow_planning`. The v0.1 source retains `long_horizon_workflow` only to preserve its
published schema and historical reproducibility.

## Comparison bar

Recent benchmarks demonstrate why declared step counts are not enough:

- [RetailBench](https://arxiv.org/abs/2603.16453) evaluates agents over a 180-day retail horizon in
  a partially observable, evolving environment where pricing, replenishment, and operating effects
  accumulate.
- [YC-Bench](https://arxiv.org/abs/2604.01212) evaluates a simulated year over hundreds of turns,
  with recurring obligations, delayed feedback, and compounding consequences.
- [LongDS-Bench](https://arxiv.org/abs/2605.30434) reports evolving-state tasks with an average of
  33 turns and an average dependency span of 11.3 turns, including update, rollback,
  counterfactual, and composition operations.
- [METR's time-horizon methodology](https://metr.org/time-horizons/) defines horizon using the time
  a skilled human would need for tasks at a predicted agent success level. Human completion time is
  a task-difficulty measure; it is not interchangeable with an agent's tool-call count.

These works use different constructs, and DecisionAgentBench will not collapse them into one
number. The relevant lesson is that a horizon claim needs executable temporal or causal structure
and a stated measurement method.

## Future acceptance criteria

A future DecisionAgentBench release may use a long-horizon label only when all of these conditions
are met:

1. Tasks contain executable state changes whose effects persist across steps.
2. Later observations or valid actions depend on earlier agent decisions, not merely on prompt
   instructions to list a sequence.
3. The benchmark measures and reports dependency span, executed turns, and successful recovery
   after delayed consequences or rollback.
4. Clean and perturbed variants preserve a comparable dependency graph.
5. Any human-time horizon is based on a documented skilled-human study and is reported separately
   from agent turns and tool calls.
6. Claims are supported by non-mock runs and trace audits showing that agents actually traversed
   the intended chain.

Until those gates are satisfied, DecisionAgentBench should be described as a process-aware,
evidence-grounded, multi-tool business-decision benchmark with workflow-planning tasks.
