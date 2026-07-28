"""Interactive DecisionAgentBench Lab for replaying and auditing evaluations."""

from __future__ import annotations

import json
import tempfile
from html import escape
from pathlib import Path
from typing import Any

from decision_agent_bench.evals.cases import CASES_BY_ID
from decision_agent_bench.evals.instances import expanded_instance_catalog
from decision_agent_bench.evals.runtime import apply_perturbation, perturbation_kind
from decision_agent_bench.evals.scorer import grade_submission, parse_submission
from decision_agent_bench.lab import (
    agent_choices,
    agent_description,
    run_replay,
    run_status_html,
    score_explainer_html,
    trace_inspector_html,
    trace_rows,
    write_run_report,
)
from decision_agent_bench.simulator import GenerationConfig, RetailEnvironment, generate_world
from decision_agent_bench.simulator.workflow import workflow_instance_catalog

_CATALOG = {item["instance_id"]: item for item in expanded_instance_catalog()}
_WORKFLOW_CATALOG = {item["instance_id"]: item for item in workflow_instance_catalog()}
_WORLD_TEMPORARY_DIRECTORY: tempfile.TemporaryDirectory[str] | None = None
_WORLD_PATH: Path | None = None
_RUN_WORLD_TEMPORARY_DIRECTORY: tempfile.TemporaryDirectory[str] | None = None
_RUN_WORLD_PATHS: dict[tuple[str, str], Path] = {}

QUERY_LIBRARY = {
    "Regional sales trend": """
        SELECT s.region_id, substr(t.sold_at, 1, 10) AS day,
               SUM(t.units) AS units, ROUND(SUM(t.net_sales), 2) AS net_sales
        FROM transactions t JOIN stores s USING(store_id)
        WHERE date(t.sold_at) >= date('2026-06-30', '-20 days')
        GROUP BY s.region_id, day ORDER BY day DESC, s.region_id LIMIT 18
    """,
    "Feed freshness": """
        SELECT feed_name, scope, last_complete_at, status, expected_frequency_minutes
        FROM data_feed_status ORDER BY feed_name, scope
    """,
    "Active recall": """
        SELECT r.notice_id, r.product_id, r.affected_lot_id, r.issued_at, r.status,
               SUM(l.on_hand_units) AS traced_units
        FROM recall_notices r LEFT JOIN inventory_lots l
          ON r.product_id=l.product_id AND r.affected_lot_id=l.lot_id
        WHERE r.status='active' GROUP BY r.notice_id
    """,
    "Refund clusters": """
        SELECT customer_id, store_id, COUNT(*) AS refunds,
               ROUND(SUM(amount), 2) AS refunded_amount,
               SUM(CASE WHEN receipt_present=0 THEN 1 ELSE 0 END) AS no_receipt
        FROM refunds GROUP BY customer_id, store_id
        ORDER BY refunds DESC, refunded_amount DESC LIMIT 12
    """,
}

_DEMO_CSS = """
:root {
  --lab-bg: #07111f;
  --lab-panel: #0c1828;
  --lab-panel-raised: #111f31;
  --lab-border: #26364b;
  --lab-border-strong: #38506e;
  --lab-text: #e8eef7;
  --lab-muted: #94a3b8;
  --lab-indigo: #536dfe;
  --lab-cyan: #45c8d8;
  --lab-green: #6fd08c;
  --lab-amber: #f3b35b;
  --lab-red: #ef6a6a;
}
body, .gradio-container {
  background: var(--lab-bg) !important;
  color: var(--lab-text) !important;
}
.gradio-container {
  max-width: 1540px !important;
  padding: 18px 22px 32px !important;
}
.contain { max-width: none !important; }
.lab-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 12px;
}
.lab-header h1, .score-workbench h2, .inspector-panel h3 {
  color: var(--lab-text);
  letter-spacing: -0.025em;
  margin: 0;
}
.lab-header h1 { font-size: 26px; }
.lab-header p, .score-title-row p { color: var(--lab-muted); margin: 4px 0 0; }
.mode-badge, .notice-inline, .status-badge, .dimension-chip {
  border: 1px solid #256b62;
  border-radius: 7px;
  color: #74dec3;
  display: inline-flex;
  font-size: 12px;
  font-weight: 650;
  padding: 6px 9px;
}
.stage-header {
  align-items: center;
  background: var(--lab-panel);
  border: 1px solid var(--lab-border);
  border-radius: 9px;
  display: grid;
  grid-template-columns: 1fr 32px 1fr 32px 1fr;
  margin-bottom: 12px;
  min-height: 58px;
  padding: 0 18px;
}
.stage { color: var(--lab-muted); font-weight: 650; text-align: center; }
.stage strong {
  align-items: center;
  background: #26364b;
  border-radius: 50%;
  color: var(--lab-text);
  display: inline-flex;
  height: 26px;
  justify-content: center;
  margin-right: 8px;
  width: 26px;
}
.stage.active { color: var(--lab-text); }
.stage.active strong { background: var(--lab-indigo); }
.stage-arrow { color: #4b5e78; text-align: center; }
.config-strip, .run-shell, .score-shell, .decision-shell, .task-shell {
  background: var(--lab-panel) !important;
  border: 1px solid var(--lab-border) !important;
  border-radius: 9px !important;
  padding: 12px !important;
}
.config-strip { margin-bottom: 12px; }
.config-strip label, .config-strip .wrap { color: var(--lab-text) !important; }
.agent-note { min-height: 94px; }
.agent-note strong { display: block; font-size: 16px; margin: 4px 0; }
.agent-note p { color: var(--lab-muted); line-height: 1.45; margin: 0 0 8px; }
.eyebrow {
  color: #8fa4bf;
  display: block;
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.075em;
  text-transform: uppercase;
}
.run-status {
  align-items: center;
  background: var(--lab-panel);
  border: 1px solid var(--lab-border);
  border-radius: 9px;
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(205px, .8fr) 2.4fr;
  margin: 12px 0;
  padding: 13px 16px;
}
.run-status > div { align-items: center; display: grid; grid-template-columns: 14px 1fr; }
.run-status small { color: var(--lab-muted); grid-column: 2; }
.status-dot { background: var(--lab-green); border-radius: 50%; height: 9px; width: 9px; }
.run-status dl { display: grid; gap: 18px; grid-template-columns: repeat(4, 1fr); margin: 0; }
.run-status dl div { border-left: 1px solid var(--lab-border); padding-left: 16px; }
.run-status dt { color: var(--lab-muted); font-size: 11px; }
.run-status dd { color: var(--lab-text); font-size: 13px; font-weight: 650; margin: 2px 0 0; }
.run-shell { padding: 0 !important; overflow: hidden; }
.trace-column { border-right: 1px solid var(--lab-border); padding: 10px !important; }
.inspector-column { padding: 0 !important; }
.inspector-panel { min-height: 565px; padding: 17px; }
.panel-heading { align-items: flex-start; display: flex; justify-content: space-between; gap: 16px; }
.panel-heading h3 { font-size: 19px; margin-top: 3px; }
.inspector-meta { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 18px 0; }
.inspector-meta div { background: #091524; border: 1px solid var(--lab-border); border-radius: 6px; padding: 9px; }
.inspector-meta span { color: var(--lab-muted); display: block; font-size: 11px; }
.inspector-meta strong { display: block; font-size: 12px; margin-top: 3px; overflow-wrap: anywhere; }
.event-summary { color: #c7d2e2; line-height: 1.5; }
.inspector-panel details, .score-section {
  background: #091524;
  border: 1px solid var(--lab-border);
  border-radius: 7px;
  margin-top: 10px;
  padding: 10px 12px;
}
.inspector-panel summary, .score-section > summary { color: var(--lab-text); cursor: pointer; font-weight: 650; }
.code-block {
  background: #050d18;
  border: 1px solid #1e3047;
  border-radius: 6px;
  color: #c4d2e5;
  font-size: 11px;
  line-height: 1.5;
  max-height: 225px;
  overflow: auto;
  padding: 11px;
  white-space: pre-wrap;
}
.score-lineage { border-top: 1px solid var(--lab-border); margin-top: 16px; padding-top: 14px; }
.score-lineage p, .muted, .robustness-note { color: var(--lab-muted); font-size: 12px; line-height: 1.5; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.dimension-chip { border-color: #384d70; color: #b5c4db; padding: 4px 7px; }
.score-shell { margin-top: 12px; padding: 0 !important; }
.score-workbench { background: var(--lab-panel); padding: 18px; }
.score-title-row { align-items: flex-start; display: flex; gap: 20px; justify-content: space-between; }
.score-title-row h2 { font-size: 22px; margin-top: 3px; }
.overall-score { align-items: end; display: grid; gap: 4px; text-align: right; }
.overall-score span { color: var(--lab-muted); font-size: 11px; }
.overall-score strong { color: #70ddc3; font-size: 30px; line-height: 1; }
.validity-warning {
  align-items: center;
  background: #1b1a13;
  border: 1px solid #6a552b;
  border-radius: 7px;
  color: #d9c79f;
  display: grid;
  gap: 12px;
  grid-template-columns: auto 1fr;
  margin: 14px 0;
  padding: 10px 12px;
}
.validity-warning strong { color: var(--lab-amber); }
.score-section { background: #0a1625; margin-top: 9px; }
.score-section > summary { font-size: 14px; padding: 2px 0 7px; }
.equation { display: grid; gap: 8px; padding: 12px 4px 4px; }
.equation code { color: #c7d2e2; font-size: 12px; overflow-wrap: anywhere; }
.equation strong { color: #82d99a; font-size: 12px; }
.dimension-grid { display: grid; gap: 8px; grid-template-columns: repeat(7, minmax(125px, 1fr)); margin-top: 10px; }
.dimension-card { background: var(--lab-panel-raised); border: 1px solid var(--lab-border-strong); border-radius: 7px; padding: 11px; }
.dimension-card.task_effectiveness { border-color: #3c70a5; }
.dimension-card.decision_quality { border-color: #7059a8; }
.dimension-card.safety { border-color: #3e7b55; }
.dimension-card.recovery { border-color: #ad7634; }
.dimension-card.explainability { border-color: #376f88; }
.dimension-card.calibration { border-color: #5b7399; }
.dimension-card.efficiency { border-color: #3c8390; }
.dimension-card > div:first-child { min-height: 39px; }
.dimension-card span, .dimension-card small { display: block; }
.dimension-card span { font-size: 12px; font-weight: 650; }
.dimension-card small { color: var(--lab-muted); font-size: 10px; }
.dimension-card > strong { display: block; font-size: 23px; margin: 8px 0; }
.dimension-card p { color: var(--lab-muted); font-size: 10px; margin: 8px 0 0; }
.meter { background: #26364b; border-radius: 4px; height: 4px; overflow: hidden; }
.meter span { background: var(--lab-cyan); height: 100%; }
.gate-grid { display: grid; gap: 10px; grid-template-columns: repeat(3, 1fr); margin-top: 10px; }
.gate-card { background: var(--lab-panel-raised); border: 1px solid var(--lab-border); border-radius: 7px; padding: 11px; }
.gate-card > div { display: flex; justify-content: space-between; }
.gate-card strong { font-size: 12px; }
.gate-card p { color: var(--lab-muted); font-size: 11px; margin: 8px 0 0; }
.gate-card.pass { border-color: #376b48; }
.gate-card.pass strong { color: var(--lab-green); }
.gate-card.fail { border-color: #853f46; }
.gate-card.fail strong { color: var(--lab-red); }
.gate-result { color: var(--lab-muted); font-size: 12px; }
.ledger-layout { display: grid; gap: 12px; grid-template-columns: 2.2fr 1fr; margin-top: 10px; }
.ledger { border-collapse: collapse; font-size: 11px; width: 100%; }
.ledger th, .ledger td { border-bottom: 1px solid var(--lab-border); padding: 8px; text-align: left; }
.ledger th { color: var(--lab-muted); }
.ledger td:nth-child(3), .ledger tfoot th { color: var(--lab-green); }
.ledger-delta { align-items: center; display: grid; gap: 7px; grid-template-columns: minmax(35px, 1fr) auto; }
.ledger-delta > span { background: var(--lab-cyan); border-radius: 3px; display: block; height: 7px; }
.ledger-delta > span.task_effectiveness { background: #5a91d1; }
.ledger-delta > span.decision_quality { background: #8f72d1; }
.ledger-delta > span.safety { background: #65b77c; }
.ledger-delta > span.recovery { background: #daa151; }
.ledger-delta > span.explainability { background: #5ba4be; }
.ledger-delta > span.calibration { background: #839ac0; }
.ledger-delta > span.efficiency { background: #5fb7c2; }
.evidence-map { background: var(--lab-panel-raised); border: 1px solid var(--lab-border); border-radius: 7px; padding: 10px; }
.evidence-map h4 { font-size: 12px; margin: 0 0 8px; }
.evidence-map ul { list-style: none; margin: 0; padding: 0; }
.evidence-map li { border-top: 1px solid var(--lab-border); display: grid; gap: 6px; grid-template-columns: 70px 1fr; padding: 7px 0; }
.evidence-map li span { color: var(--lab-muted); font-size: 10px; }
.task-context h3 { color: var(--lab-text); margin: 0 0 6px; }
.task-context p { color: #c6d1df; line-height: 1.5; }
.task-meta { display: flex; flex-wrap: wrap; gap: 7px; }
.task-meta span { background: #111f31; border: 1px solid var(--lab-border); border-radius: 6px; color: var(--lab-muted); font-size: 11px; padding: 5px 7px; }
.historical-note { border-left: 3px solid var(--lab-amber); color: #d5c39e !important; padding-left: 10px; }
.empty-panel { color: var(--lab-muted); padding: 30px; }
#run-evaluation { min-height: 44px; }
#trace-table table { font-size: 11px !important; }
#trace-table th { background: #0a1625 !important; color: #98a8bd !important; }
#trace-table td { background: #0c1828 !important; color: #d3ddea !important; }
#trace-table tr:hover td { background: #142642 !important; }
footer { display: none !important; }
@media (max-width: 1050px) {
  .run-status { grid-template-columns: 1fr; }
  .run-status dl { grid-template-columns: repeat(2, 1fr); }
  .dimension-grid { grid-template-columns: repeat(2, 1fr); }
  .ledger-layout { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .gradio-container { padding: 12px !important; }
  .lab-header, .score-title-row { flex-direction: column; }
  .stage-header { grid-template-columns: 1fr; gap: 6px; padding: 12px; }
  .stage-arrow { display: none; }
  .run-status dl, .gate-grid, .inspector-meta { grid-template-columns: 1fr; }
  .dimension-grid { grid-template-columns: 1fr; }
}
"""


def _world_path() -> Path:
    global _WORLD_PATH, _WORLD_TEMPORARY_DIRECTORY
    if _WORLD_PATH is None:
        _WORLD_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory(prefix="dab-demo-")
        _WORLD_PATH = generate_world(Path(_WORLD_TEMPORARY_DIRECTORY.name), GenerationConfig())
    return _WORLD_PATH


def _run_world_path(instance_id: str, variant: str) -> Path:
    """Return a cached isolated world matching the selected instance and paired variant."""

    global _RUN_WORLD_TEMPORARY_DIRECTORY
    key = (instance_id, variant)
    if key in _RUN_WORLD_PATHS:
        return _RUN_WORLD_PATHS[key]
    if _RUN_WORLD_TEMPORARY_DIRECTORY is None:
        _RUN_WORLD_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory(prefix="dab-lab-runs-")
    item = _CATALOG[instance_id]
    destination = Path(_RUN_WORLD_TEMPORARY_DIRECTORY.name) / f"{instance_id}-{variant}"
    database_path = generate_world(
        destination,
        GenerationConfig(seed=int(item["scenario_seed"])),
    )
    if variant == "perturbed":
        apply_perturbation(database_path, str(item["perturbation"]))
    _RUN_WORLD_PATHS[key] = database_path
    return database_path


def task_context_html(instance_id: str, variant: str) -> str:
    """Render public task context without exposing hidden grading targets or oracle fields."""

    item = _CATALOG[instance_id]
    sample_id = item[f"{variant}_sample_id"]
    perturbation = (
        "Clean paired sample; no controlled perturbation is applied."
        if variant == "clean"
        else f"Controlled perturbation: {item['perturbation']}"
    )
    return f"""
    <section class="task-context">
      <span class="eyebrow">Selected task</span>
      <h3>{escape(str(item['family_id']))} · {escape(str(item['category']).replace('_', ' '))}</h3>
      <p>{escape(str(item['prompt']))}</p>
      <div class="task-meta">
        <span>Sample {escape(str(sample_id))}</span>
        <span>Difficulty {escape(str(item['difficulty']))}</span>
        <span>Seed {item['scenario_seed']}</span>
        <span>Optimal tool calls {item['optimal_tool_calls']}</span>
        <span>Evidence dependency depth {item['enforced_dependency_depth']}</span>
      </div>
      <p class="historical-note">{escape(perturbation)} The v0.2 catalog is a historical
      evidence-gated contract; it does not establish long-horizon capability.</p>
    </section>
    """


def _execute_lab_run(agent_key: str, instance_id: str, variant: str) -> dict[str, Any]:
    item = _CATALOG[instance_id]
    run = run_replay(
        agent_key=agent_key,
        instance=item,
        variant=variant,
        database_path=_run_world_path(instance_id, variant),
    )
    return run.as_payload()


def task_view(instance_id: str, variant: str) -> tuple[str, dict[str, Any], str]:
    """Return prompt, metadata, and perturbation explanation for one catalog entry."""

    item = _CATALOG[instance_id]
    sample_id = item["clean_sample_id"] if variant == "clean" else item["perturbed_sample_id"]
    metadata = {
        "sample_id": sample_id,
        "family_id": item["family_id"],
        "category": item["category"],
        "difficulty": item["difficulty"],
        "declared_workflow_steps": item["declared_workflow_steps"],
        "optimal_tool_calls": item["optimal_tool_calls"],
        "enforced_dependency_depth": item["enforced_dependency_depth"],
        "horizon_claim": item["horizon_claim"],
        "scenario_seed": item["scenario_seed"],
        "benchmark_version": item["benchmark_version"],
    }
    perturbation = (
        "No perturbation. This is the clean paired sample."
        if variant == "clean"
        else f"Controlled perturbation: `{item['perturbation']}`"
    )
    return str(item["prompt"]), metadata, perturbation


def workflow_view(instance_id: str, variant: str) -> tuple[str, dict[str, Any], str]:
    """Return the public v0.3 prompt, measured contract, and paired stress event."""

    item = _WORKFLOW_CATALOG[instance_id]
    metadata = {
        "sample_id": item[f"{variant}_sample_id"],
        "workflow_id": item["workflow_id"],
        "category": item["category"],
        "scenario_seed": item["scenario_seed"],
        "enforced_transitions": item["enforced_transitions"],
        "dependency_span_target": item["dependency_span_target"],
        "minimum_simulated_days": item["minimum_simulated_days"],
        "horizon_claim": item["horizon_claim"],
        "benchmark_version": item["benchmark_version"],
    }
    event = (
        "No disruption. Delayed checkpoints still apply."
        if variant == "clean"
        else f"Delayed recovery event: `{item['perturbation']}`"
    )
    return str(item["prompt"]), metadata, event


def _evidence_calls(family_id: str, evidence_pack: str) -> list[dict[str, Any]]:
    if evidence_pack == "none":
        return []
    contract = CASES_BY_ID[family_id]
    tools = list(contract.required_tools)
    target_count = contract.min_evidence if evidence_pack == "complete" else 1
    while len(tools) < target_count:
        tools.append(tools[-1] if tools else "retail_sql")
    return [
        {
            "index": index,
            "tool": tool_name,
            "status": "success",
            "arguments": {},
            "evidence_id": f"E{index:03d}",
            "result_sha256": "demo-evidence",
        }
        for index, tool_name in enumerate(tools, start=1)
    ]


def score_candidate(
    family_id: str,
    variant: str,
    evidence_pack: str,
    candidate_json: str,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Grade a user-authored decision with a transparent simulated evidence ledger."""

    case = CASES_BY_ID[family_id]
    calls = _evidence_calls(family_id, evidence_pack)
    perturbation = (
        next(item["perturbation"] for item in _CATALOG.values() if item["family_id"] == family_id)
        if variant == "perturbed"
        else None
    )
    grade = grade_submission(
        contract={**case.target(), "contract_version": "0.2.1"},
        submission=parse_submission(candidate_json, strict=True),
        tool_calls=calls,
        recoveries=[calls[0]["tool"]] if calls and variant == "perturbed" else [],
        variant=variant,
        perturbation_kind=perturbation_kind(perturbation),
        database_path=_world_path(),
    )
    details = {
        "failure_taxonomy": list(grade.failures),
        "explanation": grade.explanation,
        "available_evidence_ids": [call["evidence_id"] for call in calls],
        "evidence_tools": [call["tool"] for call in calls],
        "hard_safety_gate": grade.values["safety"] == 0,
        "evidence_eligible": "F-EVID" not in grade.failures,
    }
    return grade.values, details


def world_snapshot(query_name: str) -> list[dict[str, Any]]:
    """Run one allow-listed, read-only reference-world query."""

    with RetailEnvironment(_world_path(), row_limit=24) as environment:
        return environment.query_sql(QUERY_LIBRARY[query_name])


def default_candidate() -> str:
    """Return a valid example submission for the first task family."""

    return json.dumps(
        {
            "conclusion": "R03 shows a material decline in unit demand; investigate locally.",
            "confidence": 0.85,
            "evidence_ids": ["E001", "E002"],
            "selected_ids": ["R03"],
            "numeric_values": {},
            "escalate": False,
            "data_quality_issues": [],
        },
        indent=2,
    )


def build_demo() -> Any:
    """Build the setup-to-review Gradio workbench; Gradio remains optional."""

    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError('install the demo extra with `pip install -e ".[demo]"`') from error

    default_instance = "DAB-ASS-001-i1"
    if default_instance not in _CATALOG:
        default_instance = sorted(_CATALOG)[0]
    task_choices = [
        (
            f"{item['family_id']} · {str(item['category']).replace('_', ' ')} · {instance_id}",
            instance_id,
        )
        for instance_id, item in sorted(_CATALOG.items())
    ]
    initial_payload = _execute_lab_run("planner_executor", default_instance, "clean")
    initial_report = write_run_report(initial_payload)

    def execute_for_ui(
        agent_key: str,
        instance_id: str,
        variant: str,
    ) -> tuple[
        dict[str, Any],
        str,
        list[list[str]],
        str,
        dict[str, Any],
        str,
        str,
        str,
    ]:
        payload = _execute_lab_run(agent_key, instance_id, variant)
        return (
            payload,
            run_status_html(payload),
            trace_rows(payload),
            trace_inspector_html(payload),
            payload["submission"],
            score_explainer_html(payload),
            task_context_html(instance_id, variant),
            write_run_report(payload),
        )

    def inspect_selected(payload: dict[str, Any], event: Any) -> str:
        index = event.index
        row_index = index[0] if isinstance(index, tuple | list) else int(index)
        return trace_inspector_html(payload, row_index)

    inspect_selected.__annotations__["event"] = gr.SelectData

    theme = gr.themes.Base(primary_hue="indigo", neutral_hue="slate")
    blocks_options: dict[str, Any] = {
        "title": "DecisionAgentBench Lab",
        "fill_width": True,
    }
    if int(str(gr.__version__).split(".", maxsplit=1)[0]) < 6:
        blocks_options.update({"theme": theme, "css": _DEMO_CSS})
    with gr.Blocks(**blocks_options) as demo:
        run_state = gr.State(initial_payload)
        gr.HTML(
            """
            <header class="lab-header"><div><h1>DecisionAgentBench Lab</h1>
            <p>Evaluation Studio · replay an agent, inspect its trace, and audit every score.</p></div>
            <span class="mode-badge">Local deterministic replay · no provider calls</span></header>
            <nav class="stage-header" aria-label="Evaluation stages">
              <span class="stage"><strong>1</strong>Setup</span><span class="stage-arrow">→</span>
              <span class="stage"><strong>2</strong>Execute</span><span class="stage-arrow">→</span>
              <span class="stage active"><strong>3</strong>Review</span>
            </nav>
            """
        )
        with gr.Row(elem_classes="config-strip"):
            with gr.Column(scale=4, min_width=240):
                selected_agent = gr.Dropdown(
                    choices=agent_choices(),
                    value="planner_executor",
                    label="Agent architecture",
                )
            with gr.Column(scale=5, min_width=300):
                selected_task = gr.Dropdown(
                    choices=task_choices,
                    value=default_instance,
                    label="Task instance",
                )
            with gr.Column(scale=2, min_width=180):
                selected_variant = gr.Radio(
                    ["clean", "perturbed"],
                    value="clean",
                    label="Condition",
                )
            with gr.Column(scale=2, min_width=170):
                run_button = gr.Button(
                    "Run evaluation",
                    variant="primary",
                    elem_id="run-evaluation",
                )
        with gr.Accordion("Agent and task context", open=False):
            with gr.Row():
                with gr.Column(scale=4, elem_classes="task-shell"):
                    selected_agent_note = gr.HTML(agent_description("planner_executor"))
                with gr.Column(scale=8, elem_classes="task-shell"):
                    selected_task_context = gr.HTML(task_context_html(default_instance, "clean"))

        status = gr.HTML(run_status_html(initial_payload))
        with gr.Row(equal_height=True, elem_classes="run-shell"):
            with gr.Column(scale=7, elem_classes="trace-column"):
                gr.Markdown("### Agent run trace\nSelect any row to inspect its exact payload and score lineage.")
                trace_table = gr.Dataframe(
                    value=trace_rows(initial_payload),
                    headers=["Step", "Time", "Actor", "Event", "Summary", "Evidence", "Outcome"],
                    datatype=["str"] * 7,
                    interactive=False,
                    wrap=True,
                    elem_id="trace-table",
                    label=None,
                )
            with gr.Column(scale=5, elem_classes="inspector-column"):
                inspector = gr.HTML(trace_inspector_html(initial_payload))

        with gr.Group(elem_classes="score-shell"):
            score_explainer = gr.HTML(score_explainer_html(initial_payload))
        with gr.Accordion("Final structured decision and portable report", open=False):
            with gr.Row():
                final_decision = gr.JSON(initial_payload["submission"], label="Submitted JSON")
                with gr.Column(min_width=220):
                    gr.Markdown(
                        "The report contains the public task metadata, scripted trace, evidence "
                        "lineage, final JSON, every score, gates, and the replay claim boundary."
                    )
                    report = gr.DownloadButton(
                        "Download run report",
                        value=initial_report,
                        variant="secondary",
                    )
                    gr.Markdown(
                        "To evaluate a real external system, follow "
                        "[`docs/evaluating-your-agent.md`](file/docs/evaluating-your-agent.md)."
                    )

        selected_agent.change(
            agent_description,
            inputs=selected_agent,
            outputs=selected_agent_note,
            show_progress="hidden",
            api_name=False,
        )
        selected_task.change(
            task_context_html,
            inputs=[selected_task, selected_variant],
            outputs=selected_task_context,
            show_progress="hidden",
            api_name=False,
        )
        selected_variant.change(
            task_context_html,
            inputs=[selected_task, selected_variant],
            outputs=selected_task_context,
            show_progress="hidden",
            api_name=False,
        )
        run_button.click(
            execute_for_ui,
            inputs=[selected_agent, selected_task, selected_variant],
            outputs=[
                run_state,
                status,
                trace_table,
                inspector,
                final_decision,
                score_explainer,
                selected_task_context,
                report,
            ],
            show_progress="minimal",
            api_name=False,
        )
        trace_table.select(
            inspect_selected,
            inputs=run_state,
            outputs=inspector,
            show_progress="hidden",
            api_name=False,
        )
    return demo


def launch_demo(host: str = "127.0.0.1", port: int = 7860) -> None:
    """Launch the local-only interactive demo."""

    demo = build_demo()
    import gradio as gr

    launch_options: dict[str, Any] = {
        "server_name": host,
        "server_port": port,
        "share": False,
        "show_error": True,
    }
    if int(str(gr.__version__).split(".", maxsplit=1)[0]) >= 6:
        launch_options.update(
            {
                "css": _DEMO_CSS,
                "theme": gr.themes.Base(primary_hue="indigo", neutral_hue="slate"),
            }
        )
    demo.launch(
        **launch_options,
    )
