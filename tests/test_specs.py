from __future__ import annotations

import json
from pathlib import Path

import pytest

from decision_agent_bench.specs import load_task_specs, validate_task_specs


def test_v01_catalog_contains_25_unique_tasks() -> None:
    report = validate_task_specs()

    assert report.task_count == 25
    assert sum(report.category_counts.values()) == 25


def test_every_task_has_multiple_score_dimensions() -> None:
    specs = load_task_specs()

    assert all(len(spec["success_criteria"]) >= 2 for spec in specs)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    specs = load_task_specs()
    specs[1]["id"] = specs[0]["id"]
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(specs), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate task ids"):
        validate_task_specs(path)
