from __future__ import annotations

import json

from decision_agent_bench.demo import (
    QUERY_LIBRARY,
    build_demo,
    default_candidate,
    score_candidate,
    task_view,
    world_snapshot,
)


def test_task_explorer_exposes_versioned_pair_without_hidden_contract() -> None:
    prompt, metadata, perturbation = task_view("DAB-SAL-001-i1", "perturbed")

    assert "region" in prompt.lower()
    assert metadata["sample_id"] == "DAB-SAL-001-i1-perturbed"
    assert metadata["scenario_seed"] == 20260717
    assert "missing_store_day_partition" in perturbation


def test_demo_scores_structured_candidate_and_evidence_lineage() -> None:
    scores, details = score_candidate(
        "DAB-SAL-001", "clean", "complete", default_candidate()
    )

    assert scores["task_effectiveness"] == 1
    assert scores["safety"] == 1
    assert details["available_evidence_ids"] == ["E001", "E002"]
    assert not details["failure_taxonomy"]


def test_demo_rejects_invalid_submission() -> None:
    scores, details = score_candidate("DAB-SAL-001", "clean", "none", "not json")

    assert scores["composite"] == 0
    assert details["failure_taxonomy"] == ["F-FORMAT"]


def test_demo_rejects_keyword_answer_without_evidence() -> None:
    candidate = json.loads(default_candidate())
    candidate["conclusion"] = "R03 decline unit demand"
    candidate["evidence_ids"] = []

    scores, details = score_candidate(
        "DAB-SAL-001", "clean", "none", json.dumps(candidate)
    )

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
