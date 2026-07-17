# Security and release-integrity model

DecisionAgentBench executes untrusted model output against a synthetic environment. Its primary
security goals are to prevent host command execution, credential disclosure, hidden-oracle leakage,
unauthorized state changes, and misleading publication of incomplete results.

## Trust boundaries

- Model text, retrieved external documents, SQL strings, and proposed actions are untrusted.
- Agent-facing SQL is single-statement, read-only, row-bounded, and authorized table by table.
- Oracle parameters, grading contracts, and annotation re-identification keys are evaluator-only.
- State changes use typed methods with policy checks, approval IDs, and an immutable action ledger.
- Experiment credentials come from process environment variables and are never accepted in
  manifests or model arguments.
- The public analyzer excludes prompts, targets, transcripts, raw tool results, provider payloads,
  temporary paths, and annotation keys.

## Automated controls

`decision-agent-bench audit-release` performs deterministic local checks over task/reference-world
reproduction, agent/oracle separation, high-confidence credential patterns, data provenance,
licensing, and public research artifacts. It can ingest a JSON `pip-audit` report and fails on every
known vulnerability that lacks a reviewed OpenVEX statement. Supplying `--container-image` also
records the image ID, default reference-world check, and non-root runtime identity.

GitHub security automation adds:

- CodeQL analysis for Python;
- full-history Gitleaks scanning;
- PyPA `pip-audit` over the hash-locked runtime dependency set;
- Dependabot updates for Python, GitHub Actions, and the pinned Docker base; and
- a weekly scheduled security run in addition to push and pull-request checks.

An audit status of `pending` is not a release pass. It means a required external fact—such as the
GitHub repository identity, clean committed state, live vulnerability response, or container
runtime evidence—has not yet been supplied.

## Current vulnerability disposition

The 17 July 2026 audit identified `CVE-2026-7246` in transitive dependency `click==8.2.1`. The fix is
Click 8.3.3, but Inspect AI 0.3.247 constrains Click below 8.2.2. The affected `click.edit()` helper
is absent from DecisionAgentBench call paths and is not called by the installed Inspect source.
Evaluated agents cannot invoke an editor or arbitrary host command. `security/openvex.json` records
the time-bounded `not_affected` assessment; CI ignores only this named advisory and must fail on any
other vulnerability. The assessment expires for review on 17 August 2026 or when upstream metadata
allows the fixed Click version.

## Residual risks

- Python and SQLite are not a hardened sandbox against a malicious maintainer or dependency.
- Provider SDKs and Inspect remain third-party code with their own update cadence.
- Static secret detection can miss novel credential formats; GitHub secret scanning should also be
  enabled when the repository becomes public.
- Prompt-injection fixtures deliberately contain hostile text. Their presence is expected, but any
  route from that text to host execution is a vulnerability.
- The Gradio lab is designed for loopback use. Exposing it to an untrusted network is unsupported.

Report suspected escapes or secret/oracle disclosure through a private GitHub security advisory as
described in `SECURITY.md`.
