# Business Regret as an Agent Metric—and When a Judge Disagrees

**Research article draft — no judge or frontier-model result is claimed before the blinded study.**

Open-ended business decisions are attractive targets for model judges. A judge can read a rationale
and decide whether it sounds complete, thoughtful, or persuasive. The weakness is that economic
quality is often executable. When a simulator can compute feasible alternatives, asking another
model to infer the outcome from prose adds variance where a direct calculation is available.

DecisionAgentBench uses regret to connect a decision with its opportunity cost:

```text
normalized regret = (oracle utility − agent utility)
                    / max(|oracle utility|, epsilon)
decision quality = clip(1 − normalized regret, 0, 1)
```

The point is not that every business objective reduces to money. It is that a declared objective
should have a declared outcome function. Promotion tasks can combine contribution margin and
constraints. Assortment tasks can value demand, margin, shelf capacity, and vendor feasibility.
Inventory tasks can trade service level against holding and shortage costs. Safety remains a hard
constraint rather than another utility term.

## Which oracle?

An unfair oracle can make regret meaningless. A clairvoyant optimizer that sees future realized
demand will dominate an agent that only sees decision-time evidence. DecisionAgentBench therefore
distinguishes:

- **information-matched oracle:** best feasible action using information the agent could validly
  obtain at decision time;
- **clairvoyant oracle:** best action with future realization, reported only as an upper bound; and
- **policy baseline:** a deterministic rule representing a simple organizational default.

Primary regret uses the information-matched oracle. Small cases are exhaustively enumerated to
test optimality and tolerance. Tool failures do not grant the oracle hidden future knowledge; the
paired analysis separately measures whether the agent recovers access to valid decision-time
evidence.

## Why a fluent answer can be economically wrong

Language rewards coherence. A detailed promotion narrative can emphasize unit lift and customer
engagement while omitting margin. A product-replacement recommendation can cite demand while
ignoring shelf capacity or vendor lead time. A judge that sees prose but not an executable feasible
set may prefer the more polished answer.

This motivates a disagreement study rather than a declaration that either judge is infallible.
The preregistered hypothesis is that judge-positive/deterministic-negative cases concentrate among
fluent answers with invalid evidence or high regret.

## Blinded three-way validation

Completed Inspect logs are exported into packets with opaque IDs. Each packet contains the task
prompt, visible tool evidence, and final answer. Model, architecture, task ID, clean/perturbed
condition, and deterministic labels remain in a separate private key.

At least two humans—and preferably three—rate effectiveness, decision quality, safety, and recovery
using binary rubric anchors. An LLM judge receives the identical packet and rubric in a fresh
context. The analysis reports:

- Fleiss' kappa among human raters;
- deterministic-versus-human agreement and confusion counts;
- LLM-judge-versus-human agreement and confusion counts; and
- LLM-judge-versus-deterministic agreement and confusion counts.

Ties and missing labels are excluded transparently. Judge model ID, provider, date, prompt hash,
settings, and cost are part of the study record.

| Dimension | Human κ | Deterministic ↔ human | Judge ↔ human | Judge ↔ deterministic |
| --- | ---: | ---: | ---: | ---: |
| _pending_ |  |  |  |  |

The deterministic threshold is frozen before unblinding. Sensitivity analysis may show alternative
thresholds, but it cannot replace the primary analysis after outcomes are known.

## Reading the confusion matrix

A false positive for the LLM judge is not automatically proof that the judge failed. It identifies
a case for adjudication. The deterministic contract may have omitted an acceptable synonym, used
the wrong feasibility set, or encoded a disputable utility. Conversely, a human rater may reward a
plausible rationale while missing a policy or numeric constraint.

Disagreements should be sampled by type and reviewed against the raw synthetic evidence and oracle
implementation. The report will classify at least:

- fluent but economically dominated;
- correct decision with unsupported or fabricated evidence;
- conservative escalation that sacrifices utility appropriately;
- deterministic contract false negative;
- judge style or verbosity preference; and
- genuinely ambiguous task construction.

Ambiguous tasks remain in the audit trail and are corrected only in a new benchmark version.

## Regret is necessary, not sufficient

Economic regret cannot judge whether an agent violated authority, trusted an injected document, or
communicated a harmful accusation. Nor does a low-regret choice prove causal reasoning; the agent
may have guessed. That is why regret sits beside safety, evidence lineage, calibration, recovery,
and repeated-run reliability.

The strongest evaluation uses executable outcomes where the world makes them executable, human
judgment where interpretation is unavoidable, and model judges as scalable but validated tools.
The hierarchy matters. If a database and oracle can establish that a recommendation destroyed
margin, eloquence should not overrule arithmetic.
