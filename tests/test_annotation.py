from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from inspect_ai.model import ChatMessageAssistant, ChatMessageTool, ChatMessageUser

from decision_agent_bench.research.annotation import (
    DIMENSIONS,
    RATING_FIELDS,
    agreement_report,
    annotation_entries,
)


def _fake_log() -> SimpleNamespace:
    score = SimpleNamespace(
        value={dimension: 1.0 for dimension in DIMENSIONS}, metadata={}
    )
    sample = SimpleNamespace(
        id="sample-secret-id",
        epoch=1,
        input="ignored",
        metadata={"task_id": "DAB-SAL-001", "variant": "perturbed"},
        messages=[
            ChatMessageUser(content="Investigate a sales decline."),
            ChatMessageTool(function="retail_sql", content='[{"region_id":"R03"}]'),
            ChatMessageAssistant(content='{"conclusion":"Investigate R03"}'),
        ],
        output=None,
        scores={"decision_agent_scorer": score},
    )
    evaluation = SimpleNamespace(
        run_id="private-run", model="provider/private-model", task_args={"baseline": "secret"}
    )
    return SimpleNamespace(status="success", eval=evaluation, samples=[sample])


def test_annotation_packet_blinds_experimental_identity() -> None:
    packet, key = annotation_entries(_fake_log())[0]

    assert set(packet) == {"blind_id", "prompt", "tool_evidence", "final_answer"}
    assert packet["prompt"] == "Investigate a sales decline."
    assert packet["tool_evidence"][0]["function"] == "retail_sql"
    assert "provider/private-model" not in json.dumps(packet)
    assert key["model"] == "provider/private-model"
    assert key["variant"] == "perturbed"
    assert key["deterministic_scores"]["safety"] == 1.0


def _write_key(path: Path) -> None:
    entries = [
        {
            "blind_id": "A",
            "deterministic_scores": {dimension: 1.0 for dimension in DIMENSIONS},
        },
        {
            "blind_id": "B",
            "deterministic_scores": {dimension: 0.0 for dimension in DIMENSIONS},
        },
    ]
    path.write_text("".join(json.dumps(item) + "\n" for item in entries), encoding="utf-8")


def _write_ratings(path: Path) -> None:
    rows = []
    for blind_id, value in (("A", 1), ("B", 0)):
        for rater_id in ("human-1", "human-2"):
            rows.append(
                {
                    "blind_id": blind_id,
                    "rater_id": rater_id,
                    "rater_type": "human",
                    **{dimension: value for dimension in DIMENSIONS},
                    "failure_codes": "",
                    "notes": "",
                }
            )
        rows.append(
            {
                "blind_id": blind_id,
                "rater_id": "judge-1",
                "rater_type": "llm",
                **{dimension: value for dimension in DIMENSIONS},
                "failure_codes": "",
                "notes": "",
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RATING_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_agreement_report_compares_all_three_rating_sources(tmp_path: Path) -> None:
    key = tmp_path / "key.jsonl"
    ratings = tmp_path / "ratings.csv"
    output = tmp_path / "agreement.json"
    _write_key(key)
    _write_ratings(ratings)

    report = agreement_report(ratings, key, output)

    assert output.exists()
    assert report["rater_counts"] == {"human": 4, "llm": 2}
    for dimension in DIMENSIONS:
        dimension_report = report["dimensions"][dimension]
        assert dimension_report["human"]["fleiss_kappa"] == 1.0
        assert dimension_report["deterministic_vs_human"]["agreement"] == 1.0
        assert dimension_report["llm_judge_vs_human"]["agreement"] == 1.0


def test_agreement_report_rejects_duplicate_ratings(tmp_path: Path) -> None:
    key = tmp_path / "key.jsonl"
    ratings = tmp_path / "ratings.csv"
    _write_key(key)
    _write_ratings(ratings)
    rows = ratings.read_text(encoding="utf-8").splitlines()
    ratings.write_text("\n".join([*rows, rows[1]]) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate rating"):
        agreement_report(ratings, key)


def test_agreement_report_rejects_invalid_threshold(tmp_path: Path) -> None:
    key = tmp_path / "key.jsonl"
    ratings = tmp_path / "ratings.csv"
    _write_key(key)
    _write_ratings(ratings)

    with pytest.raises(ValueError, match="between 0 and 1"):
        agreement_report(ratings, key, threshold=1.1)
