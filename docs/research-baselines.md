# Research baselines and preregistered comparisons

DecisionAgentBench v0.2 adds four architectures and two prompt ablations to the v0.1 single-agent
and planner-executor references. Every architecture receives the same task, tools, model, generation
settings, token limit, time limit, and per-sample cost cap. Architecture overhead remains visible in
token, latency, turn, and cost telemetry.

| Baseline | Intervention | Primary hypothesis |
| --- | --- | --- |
| `independent_verifier` | Tool user followed by an isolated audit and correction pass | Higher evidence and safety scores, with higher cost and latency |
| `multi_agent` | Independent analyst and risk pre-mortems feed a synthesis tool user | Better multi-stage effectiveness and fewer planning failures |
| `memory_feedback` | Fixed prior-failure memory plus a transcript-grounded revision | Better recovery and calibration under perturbation |
| `corrupted_context` | Untrusted retained-memory injection precedes normal execution | Lower safety/robustness unless the model resists the added context |
| `no_policy_prompt` | Removes explicit trust, approval, and guardrail instructions | More policy and security failures |
| `no_evidence_prompt` | Removes explicit evidence-collection and citation guidance | Lower evidence precision/sufficiency and explainability |

The fixed memory contains benchmark-general lessons, not task answers or hidden grading targets.
Role specialists produce hypotheses without tools; their text is not accepted as evidence. The
verifier can inspect the transcript but cannot call tools or change simulated state.

## Analysis commitments

- Primary endpoint: paired perturbed-minus-clean composite score, with the safety gate retained.
- Safety endpoint: policy/security failure probability and taxonomy counts.
- Reliability endpoint: mean within-task standard deviation across repeated epochs.
- Resource endpoints: total tokens, provider-reported cost, latency, turns, and tool calls.
- Unit of pairing: model, baseline, task family, scenario seed, and epoch.
- Minimum public run: all 200 samples, at least three repetitions, immutable manifest, and explicit
  per-sample and whole-study cost limits.

Architecture comparisons must use the same underlying model. Model comparisons must use the same
architecture and budgets. Confirmatory claims require declaring comparisons before looking at the
full results and controlling multiplicity; exploratory differences must be labeled exploratory.

The complete registered grid is encoded in `configs/experiments/v0.2.template.json`. Its preflight
contains 4,800 sample executions per enabled model, making staged budgeting and model selection an
explicit research decision rather than an incidental runner setting.
