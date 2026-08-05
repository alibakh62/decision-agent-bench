# v0.5 statistical power and study-design audit

This document records the implemented DecisionAgentBench v0.5 power analysis. It answers a narrow
question: under explicit variance and missingness assumptions, how precisely can the registered
task-family population estimate the proposed architecture contrasts?

It does **not** establish that the historical score dimensions measure the intended constructs.
The merged measurement-validity audit describes the required v0.4 redesign, but the repository
still contains the historical lexical scorer. Consequently, the v0.5 report keeps publication-scale
execution blocked even when a statistical power gate passes.

## Reproduce the report

```bash
decision-agent-bench simulate-power \
  configs/power/v0.5-initial.json \
  results/design/v0.5-initial-power.json

decision-agent-bench verify-power \
  results/design/v0.5-initial-power.json \
  --design configs/power/v0.5-initial.json

decision-agent-bench simulate-power \
  configs/power/v0.5.json \
  results/design/v0.5-power.json

decision-agent-bench verify-power \
  results/design/v0.5-power.json \
  --design configs/power/v0.5.json
```

Both the initial three-confirmatory-contrast design and the revised design are retained with their
reports. This makes the exploratory reclassification auditable instead of overwriting the failed
preflight. The simulator uses only Python's standard library, a fixed seed, and 4,000 Monte Carlo
draws. Repeating either command with the same code and design produces the same statistical fields
and digest.

## Candidate grid

| Quantity | v0.5 candidate |
| --- | ---: |
| Fixed model-family blocks | 3 |
| Architectures | 4 |
| Variants | 2 |
| Independent task families | 25 |
| Seeded instances per family | 4 |
| Seeded instances | 100 |
| Paired clean/perturbed samples | 200 |
| Repetitions | 3 |
| Total sample executions | 7,200 |
| Per-sample cost ceiling | $0.25 |
| Whole-study cost ceiling | $1,800 |

The four candidate architectures are `single_agent`, `planner_executor`,
`independent_verifier`, and `memory_feedback`. The previous eight-baseline template remains useful
for historical reproduction. `multi_agent` is removed from the candidate paid grid because its
incremental hypothesis does not justify its extra cost before a discrimination pilot. The
`corrupted_context`, `no_policy_prompt`, and `no_evidence_prompt` conditions remain validation
probes, not architecture candidates.

The 25 task families—not the 100 instances, 200 samples, 7,200 executions, or 4,000 simulation
draws—are the independent units for the intended task-population inference. The three model
families are fixed blocks; the analysis does not generalize statistically to all possible models.

## Data-generating assumptions

Each simulated score contains a task-family effect, seeded-instance effect, architecture-by-family
effect, architecture-by-model-block-by-family effect, architecture-by-variant-by-family effect, and
trajectory noise. Clean and perturbed trajectory errors are generated as correlated Gaussian
draws. Missing observations are sampled independently, and all available observations are
aggregated within task family before inference.

| Assumption | Value |
| --- | ---: |
| Task-family standard deviation | 0.18 |
| Architecture × family standard deviation | 0.08 |
| Architecture × model block × family standard deviation | 0.06 |
| Architecture × variant × family standard deviation | 0.05 |
| Instance standard deviation | 0.08 |
| Trajectory standard deviation | 0.16 |
| Clean/perturbed correlation | 0.60 |
| Missingness probability | 0.02 |

These are planning assumptions, not estimates disguised as observations. A small explicitly
non-publishable pilot must replace any assumption that materially disagrees with observed family,
instance, or trajectory variance. Pilot outcomes cannot be promoted to benchmark comparisons.

## Estimator and multiplicity

The simulator computes architecture differences within every task family after averaging the
prespecified model blocks, instances, repetitions, and relevant variants. The test statistic is the
mean family contrast divided by its across-family standard error.

Confirmatory inference uses a single-step Monte Carlo max-|t| threshold. For every null draw, the
largest absolute statistic across the confirmatory hypothesis family is retained; its 95th
percentile is the simultaneous critical value. The realized null family-wise error in the committed
run is 0.05025. Exploratory contrasts use a per-contrast Monte Carlo threshold and carry no
family-wise error guarantee.

MDE is the smallest signed shift achieving the target 80% simulated detection probability under
the prespecified critical value. Interval widths are the median simultaneous width across simulated
draws. They are conditional design quantities, not confidence intervals around real model results.
All effects, MDEs, and widths are absolute changes on the `[0,1]` score scale; `0.10` means ten
percentage points, not a standardized effect size.

## Results and decision

The initial design treated all three contrasts as confirmatory. With max-|t| correction, the two
0.08 effects reached only 61.73% and 62.68% power, while the 0.10 recovery effect reached 79.83%.
All three therefore missed the 80% threshold. Following the preregistered decision rule, the first
two were relabeled exploratory and the design was rerun. This change reduced the confirmatory
family rather than pretending that seeded instances created more independent concepts.

| Contrast | Status | Smallest effect | Simulated power | 80% MDE | Median interval width |
| --- | --- | ---: | ---: | ---: | ---: |
| Planner vs. single-agent effectiveness | Exploratory | 0.08 | 0.7930 | 0.0806 | 0.1117 |
| Verifier vs. single-agent explainability | Exploratory | 0.08 | 0.7765 | 0.0824 | 0.1157 |
| Memory-feedback vs. single-agent perturbed recovery | **Confirmatory** | 0.10 | **0.9003** | 0.0849 | 0.1207 |

The exploratory rows use separate per-contrast Monte Carlo thresholds and have no multiplicity-
controlled inferential status. The confirmatory row uses the max-|t| threshold for the final
confirmatory family.

The reduced multiplicity burden raises recovery power above the threshold. The final candidate
design therefore satisfies the statistical rule: its sole confirmatory contrast has at least 80%
simulated power, while the other proposed comparisons are explicitly exploratory. The configured
$1,800 exposure also fits the $1,800 hard ceiling.

The grid is nevertheless **not authorized or fully frozen**. The machine-readable report has
`publication_scale_run_authorized: false` because the required measurement-validity implementation
has not passed. Current provider model IDs and observed pilot variance must also be bound before any
paid manifest is created.

## Updating assumptions from a pilot

1. Run only an explicitly non-publishable development manifest.
2. Estimate variance separately at the task-family, seeded-instance, and repeated-trajectory levels.
3. Estimate clean/perturbed correlation and missingness without inspecting architecture outcomes as
   confirmatory results.
4. Update only the documented assumption fields in `configs/power/v0.5.json`.
5. Regenerate and review the content-addressed report.
6. Increase distinct families, reduce the confirmatory family, or keep underpowered comparisons
   exploratory if the power rule no longer passes.

Changing assumptions, endpoints, contrasts, multiplicity, or the grid changes the design digest and
requires review before execution.

## Interpretation boundary

- Simulated power is conditional on assumptions; it is not a guarantee about realized data.
- A high powered test can precisely estimate an invalid metric. Construct validity remains upstream.
- The Gaussian planning model approximates bounded benchmark scores; a pilot should test whether
  strong ceiling/floor behavior requires a binary, ordinal, or otherwise bounded simulation.
- Task-family generalization is limited to the registered concepts until v0.8 adds genuinely new
  families on the v0.7 closed-loop world.
- Exploratory comparisons must be labeled as such regardless of their observed p-values.
