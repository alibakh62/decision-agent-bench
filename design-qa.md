# DecisionAgentBench Lab design QA

## Review target

- Version: v0.5.3 toolbar and incomplete-run corrective pass
- Route: `http://127.0.0.1:7875`
- Runtime: Gradio 6.20.0 with real Inspect execution
- Desktop verification viewport: 1280 × 720 CSS pixels, device pixel ratio 2
- Evaluation state: ready toolbar and a replay of the reported Luna `.eval` log

## References and captures

- User toolbar reference:
  `/var/folders/y8/l1vtj33s14q6jbb9jlqr4tx80000gp/T/codex-clipboard-b8d11ce2-5f39-4289-b550-db3d60f58f64.png`
- Reported Luna result:
  `/Users/abakh005/Downloads/screencapture-127-0-0-1-7860-2026-07-28-16_33_33.png`
- Initial 1280-pixel implementation capture: `/private/tmp/dab-lab-v053-toolbar.png`
- Normalized reference/implementation comparison:
  `/private/tmp/dab-lab-v053-toolbar-comparison.png`

The reference and implementation toolbar were placed in one 1812-pixel-wide comparison input.
That comparison exposed the remaining narrow-condition overflow before the final width rebalance.
Loopback navigation was subsequently denied by the user's in-app browser policy, so the last pass
was verified from the measured pre-fix geometry, final CSS constraints, Gradio structure, and UI
regression tests rather than by bypassing that browser restriction.

## Initial audit

- P1: Agent and Model helper text made their inputs start lower than Task, Condition, and Run.
- P1: the Condition field received only 159.7 CSS pixels at the 1280-pixel viewport and overflowed,
  exposing a horizontal scrollbar.
- P0: the Luna agent reached Inspect's 42-message boundary while still requesting tools. It never
  submitted a final JSON decision, but the Lab presented the scorer's format-gate diagnostic as a
  genuine 0.0000 model-quality score.
- P1: the built-in loop had no protected final-answer turn after evidence exploration.

## Final findings

- The five toolbar cells now share an equal-height row and bottom alignment. Agent and Model helper
  text was removed from the dense toolbar, eliminating the staggered input baselines.
- The primary button has one explicit 48-pixel height and a one-pixel optical bottom adjustment.
- Responsive minimums were rebalanced to 210 / 210 / 280 / 180 / 140 pixels. The Condition cell now
  remains wide enough for both options at the tested viewport without forcing a second row.
- Every built-in architecture is wrapped in an Inspect `Plan` with a finish solver. If exploration
  stops at the message boundary, the finish solver clears tools and reserves one provider-safe
  generation for the required JSON.
- A run with no JSON submission is now `incomplete`, not `success`. The Lab preserves its trace and
  evidence but reports **No score was reported** and suppresses the provisional zero scorecard.
- The Inspect scorer returns `Score.unscored()` for a missing submission, so the sample is excluded
  from aggregate metrics. A submitted, contract-valid decision that genuinely earns zero remains a
  valid zero and is still shown normally.
- Reprocessing the exact reported Luna log produces `Run incomplete`, an unavailable grade, and a
  final `Submission incomplete / Not scored` trace event.

## Interaction and regression checks

- All built-in baselines expose the finalizer as their `Plan.finish` solver.
- The finalizer test verifies that tools are empty, `tool_calls="none"` is sent, the final contract
  prompt is present, and a conforming JSON response is accepted.
- The missing-submission adapter test verifies that historical all-zero/safety-one diagnostics are
  retained only as raw audit data and never rendered as a composite score.
- The Inspect scorer test verifies that missing output produces the canonical NaN unscored sentinel
  plus `submission_status=missing`.
- Existing structured, evidence-gated, provider-error, live-run, trace, and score-explainer tests
  remain in the full project check.

## Residual notes

- A real provider rerun requires the user's exported API key and therefore must be performed from
  the same key-bearing shell that launches the Lab.
- The v0.2.1 scorer remains a historical development contract with documented construct-validity
  limitations. This pass corrects run completeness semantics; it does not expand publication claims.
- No P0, P1, or P2 issue remains in the implementation or regression surface reviewed here.

final result: passed
