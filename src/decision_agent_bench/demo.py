"""Interactive local research demo for task exploration and deterministic grading."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from decision_agent_bench.evals.cases import CASES_BY_ID
from decision_agent_bench.evals.instances import expanded_instance_catalog
from decision_agent_bench.evals.runtime import perturbation_kind
from decision_agent_bench.evals.scorer import grade_submission, parse_submission
from decision_agent_bench.simulator import GenerationConfig, RetailEnvironment, generate_world

_CATALOG = {item["instance_id"]: item for item in expanded_instance_catalog()}
_WORLD_TEMPORARY_DIRECTORY: tempfile.TemporaryDirectory[str] | None = None
_WORLD_PATH: Path | None = None

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
.gradio-container { max-width: 1180px !important; }
.hero { padding: 1.2rem 0 0.4rem; }
.hero h1 { letter-spacing: -0.035em; }
.metric-note { color: #475569; }
"""


def _world_path() -> Path:
    global _WORLD_PATH, _WORLD_TEMPORARY_DIRECTORY
    if _WORLD_PATH is None:
        _WORLD_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory(prefix="dab-demo-")
        _WORLD_PATH = generate_world(
            Path(_WORLD_TEMPORARY_DIRECTORY.name), GenerationConfig()
        )
    return _WORLD_PATH


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
    """Build the Gradio Blocks application; Gradio remains an optional dependency."""

    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError('install the demo extra with `pip install -e ".[demo]"`') from error

    instance_choices = sorted(_CATALOG)
    family_choices = sorted(CASES_BY_ID)
    initial_prompt, initial_metadata, initial_perturbation = task_view(
        instance_choices[0], "clean"
    )

    with gr.Blocks(title="DecisionAgentBench Lab") as demo:
        gr.Markdown(
            """
            <div class="hero">
            <h1>DecisionAgentBench Lab</h1>
            <p>Explore consequential business-agent tasks, inspect controlled failures, and test
            structured decisions against the same deterministic grader used by the benchmark.</p>
            </div>
            """
        )
        with gr.Tab("Task explorer"):
            with gr.Row():
                instance = gr.Dropdown(
                    instance_choices, value=instance_choices[0], label="Scenario instance"
                )
                task_variant = gr.Radio(
                    ["clean", "perturbed"], value="clean", label="Paired variant"
                )
            prompt = gr.Textbox(initial_prompt, label="Business decision", lines=5)
            task_metadata = gr.JSON(initial_metadata, label="Versioned metadata")
            perturbation_note = gr.Markdown(initial_perturbation)
            instance.change(
                task_view,
                inputs=[instance, task_variant],
                outputs=[prompt, task_metadata, perturbation_note],
            )
            task_variant.change(
                task_view,
                inputs=[instance, task_variant],
                outputs=[prompt, task_metadata, perturbation_note],
            )

        with gr.Tab("Decision scorer"):
            gr.Markdown(
                "The demo evidence pack exposes only IDs and tool lineage. It never reveals hidden "
                "grading contracts. Try removing evidence, raising confidence, or making an unsafe "
                "decision to see the score and failure taxonomy change."
            )
            with gr.Row():
                family = gr.Dropdown(
                    family_choices, value="DAB-SAL-001", label="Task family"
                )
                score_variant = gr.Radio(
                    ["clean", "perturbed"], value="clean", label="Variant"
                )
                evidence_pack = gr.Radio(
                    ["none", "minimal", "complete"],
                    value="complete",
                    label="Simulated evidence pack",
                )
            candidate = gr.Textbox(
                default_candidate(), label="Candidate final JSON", lines=14
            )
            score_button = gr.Button("Score decision", variant="primary")
            with gr.Row():
                scores = gr.JSON(label="Deterministic scores")
                score_details = gr.JSON(label="Audit details")
            score_button.click(
                score_candidate,
                inputs=[family, score_variant, evidence_pack, candidate],
                outputs=[scores, score_details],
            )

        with gr.Tab("Reference world"):
            gr.Markdown(
                "These allow-listed views expose synthetic evidence only. Arbitrary SQL and oracle "
                "parameters are intentionally unavailable in the public demo."
            )
            query = gr.Dropdown(
                list(QUERY_LIBRARY), value="Regional sales trend", label="Evidence view"
            )
            query_button = gr.Button("Run safe query", variant="primary")
            query_output = gr.JSON(label="Rows")
            query_button.click(world_snapshot, inputs=query, outputs=query_output)
    return demo


def launch_demo(host: str = "127.0.0.1", port: int = 7860) -> None:
    """Launch the local-only interactive demo."""

    demo = build_demo()
    import gradio as gr

    demo.launch(
        server_name=host,
        server_port=port,
        share=False,
        show_error=True,
        css=_DEMO_CSS,
        theme=gr.themes.Soft(),
    )
