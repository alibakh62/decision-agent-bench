# Why Task-Success Rate Can Hide Catastrophic Agent Failures

**Research article draft — empirical tables are intentionally withheld until the preregistered
multi-model run is complete.**

A task-success number answers a narrow question: did the agent reach a recognizable endpoint? For
consequential decisions, that endpoint is often the least controversial part of evaluation. The
harder question is how the agent got there and what else it changed.

Consider an agent asked to recommend a promotion. It selects a product, produces a discount, and
writes an executive explanation. A conventional exact-match or model-judge grader might call the
task complete. Yet four materially different trajectories can share that outcome:

1. the promotion increases contribution margin within authority;
2. it increases unit volume but destroys margin;
3. it is economically reasonable but exceeds the agent's discount authority; or
4. it is reasonable and authorized, but justified with evidence the tools never returned.

Collapsing these cases to one bit makes a high score compatible with an unsafe system.

## The measurement problem

Task success is not useless. It is an important component of effectiveness. The problem is using it
as a sufficient statistic for a process whose losses are asymmetric. A small number of severe
policy violations can matter more than many routine successes. Likewise, two agents with equal
completion rates can impose very different economic regret.

DecisionAgentBench separates the endpoint into a constrained scorecard:

- **effectiveness:** did the operational objective succeed?
- **decision quality:** how much utility was retained relative to an information-matched oracle?
- **safety:** were policy and authorization boundaries respected?
- **explainability:** do cited evidence IDs exist and support the required evidence path?
- **recovery:** did the agent repair its reasoning after an observable failure?
- **robustness, calibration, and efficiency:** did the decision survive perturbation, express
  appropriate confidence, and use bounded resources?

The benchmark reports every dimension and a preregistered composite. A hard safety violation sets
that composite to zero. This is a normative choice, and it is made explicit: prohibited action is a
constraint, not a small penalty that enough revenue can offset.

## A falsifiable experiment

The article's central hypothesis is a rank reversal: at least one evaluated system pair will be
ordered differently by nominal effectiveness and by the safety-gated composite.

The confirmatory design fixes 25 task families, matched clean and perturbed conditions, two
reference architectures, at least three current model families, and at least three repetitions.
All systems receive the same tools, task instances, and model-level budgets. A content-hashed
manifest is frozen before execution. Mock models are excluded.

For each model–architecture pair, the primary table will contain:

| System | n | Effectiveness | Decision quality | Safety | Evidence | Composite | Hard violations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| _pending_ |  |  |  |  |  |  |  |

The analysis will compute pairwise differences over matched task, condition, and repetition. A
task-family cluster bootstrap will preserve the fact that seeded instances from one family are not
independent concepts. Rank reversal will be reported as an effect with uncertainty—not as a
dramatic anecdote from one trace.

## What counts as a catastrophic failure?

The term should not be stretched to mean “low score.” In this study it refers to a prespecified
hard event:

- a prohibited state-changing attempt;
- an action beyond the agent's authority without required approval;
- failure to escalate an active recall or equivalent mandatory safety condition; or
- following operational instructions from explicitly untrusted retrieved content.

The simulator records attempted and accepted actions separately. This matters: a system that blocks
an unsafe tool call prevents real state change, but the agent still demonstrated unsafe intent. The
report will distinguish proposed, attempted, denied, and executed violations.

## Why evidence lineage belongs in the same analysis

Fluent explanations make weak decisions look coherent. DecisionAgentBench assigns IDs only to
successful evidence-producing tool calls, hashes their results, and asks the final answer to cite
those IDs. The scorer can therefore identify fabricated citations without asking another model.
Required-tool coverage measures whether the agent consulted the evidence class the task demands.

This does not prove every sentence in a rationale. It establishes a lower bound: cited evidence
existed in this trajectory and the agent did not skip mandatory sources. A blinded human study then
tests whether the visible evidence actually supports the conclusion and whether deterministic
labels are too strict or too permissive.

## How to interpret a rank reversal

A reversal would not show that the lower-effectiveness system is universally better. It would show
that “better” depends on the loss function and that endpoint-only evaluation concealed a material
trade-off. The right response is to publish the scorecard, failure counts, and uncertainty—not to
replace one opaque leaderboard scalar with another.

No reversal would also be informative. It could mean current systems fail uniformly, the tasks do
not discriminate the intended constructs, or the composite weights add little beyond
effectiveness. The ablations and human study help separate those explanations.

The practical standard is simple: if a benchmark can declare an agent successful while hiding an
unauthorized or economically dominated decision, the benchmark has measured task completion—not
decision reliability.
