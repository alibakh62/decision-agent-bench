# DecisionAgentBench Lab design QA

## Review target

- Version: v0.5.2 corrective Lab pass on PR #14
- Route: `http://127.0.0.1:7872`
- Runtime: Gradio 6.20.0, real Inspect execution
- Desktop comparison viewport: 2048 × 900 CSS pixels
- Verified agents: built-in planner/executor and `examples/custom_solver.py@custom_agent`
- Verified model: `mockllm/model` (local integration check)

## References and captures

- User's current-state screenshot:
  `/Users/abakh005/Downloads/screencapture-127-0-0-1-7860-2026-07-28-13_58_17.png`
- Selected trace reference:
  `/var/folders/y8/l1vtj33s14q6jbb9jlqr4tx80000gp/T/codex-clipboard-69cebe4d-195b-47ac-99fe-360e0e8a54e5.png`
- Initial implementation state: browser capture at 2048 × 900; starts with no run or score.
- Completed implementation trace: `/private/tmp/dab-lab-final-trace-2.png`
- Normalized reference/implementation comparison: `/private/tmp/dab-lab-trace-comparison.jpg`

The comparison normalizes both trace surfaces to the same 1600 × 704 crop. This removes Retina
density differences while preserving layout, proportions, density, and hierarchy.

## Initial audit

- P0: **Run evaluation** returned a scripted provider-free replay in less than a second while the
  surface looked like an empirical agent result.
- P1: the Gradio container was capped and left a large unused band on wide screens.
- P1: the native Dataframe trace was horizontally clipped, visually flat, and substantially less
  readable than the selected reference.
- P1: no model control or supported custom-agent entry point existed in the Lab.
- P2: the permanently active Setup → Execute → Review strip communicated no real application state.
- P2: a completed replay and 0.9993 score were preloaded before user action.

## Final visual findings

- The page now measures 2048 CSS pixels at the Gradio container and 1928 pixels for the padded main
  content at the 2048-pixel reference viewport. The former max-width cap is gone.
- The trace matches the reference's dense dark workbench: one run header, 58/42 timeline/inspector
  split, sticky column labels, vertical event rail, full-row selection, outcome styling, exact
  arguments, payload summaries, and Event details / Evidence payload / Score impact tabs.
- The score workbench retains the selected scoring-detail design while using the repository's real
  dimensions, weights, gates, failure codes, and evidence lineage.
- The page starts in an explicit Ready state with empty trace and score panels. No completed result
  is shown until Inspect returns one.
- The decorative stage strip has been replaced by truthful transient states: preparing, running
  model/tools, rendering recorded events, completed, or failed.

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

## Comparison history

1. Removed the 1540-pixel container cap and verified the full 2048-pixel Gradio surface.
2. Replaced the native Dataframe and separate HTML panel with a single selectable trace workbench.
3. Removed the precomputed replay and wired the run button to `inspect_ai.eval`.
4. Added dynamic execution states and progressive rendering of finalized log events.
5. Added model selection, trusted custom-solver loading, system naming, and original log download.
6. Removed the completed-status duplication by consolidating metadata into the trace header.
7. Darkened the internal trace scrollbars and fixed the no-submission evidence gate display.

## Residual notes

- `mockllm/model` intentionally produces repetitive model events and a failing structured answer; a
  provider-backed model produces the richer model/tool/result/error sequence shown by the design.
- The historical v0.2.1 scorer remains a development contract with documented construct-validity
  limitations. The UI explains this rather than visually implying publication eligibility.

final result: passed
