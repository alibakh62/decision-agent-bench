# Leaderboard governance

The DecisionAgentBench leaderboard is an evidence registry, not a marketing ranking. Entries must
be reproducible, comparable, and attributable to a frozen benchmark version.

## Admission requirements

A public entry must include a clean commit, immutable experiment manifest, exact model identifier
and access date, both paired variants, every task in the claimed suite, every required baseline,
at least three repetitions, matched limits, and sanitized sample telemetry. The analysis manifest
must verify source-log hashes. Mock models, development subsets, unreviewed prompt modifications,
and runs with missing cells do not enter the primary table.

The planner refuses to create a publishable manifest from a dirty Git working tree. This makes the
recorded source commit a complete code identity rather than a partial description of local state.

Self-reported submissions are welcome through a GitHub issue. Maintainers rerun the manifest and
analysis checks before merging. Provider-hosted models may be reproduced through the same API or,
when that version is no longer available, listed as historical and non-reproducible.

Every entry's analysis manifest must bind the complete raw-log set, immutable experiment manifest,
and all generated public artifacts by SHA-256 and byte size. Maintainer admission runs
`verify-analysis --require-sources`; a standalone public mirror must at minimum pass artifact-bundle
verification. Added, missing, or modified files invalidate the entry until it is regenerated.

## Ranking and uncertainty

The default table orders eligible systems by the gated composite, then safety, then model ID. Every
row also displays sample count, safety, robustness, within-task variability, and token use. A hard
safety violation cannot be offset by higher economic utility. Confidence intervals and paired
effects belong beside point estimates; overlapping intervals are not a hypothesis test.

Official comparisons must report the complete scorecard. Teams may publish alternative rankings,
but they must not call them the primary DecisionAgentBench leaderboard.

## Versioning, corrections, and conflicts

Results never migrate silently across task, simulator, scorer, or protocol versions. Material
changes create a new leaderboard namespace. Discovered grader defects trigger a visible correction
notice, affected rows are marked, and original artifacts remain archived.

Submitters disclose employment, funding, and model-provider relationships. A maintainer with a
material conflict cannot be the sole reviewer of that entry. Appeals are decided from artifacts
and protocol text; model reputation is not evidence.

## Security and privacy

Only synthetic benchmark evidence and sanitized telemetry may be published. API keys, raw provider
payloads, hidden oracle state, annotation re-identification keys, local paths, and personal data are
prohibited. Suspected leakage or contamination should be reported privately under `SECURITY.md`.
