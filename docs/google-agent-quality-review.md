# Google Agent Quality white-paper review

## Source and scope

This review covers *Agent Quality* by Meltem Subasioglu, Turan Bulmus, and Wafae Bakkali,
published in November 2025 as part of Google's agentic AI course materials. The supplied 51-page
paper is a practical architecture and operations framework, not a controlled benchmark study or a
formal statistical standard.

Its central recommendations are:

- evaluate agent quality across effectiveness, efficiency, robustness, and safety;
- start outside-in with end-to-end goal achievement, then diagnose the inside-out trajectory;
- combine automated metrics, LLM or agent judges, and human evaluation;
- make agents evaluatable by design through structured logs, causal traces, and aggregated metrics;
- distinguish operational system metrics from judgment-based quality metrics; and
- convert reviewed failures into durable regression cases through a continuous quality flywheel.

## What DecisionAgentBench already covers

DecisionAgentBench already implements or plans important parts of this framework:

- an outcome-first score hierarchy with safety as a non-compensatory constraint;
- effectiveness, efficiency, robustness, safety, recovery, evidence, and decision-utility measures;
- complete Inspect run logs, model and tool events, evidence IDs, latency, usage, and score lineage;
- a trace-first Lab that shows final results and the process that produced them;
- deterministic graders, optional blinded LLM judgment, human annotation, and agreement analysis;
- matched clean and perturbed tasks for tool failures, missing data, ambiguity, and adversarial
  context;
- cost, token, duration, failure, calibration, and uncertainty telemetry in sanitized analysis; and
- simulated approval boundaries, security checks, red teaming in the roadmap, and private/public
  artifact separation.

The paper therefore supports the project's validity-first direction. It does not repair the
historical scorer or prove that the existing tasks measure the named constructs.

## Additions adopted into the roadmap

### 1. Explicit outside-in evaluation contract

The benchmark will distinguish three layers:

1. **Eligibility and hard safety:** whether a valid, policy-compliant run exists.
2. **End-to-end outcome quality:** whether the intended business objective was achieved and what
   utility or regret resulted.
3. **Trajectory diagnostics:** why the outcome occurred, including planning, tool selection,
   arguments, result interpretation, evidence use, recovery, handoffs, and resource use.

Process quality may explain or break a tie between comparable safe outcomes, but an attractive trace
cannot compensate for a failed business outcome or a hard safety violation.

### 2. Versioned causal trace contract

Scored agents will emit or be adapted into a common event model containing run, trace, span, and
parent identifiers; timestamps; actor and role; public action intent; model and tool events; exact
typed arguments; results and errors; state mutations; evidence and action lineage; approvals;
latency; tokens; and cost. This schema supports local agents, remote services, and multi-agent
systems without requiring provider-private chain of thought.

### 3. Trajectory failure taxonomy

The construct-valid contract will distinguish at least:

- planning or decomposition failure;
- wrong, missing, redundant, or hallucinated tool selection;
- invalid tool parameterization;
- tool or infrastructure failure;
- tool-result and error-state misinterpretation;
- retrieval relevance, freshness, provenance, or grounding failure;
- repetitive loops and inefficient exploration;
- failed recovery or unjustified continuation;
- multi-agent role, handoff, communication, contention, or deadlock failure; and
- authorization, privacy, security, or safety failure.

The taxonomy describes observable behavior. It does not claim access to hidden reasoning.

### 4. Portable observability

The roadmap adds OpenTelemetry-compatible trace export and context propagation across the Lab,
Inspect, local adapters, and remote agent services. Operational metrics such as latency percentiles,
error rates, tokens, cost, and tool frequency remain separate from quality judgments such as
correctness, utility, evidence support, recovery, and safety.

Official benchmark runs require complete traces. Dynamic production sampling may be supported for
imported operational telemetry, but sampled or incomplete traces cannot enter benchmark rankings.

### 5. Evaluator triangulation

Deterministic state and policy checks remain authoritative where ground truth exists. Subjective
constructs may use blinded pairwise LLM-as-a-judge or agent-as-a-judge diagnostics, but those judges
must be tested for order, identity, self-preference, verbosity, reference leakage, and repeatability
bias and calibrated against blinded human ratings. They cannot silently override deterministic
facts, hard safety events, or human adjudication.

### 6. Reviewer workflow and quality flywheel

The Lab and annotation tooling will gain context-rich review queues, inline failure tags, and
optional user or developer feedback ingestion. A reviewed failure may become a regression case only
after adjudication, deduplication, privacy review, ambiguity review, and versioning. Public benchmark
tests, private holdouts, and product regression cases remain separate to limit leakage and benchmark
contamination.

### 7. Capture-time privacy and retention

The project already sanitizes shareable analysis artifacts. The revised plan moves privacy controls
closer to ingestion by classifying trace fields, minimizing sensitive content, redacting configured
secrets and personal data before durable storage where possible, and documenting retention and
access boundaries for raw traces.

## Recommendations modified or rejected

- **Hidden chain of thought:** not required. The benchmark evaluates public plans, action intent,
  tool interactions, state changes, and outcomes. Provider-private reasoning may be unavailable and
  should not be treated as necessary evidence.
- **Exact trajectory matching:** rejected as a general quality metric. Several action orders can be
  valid. DecisionAgentBench uses outcomes, constraints, partial orders, required evidence, and
  observable failure conditions instead.
- **LLM judge as ground truth:** rejected. Model judges are scalable diagnostics whose validity must
  be measured against independent human review.
- **User satisfaction as a universal benchmark score:** modified. Feedback is valuable for product
  regression and reviewer prioritization, but the synthetic benchmark has no authentic end user, so
  satisfaction is not a core leaderboard dimension.
- **Dynamic sampling for scored evaluations:** rejected. Reproducible benchmark studies require
  complete eligible traces; sampling belongs only to production observability integrations.

## Governing consequence

The [versioned roadmap](roadmap.md) remains validity-first. The white paper does not add another
release number, but it expands v0.6 with an outside-in evaluation and trace contract, v0.9 with
portable observability and trajectory diagnostics, and v0.10 with evaluator triangulation, reviewer
workflows, and a governed regression flywheel. The v0.11 empirical beta remains blocked until those
gates pass.
