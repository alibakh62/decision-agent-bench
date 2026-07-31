# DecisionAgentBench Lab design QA

## Review target

- Version: v0.5.6 custom-agent onboarding and cross-theme accessibility pass
- Route: `http://127.0.0.1:7880`
- Runtime: Gradio 6.20.0 with the production Lab CSS and real Inspect execution path
- Verification viewport: 1280 × 720 CSS pixels, device pixel ratio 2
- States reviewed: ready Lab in dark and light themes, custom-agent onboarding before upload,
  validated uploaded adapter, and a completed custom-agent execution attempt

## Source truth and implementation evidence

- Dark-theme baseline: `artifacts/design-qa/v0.5.6/before-dark.png`
- Dark-theme implementation: `artifacts/design-qa/v0.5.6/after-dark.png`
- Light-theme baseline: `artifacts/design-qa/v0.5.6/before-light.png`
- Light-theme implementation: `artifacts/design-qa/v0.5.6/after-light.png`
- Custom-agent onboarding: `artifacts/design-qa/v0.5.6/custom-agent-dark.png`
- Custom-agent execution trace: `artifacts/design-qa/v0.5.6/custom-agent-run.png`

The dark/light baseline and implementation captures were opened together in one comparison input.
The final design preserves the established Lab hierarchy and trace/scoring workbench while making
theme behavior explicit and elevating custom-agent connection from a hidden advanced field to a
guided primary workflow.

## Findings and corrections

- P1: Light mode inherited dark-only surface and text colors inside Gradio's application root.
  Explicit semantic tokens now bind page, panel, control, muted text, borders, alerts, trace rows,
  scorecards, and onboarding surfaces in light mode. Dark tokens are applied both to `body.dark`
  and through `:host-context(.dark)` so shadow-root rendering remains correct.
- P2: The original first-class onboarding layout could exceed a 1280-pixel laptop viewport and the
  upload helper could collide with the file drop zone. The toolbar and context strip now reflow at
  1350 pixels, the onboarding steps and configuration columns stack cleanly, and upload help owns a
  separate readable row.
- The custom-agent route is now named **Connect your own agent** and presents a three-step mental
  model before asking for configuration.
- Upload is the default low-friction path; an existing trusted local solver remains available for
  repository-based workflows.
- Uploaded adapters are validated for file type, size, UTF-8, Python syntax, and registered Inspect
  solver entrypoints without importing or executing the file. The run action stays disabled until a
  valid entrypoint and system name are available.
- The onboarding surface includes a starter adapter download, an in-product link to the full guide,
  and a prominent local-code safety explanation.

## Interaction and runtime checks

- Selected **Connect your own agent** and verified the onboarding workbench appeared while the Run
  evaluation action was disabled.
- Uploaded `examples/custom_solver.py`; the Lab detected `custom_agent`, changed the adapter status
  to ready, and enabled Run evaluation.
- Ran the uploaded solver with `mockllm/model`. Inspect executed the custom adapter in the real task,
  recorded its trace, and honestly reported an incomplete submission when the mock model did not
  emit the required final JSON; no score was fabricated.
- Verified the latest 1280-pixel custom-agent layout has no document-level horizontal overflow.
- Verified complete evaluation-target copy remains readable in both themes.
- Checked the final dark and light Lab tabs for browser console errors; none were reported.

## Visual comparison

- Typography: headings, labels, helper text, controls, and monospace trace content remain legible in
  both themes with consistent hierarchy.
- Layout: the toolbar, context strip, run state, trace placeholder, scoring placeholder, and custom
  onboarding retain aligned edges and predictable responsive stacking.
- Color: light surfaces use dark foregrounds and visible borders; dark surfaces preserve the existing
  navy palette and status semantics.
- Assets: this workflow has no illustrative source assets; interface icons and control affordances
  remain native to the existing Gradio-based design system.
- Copy: onboarding text explains what an adapter is, what validation does, when code executes, and
  where to find the complete integration contract.

## Regression evidence

- Ruff passed.
- Full pytest suite: 153 passed.
- Specification validation: 25 task families.
- Generated world validation: 15,297 transactions across 20 tables.
- Reference and both benchmark power-design verifications passed.
- Source security audit passed; dependency and container audits remain live-CI checks by design.

No P0, P1, or P2 issue remains in the requested theme or custom-agent onboarding surfaces.

final result: passed
