# DecisionAgentBench Lab design QA

## Review target

- Version: v0.5.2 corrective Lab pass on PR #15
- Route: `http://127.0.0.1:7873`
- Runtime: Gradio 6.20.0, real Inspect execution
- Desktop verification viewport: 1530 × 900 CSS pixels
- Verified agents: built-in planner/executor and `examples/custom_solver.py@custom_agent`
- Verified model: `mockllm/model` (local integration check)

## References and captures

- User's current-state screenshot:
  `/Users/abakh005/Downloads/screencapture-127-0-0-1-7860-2026-07-28-15_23_29.png`
- Selected trace reference:
  `/var/folders/y8/l1vtj33s14q6jbb9jlqr4tx80000gp/T/codex-clipboard-69cebe4d-195b-47ac-99fe-360e0e8a54e5.png`
- Completed toolbar: `/private/tmp/dab-lab-final-toolbar.jpg`
- Completed implementation trace: `/private/tmp/dab-lab-final-trace.jpg`
- Normalized reference/implementation comparison: `/private/tmp/dab-lab-final-comparison.jpg`

The source is 2572 × 1132 and the implementation trace capture is 2756 × 900. The combined
comparison fits each surface into a 1600 × 704 frame, preserving aspect ratio and using the same
completed-run state. This removes pixel-density differences while preserving layout, proportions,
density, and hierarchy.

## Initial audit

- P0: OpenAI reasoning-model runs failed because the planning stage forced `temperature=0.0`, which
  the selected model rejects.
- P1: provider failures filled the score panel with an escaped request and Python traceback.
- P1: the setup controls formed two dense rows with weak hierarchy and nested borders.
- P1: failed runs reserved a very tall empty trace canvas with no useful event content.
- P2: the trace selected the low-value `Run started` event instead of the first meaningful model or
  tool event.

## Final visual findings

- The page remains fluid and uses the available viewport width; the former max-width cap is gone.
- The setup area is one coherent toolbar with Agent, Model, Task, Condition, and one primary action.
  Custom-solver details live in a collapsed adapter drawer instead of a permanent second form row.
- The trace matches the reference's dark workbench: one run header, 58/42 timeline/inspector
  split, sticky column labels, vertical event rail, full-row selection, outcome styling, exact
  arguments, payload summaries, and Event details / Evidence payload / Score impact tabs.
- The score workbench retains the selected scoring-detail design while using the repository's real
  dimensions, weights, gates, failure codes, and evidence lineage.
- The page starts in an explicit Ready state with empty trace and score panels. No completed result
  is shown until Inspect returns one.
- The decorative stage strip has been replaced by truthful transient states: preparing, running
  model/tools, rendering recorded events, completed, or failed.
- Failed runs collapse to a proportional diagnostic trace and a concise classified error card. Raw
  request bodies and tracebacks remain in the `.eval` log rather than leaking into the interface.

## Interaction and runtime checks

- Built-in planner/executor completed a real Inspect `mockllm/model` sample and wrote a downloadable
  `.eval` log.
- The UI visibly changed from Ready → Running model and tools → event population → Run completed.
- `examples/custom_solver.py@custom_agent` loaded through Inspect's public `SolverSpec`, completed
  the same sample, and appeared under its stable custom system name.
- Model selection is editable and includes local and OpenAI examples.
- Trace-row selection updates the entire selected row and right-hand inspector.
- Event details, Evidence payload, and Score impact tabs all switch without a server round trip.
- Invalid final output from the mock model produced the real 0.0000 score, failed format/evidence
  gates, and no fabricated fallback result.
- Browser console warnings/errors during both verified flows: 0.
- Missing-credential and unsupported-parameter paths render a remediation, never a fabricated
  score, and never a raw `BadRequestError` request dump.
- The actual planning solver is covered by a regression test asserting that provider-specific
  sampling parameters are not sent. The advanced baselines use the same provider-safe default.

## Comparison history

1. Removed the 1540-pixel container cap and replaced the scripted replay with real Inspect runs.
2. Replaced the native Dataframe with a selectable trace workbench matching the chosen reference.
3. Added model selection, trusted custom-solver loading, and original log download.
4. Removed the decorative three-stage strip and consolidated metadata into the trace header.
5. Removed forced temperature settings from all benchmark baselines.
6. Rebuilt the setup form as a one-line toolbar plus compact evaluation-target context.
7. Replaced raw exception dumps with safe, classified error states and actionable recovery copy.
8. Changed the initial trace selection to the first meaningful model or tool event.

## Residual notes

- `mockllm/model` intentionally produces repetitive model events and is labeled as local plumbing;
  a provider-backed model produces the richer model/tool/result sequence shown by the design.
- The historical v0.2.1 scorer remains a development contract with documented construct-validity
  limitations. The UI explains this rather than visually implying publication eligibility.
- No P0, P1, or P2 visual issues remain in the final reference comparison. The implementation uses
  compact textual actor/outcome labels instead of introducing an additional icon dependency; the
  event rail, selection state, and color hierarchy keep the trace scannable.

final result: passed
