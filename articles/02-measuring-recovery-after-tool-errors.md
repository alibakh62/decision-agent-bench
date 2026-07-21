# Measuring Recovery After Tool Errors in Long-Horizon Agents

**Research article draft — the protocol is frozen; model results remain pending.**

Tool failure is inevitable. The useful question is not whether an agent ever receives an error; it
is whether the agent detects the failure, changes strategy, and repairs every conclusion that
depended on the bad evidence.

Many evaluations score only the final response. That makes recovery hard to distinguish from luck.
An agent can ignore a timeout, guess the correct answer, and appear robust. Another can correctly
diagnose a stale feed, refuse to invent evidence, and receive a low task-success score despite
behaving responsibly. Recovery needs its own observable contract.

## Recovery is a sequence, not a retry count

DecisionAgentBench defines a recovery opportunity as a controlled event in a paired task: a
transient failure, missing partition, delayed feed, stale table, contradiction, schema problem, or
adversarial document. The perturbed sample shares the clean sample's underlying business objective.
It remains answerable through a fallback, a validation path, or explicit escalation.

A successful recovery has three parts:

1. **detection:** the agent recognizes that evidence or a tool is unreliable;
2. **adaptation:** it changes call, source, scope, or decision strategy rather than repeating the
   same failure indefinitely; and
3. **repair:** downstream claims, confidence, and actions reflect the corrected evidence.

A repeated call is not automatically recovery. Repeating a transient request once may be sensible;
looping without adaptation is a tool-use failure. A note saying “data may be stale” is not recovery
if the final decision still treats it as current.

## Instrumenting the trajectory

The benchmark records tool name, arguments, success/error status, evidence ID, result hash,
recovery markers, approvals, and state changes. Perturbations are injected deterministically from
the sample contract. Error messages reveal enough to act but never expose hidden scorer state.

Recovery scoring combines the assigned opportunity, observable response, and contract-specific
resolution. The final JSON also includes `data_quality_issues` and an escalation flag. Those fields
do not earn credit by themselves; the trajectory and final decision must agree.

This process-aware design prevents three common false positives:

- **lucky answer:** correct endpoint without detecting the corrupted path;
- **performative caution:** mentions uncertainty while taking the same unsupported action; and
- **tool spam:** eventually obtains evidence through repeated calls without a coherent adaptation.

## The paired experiment

For every task instance, compare the clean and perturbed trajectory under the same model,
architecture, scenario seed, and repetition. The primary effect is

```text
Δ recovery-adjusted performance = perturbed composite − clean composite
```

The score is accompanied by recovery rate, effectiveness, evidence validity, tool calls, tokens,
latency, and failure types. A robust agent should not merely preserve its final answer; it should
preserve safety and evidence quality with bounded extra work.

The preregistered hypothesis is that perturbations cause a larger decline in recovery and evidence
validity than in nominal effectiveness. This would reveal cases where the agent still reaches the
answer while its process deteriorates.

| System | Pairs | Δ effectiveness | Δ evidence | Recovery | Extra calls | Δ composite |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| _pending_ |  |  |  |  |  |  |

Paired bootstrap intervals resample at the task-family level. The report will show the full
perturbation matrix, because averaging a prompt-injection failure with a harmless transient timeout
can erase the mechanism.

## Architectures under test

The single-agent and planner–executor baselines establish the v0.1 comparison. The research track
adds independent verification, multi-agent critique, and within-sample memory/feedback.

The verifier is expected to detect unresolved contradictions and policy failures but may increase
latency and cost. Memory may help avoid repeating failed calls, but poisoned context tests whether
the same mechanism preserves untrusted instructions. Multi-agent critique could surface problems
or merely consume budget. These are testable trade-offs, not architectural branding.

Two prompt ablations remove policy guidance or evidence guidance. If recovery and evidence metrics
do not respond to the evidence ablation, that is evidence against construct validity.

## The denominator problem

Recovery is undefined when no recoverable error occurred. Treating clean tasks as successful
recoveries inflates the rate; treating them as failures depresses it. DecisionAgentBench marks the
metric applicable only when the sample contract creates an opportunity. Reports must show both the
number of opportunities and the number resolved.

Infrastructure failures also need separation. A provider outage, malformed benchmark fixture, and
agent failure are different events. The runner stops on failed cells and the analysis excludes
unsuccessful Inspect logs from capability summaries while preserving them in execution reports.

## What good recovery looks like

The desired trajectory is not endless self-reflection. It is a bounded control loop: detect a
specific problem, choose a justified fallback, revalidate the decision, lower confidence or
escalate when the evidence remains inadequate, and stop.

That definition turns “resilience” from a vague impression into an auditable sequence. A system
that succeeds only when every API behaves perfectly is not a reliable agent; it is a brittle demo
with a favorable test harness.
