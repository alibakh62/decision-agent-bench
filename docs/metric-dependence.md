# Metric-dependence audit

DecisionAgentBench v0.5 separates two questions that are often conflated:

1. **Structural dependence:** do two metrics share inputs or definitions by construction?
2. **Empirical dependence:** how strongly do their observed values move together, with uncertainty?

A high correlation triggers a construct review. It does not automatically mean that two metrics
should be merged, and a low correlation does not prove that they measure distinct constructs.

## Structural audit of the historical scorer

| Metrics | Implemented relationship | Consequence |
| --- | --- | --- |
| Composite and component scores | Historical composite is a gated weighted function of effectiveness, decision quality, safety, recovery, explainability, calibration, and efficiency | Correlation with the composite is expected and cannot validate a component |
| Decision quality and effectiveness | Decision quality defaults to effectiveness when no economic/workflow oracle applies | Identity rate and oracle applicability must accompany their correlation |
| Robustness and recovery | Robustness equals recovery for perturbed samples and is fixed at one for clean samples | These are not independent historical measurements |
| Efficiency and effectiveness | Efficiency is multiplicatively scaled by effectiveness | Part of their empirical association is guaranteed by construction |

These findings are version-specific. The future typed scorer must publish a new structural map
rather than inheriting these relationships silently.

## Empirical command

Run the audit on the sanitized JSONL produced by `analyze-results`:

```bash
decision-agent-bench metric-dependence \
  results/generated/<run-id>/samples.sanitized.jsonl \
  results/generated/<run-id>/metric-dependence.json

decision-agent-bench verify-metric-dependence \
  results/generated/<run-id>/metric-dependence.json \
  --samples results/generated/<run-id>/samples.sanitized.jsonl
```

The report contains Pearson and tie-aware Spearman correlations for every historical score pair,
pairwise sample count, independent task-family count, identical-value rate, and 95% whole-family
cluster-bootstrap intervals. The default bootstrap uses 2,000 draws and seed `20260717`.

Pairs whose observed Pearson or Spearman magnitude reaches 0.90 are placed in
`high_correlation_pairs`. This is a review threshold, not an automatic deletion threshold. The
report is content-addressed and binds the exact sanitized input by SHA-256.

## Current evidence status

No v0.5 empirical metric-dependence result is committed because there is no valid, complete,
non-mock pilot under the future typed scoring contract. Fabricating a synthetic “empirical” report
would obscure that fact. The implemented command and structural audit are ready; the empirical
section must be generated from a declared non-publishable pilot after the measurement-validity gate
is implemented.

Historical v0.1-v0.3 logs may still be audited for diagnostic purposes, but the resulting
correlations describe the known lexical scorer and cannot validate future endpoints.

## Review procedure

For every flagged pair:

1. inspect the structural map before the coefficient;
2. stratify by variant and task applicability where definitions change;
3. inspect family-level scatter and ceiling/floor mass;
4. compare Pearson and Spearman estimates and their cluster intervals;
5. decide whether the relationship reflects duplication, a causal dependency, shared difficulty,
   gating, or a small number of task families;
6. document any metric change as a result-affecting schema revision.
