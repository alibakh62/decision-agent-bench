"""State-machine, recovery, replay, and scoring tests for v0.3 workflows."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from decision_agent_bench.evals.scorer import grade_submission
from decision_agent_bench.evals.task import build_workflow_dataset
from decision_agent_bench.simulator import GenerationConfig, generate_world
from decision_agent_bench.simulator.workflow import (
    WORKFLOWS,
    WorkflowError,
    advance_time,
    execute_step,
    initialize_workflow,
    inspect_workflow_state,
    rollback_step,
    workflow_instance_catalog,
    workflow_metrics,
)


def _world(tmp_path: Path, workflow_id: str, variant: str = "clean") -> Path:
    path = generate_world(tmp_path, GenerationConfig(seed=20260717))
    initialize_workflow(
        path,
        workflow_id,
        variant=variant,
        scenario_seed=20260717,
    )
    return path


def _complete(path: Path, workflow_index: int, variant: str) -> None:
    workflow = WORKFLOWS[workflow_index]
    for ordinal in range(1, 21):
        if ordinal in {6, 11, 16}:
            advance_time(path, 5)
        if ordinal == 11 and variant == "perturbed":
            rollback_step(
                path,
                "S08",
                evidence_tools={"inspect_workflow"},
                reason="required disruption recovery",
            )
        evidence_tools = (
            {workflow.evidence_tools[ordinal - 1]} if ordinal <= 5 else {"execute_workflow_step"}
        )
        execute_step(path, f"S{ordinal:02d}", evidence_tools=evidence_tools)


def test_v03_dataset_is_12_seeded_instances_and_24_paired_samples() -> None:
    dataset = build_workflow_dataset()

    assert len(dataset) == 24
    assert len({sample.metadata["instance_id"] for sample in dataset}) == 12
    assert {sample.metadata["workflow_id"] for sample in dataset} == {
        workflow.workflow_id for workflow in WORKFLOWS
    }
    assert {sample.metadata["horizon_claim"] for sample in dataset} == {
        "dependency_enforced_preview"
    }
    assert {sample.metadata["enforced_transitions"] for sample in dataset} == {20}
    assert {sample.metadata["dependency_span_target"] for sample in dataset} == {19}
    published = json.loads(
        (Path(__file__).parents[1] / "data/task_specs/v0.3-workflows.json").read_text(
            encoding="utf-8"
        )
    )
    assert published == workflow_instance_catalog()


def test_out_of_order_and_early_transitions_are_denied_and_traced(tmp_path: Path) -> None:
    path = _world(tmp_path, WORKFLOWS[0].workflow_id)

    with pytest.raises(WorkflowError, match="dependency S01"):
        execute_step(path, "S02", evidence_tools={"retail_sql"})
    execute_step(path, "S01", evidence_tools={"retail_sql"})
    for ordinal in range(2, 6):
        execute_step(
            path,
            f"S{ordinal:02d}",
            evidence_tools={WORKFLOWS[0].evidence_tools[ordinal - 1]},
        )
    with pytest.raises(WorkflowError, match="simulated day 5"):
        execute_step(path, "S06", evidence_tools={"execute_workflow_step"})

    metrics = workflow_metrics(path)
    assert metrics["invalid_transition_count"] == 2
    assert metrics["steps_completed"] == 5
    assert not metrics["workflow_completed"]


@pytest.mark.parametrize("workflow_index", range(3))
@pytest.mark.parametrize("variant", ["clean", "perturbed"])
def test_all_workflows_complete_with_measured_time_and_dependency_span(
    tmp_path: Path, workflow_index: int, variant: str
) -> None:
    path = _world(tmp_path, WORKFLOWS[workflow_index].workflow_id, variant)
    _complete(path, workflow_index, variant)

    metrics = workflow_metrics(path)
    assert metrics["workflow_completed"]
    assert metrics["steps_completed"] == metrics["steps_required"] == 20
    assert metrics["dependency_span"] == 19
    assert metrics["simulated_days"] == 15
    assert metrics["outcome_score"] == 1.0
    assert metrics["rollback_count"] == (1 if variant == "perturbed" else 0)
    assert metrics["recovery_satisfied"]
    if workflow_index == 2:
        with sqlite3.connect(path) as connection:
            quarantined = connection.execute(
                """SELECT COUNT(*) FROM inventory_lots
                   WHERE product_id='P003' AND lot_id='LOT-P003-A' AND quarantined=1"""
            ).fetchone()[0]
            recall_status = connection.execute(
                "SELECT status FROM recall_notices WHERE notice_id='RC001'"
            ).fetchone()[0]
        assert quarantined == 12
        assert recall_status == "closed"


def test_stressed_workflow_blocks_progress_and_rollback_restores_state(
    tmp_path: Path,
) -> None:
    path = _world(tmp_path, WORKFLOWS[0].workflow_id, "perturbed")
    with sqlite3.connect(path) as connection:
        initial_price = connection.execute(
            "SELECT unit_price FROM prices WHERE store_id='S001' AND product_id='P001'"
        ).fetchone()[0]
    for ordinal in range(1, 11):
        if ordinal == 6:
            advance_time(path, 5)
        evidence_tools = (
            {WORKFLOWS[0].evidence_tools[ordinal - 1]}
            if ordinal <= 5
            else {"execute_workflow_step"}
        )
        execute_step(path, f"S{ordinal:02d}", evidence_tools=evidence_tools)
    advance_time(path, 5)

    state = inspect_workflow_state(path)
    assert state["required_rollback_step"] == "S08"
    with pytest.raises(WorkflowError, match="resolve required rollback"):
        execute_step(path, "S11", evidence_tools={"execute_workflow_step"})
    with pytest.raises(WorkflowError, match="inspect_workflow"):
        rollback_step(path, "S08", evidence_tools=set(), reason="unsupported")
    rollback_step(
        path,
        "S08",
        evidence_tools={"inspect_workflow"},
        reason="budget disruption",
    )

    with sqlite3.connect(path) as connection:
        restored_price = connection.execute(
            "SELECT unit_price FROM prices WHERE store_id='S001' AND product_id='P001'"
        ).fetchone()[0]
    assert restored_price == initial_price
    assert inspect_workflow_state(path)["required_rollback_step"] is None


def test_replay_is_deterministic_for_same_seed(tmp_path: Path) -> None:
    first = _world(tmp_path / "first", WORKFLOWS[1].workflow_id, "perturbed")
    second = _world(tmp_path / "second", WORKFLOWS[1].workflow_id, "perturbed")
    _complete(first, 1, "perturbed")
    _complete(second, 1, "perturbed")

    assert workflow_metrics(first)["state_digest"] == workflow_metrics(second)["state_digest"]


def test_narrative_only_v03_submission_scores_zero_effectiveness(tmp_path: Path) -> None:
    path = _world(tmp_path, WORKFLOWS[2].workflow_id)
    sample = build_workflow_dataset(variant="clean", instances_per_workflow=1)[2]
    contract = json.loads(sample.target)
    submission = {
        "conclusion": "Complete the recall workflow.",
        "confidence": 0.99,
        "evidence_ids": [],
        "selected_ids": [],
        "numeric_values": {},
        "escalate": False,
        "data_quality_issues": [],
    }

    grade = grade_submission(
        contract=contract,
        submission=submission,
        tool_calls=[],
        recoveries=[],
        variant="clean",
        perturbation_kind="none",
        database_path=path,
    )

    assert grade.values["task_effectiveness"] == 0.0
    assert grade.values["decision_quality"] == 0.0
    assert grade.values["composite"] == 0.0
    assert "F-EVID" in grade.failures
    assert "F-PLAN" in grade.failures
    assert grade.decision_outcome["steps_completed"] == 0
