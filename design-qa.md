# DecisionAgentBench Lab design QA

## Review target

- Version: v0.5.5 score-explanation usability pass
- Route: `http://127.0.0.1:7877`
- Runtime: Gradio 6.20.0 with the production Lab CSS and real Inspect execution path
- Verification viewport: 2048 × 1200 CSS pixels, device pixel ratio 2
- States reviewed: ready Lab, selected trace event with Score impact open, and Decision quality scorecard expanded

## Source truth and implementation evidence

- Evaluation-target reference:
  `/var/folders/y8/l1vtj33s14q6jbb9jlqr4tx80000gp/T/codex-clipboard-8ed4f0a4-60fb-4b04-ae1f-a051c7eaaa99.png`
- Evaluation-target implementation:
  `artifacts/design-qa/v0.5.5/evaluation-target-full.png`
- Score-impact reference:
  `/var/folders/y8/l1vtj33s14q6jbb9jlqr4tx80000gp/T/codex-clipboard-6e9912ab-928d-4fe1-b22d-e3f35ffb2d0c.png`
- Score-impact implementation:
  `artifacts/design-qa/v0.5.5/event-score-impact.png`
- Dimension-scorecard reference:
  `/var/folders/y8/l1vtj33s14q6jbb9jlqr4tx80000gp/T/codex-clipboard-44c9de09-9349-47d0-b8ce-37948e17e60d.png`
- Expanded scorecard implementation:
  `artifacts/design-qa/v0.5.5/dimension-score-explanation.png`

All three reference/implementation pairs were opened together in one comparison input. The final
captures preserve the existing dark Lab visual language, spacing, borders, typography, and state
colors while adding the requested information density and interactions.

## Findings and corrections

- The Evaluation target prompt previously used a single-line ellipsis. It now wraps normally in a
  top-aligned context bar, so the complete task request remains readable without hover or expansion.
- The Score impact tab previously showed the same causality disclaimer for most events. It now
  derives a selected-event verdict, citation status, evidence counts, tool coverage, and relevant
  dimension explanations from the completed trace and scorer metadata.
- The implementation does not invent per-event point deltas. It explains whether an event supplied
  credited evidence, consumed call budget, created a recovery opportunity, supplied the final
  decision, or served only as unscored model reasoning.
- Dimension cards were initially implemented as independent disclosure blocks. That caused the
  remaining cards to move into a sparse second row when one card opened. The final interaction keeps
  all seven cards visible in one row and opens one shared, full-width calculation panel beneath them.
- Each calculation panel reports the run-specific formula, plain-language reason, and the exact
  scorer inputs behind that dimension. The selected card receives a stronger outline and the panel
  has an explicit Close explanation action.

## Interaction checks

- Selected a successful `retail_sql` evidence event and opened Score impact.
- Verified the event was identified as Credited evidence with `2 of 2` valid citations, the minimum
  evidence threshold, 100% tool coverage, and separate Explainability and Efficiency reasoning.
- Opened Decision quality and verified the normalized-regret equation, oracle name, candidate
  utility, and best available utility appeared while all seven cards remained visible.
- Closed the dimension explanation and verified the shared panel returned to its neutral state.
- Reloaded the production Lab and verified the complete evaluation prompt was present in the DOM and
  visible across two lines.
- Checked both the production Lab and the component QA fixture for browser console errors; none were
  reported.

## Regression evidence

- Ruff passed.
- Full pytest suite: 147 passed.
- Specification validation: 25 task families.
- Generated world validation: 15,297 transactions across 20 tables.
- Reference and benchmark power-design verification passed.

No P0, P1, or P2 issue remains in the three requested surfaces.

final result: passed
