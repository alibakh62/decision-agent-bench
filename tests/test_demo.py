from __future__ import annotations

import inspect
import json
from asyncio import run
from types import SimpleNamespace

import pytest
from inspect_ai.model import ModelName, ModelOutput
from inspect_ai.solver import Plan, TaskState

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
from decision_agent_bench.evals import advanced_baselines, baselines
from decision_agent_bench.lab import (
    REPLAY_AGENTS,
    SCORE_WEIGHTS,
    runtime_error_summary,
    score_explainer_html,
    trace_inspector_html,
    trace_rows,
    trace_workbench_html,
    write_run_report,
)
from decision_agent_bench.lab_runtime import (
    _trace_from_sample,
    payload_from_eval_log,
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

    assert payload["status"] == "incomplete"
    assert payload["model"] == "mockllm/model"
    assert payload["sample_id"] == "DAB-ASS-001-i1-clean"
    assert payload["grade"]["available"] is False
    assert payload["grade"]["availability_reason"]
    assert payload["trace"][-1]["event"] == "Submission incomplete"
    assert payload["trace"][0]["event"] == "Run started"
    assert payload["log_path"].endswith(".eval")


def test_builtin_agents_do_not_force_provider_specific_sampling_parameters() -> None:
    source = inspect.getsource(baselines) + inspect.getsource(advanced_baselines)

    assert "temperature=" not in source


def test_planning_stage_uses_provider_safe_generation_defaults() -> None:
    state = TaskState(
        model=ModelName("mockllm/model"),
        sample_id="provider-safe",
        epoch=1,
        input="Plan this task",
        messages=[],
    )
    observed: dict[str, object] = {}

    async def provider_safe_generate(task_state: TaskState, **kwargs: object) -> TaskState:
        observed.update(kwargs)
        task_state.output = ModelOutput(model="provider-safe", completion="1. Gather evidence")
        return task_state

    result = run(baselines.planning_step()(state, provider_safe_generate))

    assert observed == {"tool_calls": "none"}
    assert result.store.get("dab.plan") == "1. Gather evidence"


def test_built_in_baselines_reserve_a_tool_free_final_submission_turn() -> None:
    wrapped = baselines.baseline_solver("planner_executor")
    state = TaskState(
        model=ModelName("mockllm/model"),
        sample_id="finalization",
        epoch=1,
        input="Make a decision",
        messages=[],
    )
    state.output = ModelOutput(model="provider-safe", completion="")
    observed: dict[str, object] = {}
    final_answer = json.dumps(
        {
            "conclusion": "Evidence is insufficient; escalate for review.",
            "confidence": 0.3,
            "evidence_ids": ["E001"],
            "selected_ids": [],
            "numeric_values": {},
            "escalate": True,
            "data_quality_issues": ["Missing shelf-capacity evidence"],
        }
    )

    async def final_generate(task_state: TaskState, **kwargs: object) -> TaskState:
        observed.update(kwargs)
        observed["tools"] = list(task_state.tools)
        observed["prompt"] = task_state.messages[-1].text
        task_state.output = ModelOutput(model="provider-safe", completion=final_answer)
        return task_state

    result = run(baselines.finalize_submission()(state, final_generate))

    assert isinstance(wrapped, Plan)
    assert wrapped.finish is not None
    assert observed["tool_calls"] == "none"
    assert observed["tools"] == []
    assert "Evidence collection is now over" in str(observed["prompt"])
    assert result.output.completion == final_answer
    assert result.store.get("dab.finalization_valid") is True


def test_evidence_agent_finalizes_inside_its_bounded_tool_loop() -> None:
    state = TaskState(
        model=ModelName("mockllm/model"),
        sample_id="bounded-finalization",
        epoch=1,
        input="Make a decision",
        messages=[],
    )
    calls: list[dict[str, object]] = []
    final_answer = json.dumps(
        {
            "conclusion": "Escalate because the available evidence is incomplete.",
            "confidence": 0.4,
            "evidence_ids": [],
            "selected_ids": [],
            "numeric_values": {},
            "escalate": True,
            "data_quality_issues": ["Missing required economic evidence"],
        }
    )

    async def bounded_generate(task_state: TaskState, **kwargs: object) -> TaskState:
        calls.append(dict(kwargs))
        completion = "Need more context" if len(calls) == 1 else final_answer
        task_state.output = ModelOutput(model="provider-safe", completion=completion)
        return task_state

    result = run(baselines.evidence_agent(max_tool_turns=8)(state, bounded_generate))

    assert calls == [
        {"tool_calls": "single", "parallel_tool_calls": False},
        {"tool_calls": "none"},
    ]
    assert result.output.completion == final_answer
    assert result.store.get("dab.agent_tool_turns") == 1
    assert result.store.get("dab.finalization_attempts") == 1
    assert result.store.get("dab.finalization_valid") is True


def test_lab_trace_recognizes_direct_json_as_the_final_decision() -> None:
    final_answer = {
        "conclusion": "Replace P005 with P021.",
        "confidence": 0.8,
        "evidence_ids": ["E002", "E003"],
        "selected_ids": ["P021"],
        "numeric_values": {},
        "escalate": False,
        "data_quality_issues": [],
    }
    model_event_type = type("ModelEvent", (), {})
    model_event = model_event_type()
    model_event.timestamp = "2026-07-29T13:28:45+00:00"
    model_event.model = "openai/gpt-5.6-luna"
    model_event.output = ModelOutput.from_content(
        "openai/gpt-5.6-luna", json.dumps(final_answer)
    )
    sample = SimpleNamespace(
        id="DAB-ASS-001-i1-clean",
        started_at="2026-07-29T13:28:40+00:00",
        events=[model_event],
    )

    trace, _ = _trace_from_sample(sample, "openai/gpt-5.6-luna")

    assert trace[-1]["event"] == "Final decision"
    assert trace[-1]["outcome"] == "Submitted"
    assert trace[-1]["evidence_id"] == "E002,E003"
    assert trace[-1]["result"] == final_answer


def test_lab_does_not_present_a_missing_submission_as_a_zero_score() -> None:
    score = SimpleNamespace(
        value={
            "task_effectiveness": 0.0,
            "decision_quality": 0.0,
            "safety": 1.0,
            "robustness": 0.0,
            "calibration": 0.0,
            "efficiency": 0.0,
            "recovery": 0.0,
            "explainability": 0.0,
            "composite": 0.0,
        },
        answer="",
        explanation="Submission was not a JSON object.",
        metadata={"failure_taxonomy": ["F-FORMAT"]},
    )
    sample = SimpleNamespace(
        id="DAB-ASS-001-i1-clean",
        started_at="2026-07-28T21:32:40+00:00",
        completed_at="2026-07-28T21:33:05+00:00",
        total_time=25.0,
        events=[],
        scores={"decision_agent_scorer": score},
        output=ModelOutput(model="gpt-5.6-luna", completion=""),
        error=None,
        limit=SimpleNamespace(type="message", limit=42),
        model_usage={},
    )
    log = SimpleNamespace(
        samples=[sample],
        status="success",
        error=None,
        location="logs/example.eval",
        eval=SimpleNamespace(
            model="openai/gpt-5.6-luna",
            run_id="test-run",
            task_version="0.2.1",
        ),
    )
    from decision_agent_bench.demo import _CATALOG

    payload = payload_from_eval_log(
        log,
        agent_source="Built-in baseline",
        baseline="planner_executor",
        solver_reference="examples/custom_solver.py@custom_agent",
        system_name="lab-test",
        instance=_CATALOG["DAB-ASS-001-i1"],
        variant="clean",
    )
    rendered = score_explainer_html(payload)

    assert payload["status"] == "incomplete"
    assert payload["grade"]["available"] is False
    assert payload["grade"]["raw_scorer_values"]["safety"] == 1.0
    assert payload["trace"][-1]["outcome"] == "Not scored"
    assert "No score was reported" in rendered
    assert "SUBMISSION_INCOMPLETE" in rendered
    assert "Composite score" not in rendered


def test_lab_turns_provider_failures_into_actionable_safe_copy() -> None:
    raw_error = (
        "BadRequestError: Unsupported parameter: 'temperature' is not supported with this model."
    )
    summary = runtime_error_summary(raw_error)
    rendered = score_explainer_html({"grade": {"available": False}, "error": raw_error})

    assert summary["code"] == "MODEL_PARAMETER_UNSUPPORTED"
    assert "Run again" in summary["action"]
    assert "BadRequestError" not in summary["detail"]
    assert "MODEL_PARAMETER_UNSUPPORTED" in rendered
    assert "BadRequestError" not in rendered


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
