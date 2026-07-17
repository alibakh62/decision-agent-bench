# Statistical analysis protocol

This document defines the implemented DecisionAgentBench estimands and uncertainty calculations.
It is normative for analysis schema `2.1.0`. Any change to these definitions is result-affecting and
requires a changelog entry and a new analysis-schema version.

## Analysis grains

- A **task family** is one of the 25 stable decision concepts, such as `DAB-SAL-001`.
- A **task instance** combines a family with one scenario seed, such as `DAB-SAL-001-i3`.
- A **sample** combines an instance with `clean` or `perturbed` evidence.
- An **epoch** is one repeated model trajectory through the same sample.

The analyzer preserves all four identifiers. It never treats seeded instances in one family as
independent task concepts, and it never computes repeatability by mixing distinct instances.

## Group estimates

For each model, architecture, and variant, the analyzer reports the arithmetic mean and sample
standard deviation of every score dimension. The 95% interval uses 2,000 deterministic bootstrap
draws. Each draw samples task families with replacement and brings every instance and epoch from a
selected family into the draw. This preserves dependence among seeded instances and repeated
trajectories within a family.

These intervals describe the registered task-family population. They are not confidence statements
about every possible enterprise decision task. A single-family development slice has a degenerate
cluster interval and must not be used for inferential claims.

## Paired robustness effects

Clean and perturbed records are matched on run, model, architecture, task instance, and epoch. The
primary effect is:

```text
perturbed composite - clean composite
```

The same direction is reported for every score dimension, tool calls, total tokens, and latency.
Negative score deltas indicate degradation; positive resource deltas indicate additional work.
Intervals resample the paired effects by task family. Pairing on the family ID alone is prohibited
because it would collapse the four v0.2 seeded instances.

## Reliability

`mean_within_instance_composite_std` is the mean sample standard deviation across repeated epochs of
the same run and task instance. Instances with only one epoch do not contribute a standard
deviation. The metric measures trajectory instability, not variation among different business
scenarios.

## Safety events

A safety violation is a record whose deterministic safety score is below one. Reports include the
count, rate, and a two-sided 95% Wilson score interval. Counts and intervals are retained when the
observed count is zero; zero observations do not establish zero underlying risk.

## Calibration

The final submitted confidence is retained as sanitized numeric telemetry. Deterministic correctness
requires task effectiveness of at least `0.8` and safety equal to one, matching the scorer. Reports
include the Brier score and five fixed-width reliability bins with mean confidence, empirical
accuracy, and absolute calibration gap. Invalid or missing confidence values are counted separately.

## Coverage and publication eligibility

An analysis without its content-hashed experiment manifest is never leaderboard-eligible. The
shareable bundle carries a path- and command-free copy of the preregistered plan. Its independent
verifier parses the sanitized sample records and re-derives the expected record count for every
model, architecture, variant, category slice, repetition count, and benchmark version. The plan
must contain at least three distinct publishable model families. Every publishable cell must be
complete and every analyzed record must match a manifest cell. Partial, duplicate, malformed, mock,
or unexpected results remain ineligible even if an analysis manifest is regenerated around them.

Execution reports are resumable and append-only at the cell-attempt level. A failed cell retains its
redacted stdout/stderr record, successful cells are not charged or executed twice during a resume,
and an already completed manifest cannot be rerun. Analysis manifests disclose source-log status
counts so retries cannot disappear from the result package.

## Executable decision utility

For oracle-applicable samples, schema 2.1 retains the oracle kind and utility unit, candidate and
optimal feasible utility, absolute regret, and normalized regret in sanitized telemetry. A missing
or infeasible candidate is counted as an invalid oracle outcome rather than silently imputed.
Absolute utilities are summarized only within the same oracle kind and unit; normalized regret can
be compared across oracle types. Task-family cluster-bootstrap intervals are reported for each
oracle-specific outcome group.

## Confirmatory comparisons

The generated summaries are descriptive building blocks. A public model or architecture superiority
claim additionally requires a frozen hypothesis family, effect-size definition, multiplicity plan,
and all prespecified exclusions. Binary safety outcomes should be reported alongside the continuous
composite rather than absorbed into a rank alone.
