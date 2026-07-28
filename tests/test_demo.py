from __future__ import annotations

import json

import pytest

from decision_agent_bench.demo import (
    QUERY_LIBRARY,
    _execute_lab_run,
    build_demo,
    default_candidate,
    launch_demo,
    score_candidate,
    task_context_html,
    task_view,
    workflow_view,
    world_snapshot,
)
from decision_agent_bench.lab import (
    REPLAY_AGENTS,
    SCORE_WEIGHTS,
    score_explainer_html,
    trace_inspector_html,
    trace_rows,
    trace_workbench_html,
    write_run_report,
)
from decision_agent_bench.lab_runtime import (
    run_live_evaluation,
    safe_model_name,
    trusted_solver_spec,
)


def test_task_explorer_exposes_versioned_pair_without_hidden_contract() -> None:
    prompt, metadata, perturbation = task_view("DAB-SAL-001-i1", "perturbed")

    assert "region" in prompt.lower()
    assert metadata["sample_id"] == "DAB-SAL-001-i1-perturbed"
    assert metadata["scenario_seed"] == 20260717
    assert "missing_store_day_partition" in perturbation


def test_demo_scores_structured_candidate_and_evidence_lineage() -> None:
    scores, details = score_candidate("DAB-SAL-001", "clean", "complete", default_candidate())

    assert scores["task_effectiveness"] == 1
    assert scores["safety"] == 1
    assert details["available_evidence_ids"] == ["E001", "E002"]
    assert not details["failure_taxonomy"]


def test_workflow_explorer_reports_enforced_v03_contract() -> None:
    prompt, metadata, event = workflow_view("DAB-LH-RECALL-i1", "perturbed")

    assert "recall" in prompt.lower()
    assert metadata["enforced_transitions"] == 20
    assert metadata["dependency_span_target"] == 19
    assert metadata["minimum_simulated_days"] == 15
    assert metadata["horizon_claim"] == "dependency_enforced_preview"
    assert "substitute_supply_shortage" in event


def test_demo_rejects_invalid_submission() -> None:
    scores, details = score_candidate("DAB-SAL-001", "clean", "none", "not json")

    assert scores["composite"] == 0
    assert details["failure_taxonomy"] == ["F-FORMAT"]


def test_demo_rejects_keyword_answer_without_evidence() -> None:
    candidate = json.loads(default_candidate())
    candidate["conclusion"] = "R03 decline unit demand"
    candidate["evidence_ids"] = []

    scores, details = score_candidate("DAB-SAL-001", "clean", "none", json.dumps(candidate))

    assert scores["task_effectiveness"] == 0
    assert scores["decision_quality"] == 0
    assert scores["composite"] == 0
    assert details["evidence_eligible"] is False


def test_reference_world_uses_only_allow_listed_queries() -> None:
    rows = world_snapshot("Active recall")

    assert set(QUERY_LIBRARY) == {
        "Regional sales trend",
        "Feed freshness",
        "Active recall",
        "Refund clusters",
    }
    assert rows[0]["product_id"] == "P003"
    assert len(world_snapshot("Regional sales trend")) <= 24


def test_gradio_blocks_builds_without_launching() -> None:
    demo = build_demo()

    assert demo is not None
    assert json.loads(default_candidate())["selected_ids"] == ["R03"]


def test_lab_starts_without_a_fabricated_completed_result(monkeypatch) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the legacy replay must not run while the page is being built")

    monkeypatch.setattr("decision_agent_bench.demo._execute_lab_run", fail_if_called)

    assert build_demo() is not None


def test_live_lab_runs_one_real_inspect_sample(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "inspect_ai._util.appdirs.user_data_path", lambda _package: tmp_path / "inspect-data"
    )
    monkeypatch.setattr(
        "inspect_ai._util.appdirs.user_cache_path", lambda _package: tmp_path / "inspect-cache"
    )
    from decision_agent_bench.demo import _CATALOG

    payload = run_live_evaluation(
        agent_source="Built-in baseline",
        baseline="single_agent",
        solver_reference="examples/custom_solver.py@custom_agent",
        system_name="lab-test",
        model_name="mockllm/model",
        instance=_CATALOG["DAB-ASS-001-i1"],
        variant="clean",
    )

    assert payload["status"] == "success"
    assert payload["model"] == "mockllm/model"
    assert payload["sample_id"] == "DAB-ASS-001-i1-clean"
    assert payload["grade"]["available"] is True
    assert payload["trace"][0]["event"] == "Run started"
    assert payload["log_path"].endswith(".eval")


def test_lab_trace_matches_the_selectable_trace_inspector_contract() -> None:
    run = _execute_lab_run("planner_executor", "DAB-ASS-001-i1", "clean")
    run.update(
        {
            "status": "success",
            "model": "openai/example-model",
            "task_version": "0.2.1",
            "duration_seconds": 12.3,
        }
    )

    rendered = trace_workbench_html(run)

    assert "trace-event-row" in rendered
    assert "Event details" in rendered
    assert "Evidence payload" in rendered
    assert "Score impact" in rendered
    assert "openai/example-model" in rendered


def test_custom_solver_is_limited_to_trusted_project_agent_directories() -> None:
    spec = trusted_solver_spec("examples/custom_solver.py@custom_agent")

    assert spec.solver.endswith("examples/custom_solver.py@custom_agent")
    with pytest.raises(ValueError, match="must already exist under"):
        trusted_solver_spec("../Downloads/untrusted.py@agent")
    with pytest.raises(ValueError, match="model must be an Inspect identifier"):
        safe_model_name("$(unsafe)")


def test_lab_replays_agent_trace_and_real_historical_scorer() -> None:
    run = _execute_lab_run("planner_executor", "DAB-ASS-001-i1", "clean")

    assert run["replay_notice"].startswith("Provider-free deterministic replay")
    assert run["agent"]["architecture"] == "Plan, then ReAct + tools"
    assert run["grade"]["values"]["decision_quality"] == 1
    assert run["grade"]["values"]["composite"] > 0.99
    assert {row[3] for row in trace_rows(run)} >= {
        "Evidence plan",
        "retail_sql",
        "Final decision",
    }
    assert "Exact arguments" in trace_inspector_html(run, 2)


def test_lab_no_evidence_ablation_visibly_triggers_hard_gate() -> None:
    run = _execute_lab_run("no_evidence_prompt", "DAB-SAL-001-i1", "clean")
    score_html = score_explainer_html(run)

    assert run["evidence_eligible"] is False
    assert run["grade"]["values"]["task_effectiveness"] == 0
    assert run["grade"]["values"]["composite"] == 0
    assert "Evidence gate" in score_html
    assert "FAIL" in score_html
    assert "reported as 0.0000" in score_html


def test_lab_score_explainer_matches_repository_composite_contract() -> None:
    run = _execute_lab_run("single_agent", "DAB-SAL-001-i1", "clean")
    expected = round(
        sum(
            weight * run["grade"]["values"][dimension]
            for dimension, weight in SCORE_WEIGHTS.items()
        ),
        6,
    )
    score_html = score_explainer_html(run)

    assert run["raw_weighted_score"] == expected
    assert "0.30" in score_html and "Task effectiveness" in score_html
    assert "Robustness:" in score_html
    assert "not separately weighted" in score_html
    assert "construct-validity implementation gate" in score_html


def test_lab_exposes_all_baselines_and_public_task_context_only() -> None:
    context = task_context_html("DAB-SAF-001-i1", "perturbed")

    assert len(REPLAY_AGENTS) == 8
    assert "Controlled perturbation" in context
    assert "expected_concepts" not in context
    assert "oracle" not in context.lower()


def test_lab_report_is_portable_json() -> None:
    run = _execute_lab_run("memory_feedback", "DAB-REC-001-i1", "perturbed")
    report_path = write_run_report(run)
    report = json.loads(open(report_path, encoding="utf-8").read())

    assert report["run_id"] == run["run_id"]
    assert report["grade"]["values"] == run["grade"]["values"]


@pytest.mark.parametrize(
    ("agent_key", "instance_id", "variant", "message"),
    [
        ("../../agent", "DAB-SAL-001-i1", "clean", "unknown agent architecture"),
        ("single_agent", "../../task", "clean", "unknown task instance"),
        (
            "single_agent",
            "DAB-SAL-001-i1",
            "../../outside",
            "unknown evaluation condition",
        ),
    ],
)
def test_lab_rejects_untrusted_selection_values(
    agent_key: str, instance_id: str, variant: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _execute_lab_run(agent_key, instance_id, variant)


def test_lab_report_path_does_not_depend_on_payload_run_id() -> None:
    run = _execute_lab_run("single_agent", "DAB-SAL-001-i1", "clean")
    run["run_id"] = "../../outside"

    report_path = write_run_report(run)

    assert "outside" not in report_path
    assert json.loads(open(report_path, encoding="utf-8").read())["run_id"] == "../../outside"


def test_demo_launch_uses_blocks_level_theme_and_css(monkeypatch) -> None:
    import gradio as gr

    launch_kwargs: dict[str, object] = {}

    class FakeDemo:
        def launch(self, **kwargs: object) -> None:
            launch_kwargs.update(kwargs)

    monkeypatch.setattr("decision_agent_bench.demo.build_demo", FakeDemo)
    launch_demo(port=7899)

    assert launch_kwargs["server_port"] == 7899
    if int(str(gr.__version__).split(".", maxsplit=1)[0]) >= 6:
        assert "css" in launch_kwargs
        assert "theme" in launch_kwargs
    else:
        assert "css" not in launch_kwargs
        assert "theme" not in launch_kwargs
