"""Loading and validation for benchmark task contracts."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "id",
    "version",
    "title",
    "category",
    "difficulty",
    "horizon",
    "objective",
    "capabilities",
    "perturbations",
    "success_criteria",
    "constraints",
    "evidence_requirements",
}
ALLOWED_DIFFICULTIES = {"easy", "medium", "hard", "expert"}


@dataclass(frozen=True)
class ValidationReport:
    """Summary returned after task specification validation."""

    task_count: int
    category_counts: dict[str, int]


def default_catalog_path() -> Path:
    """Return the task catalog from a source checkout or installed wheel."""

    source_catalog = Path(__file__).resolve().parents[2] / "data" / "task_specs" / "v0.1.json"
    if source_catalog.exists():
        return source_catalog
    return Path(str(files("decision_agent_bench").joinpath("data/v0.1.json")))


def load_task_specs(path: Path | None = None) -> list[dict[str, Any]]:
    """Load task specifications from *path*."""

    catalog_path = path or default_catalog_path()
    with catalog_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("task catalog must be a JSON array")
    return payload


def validate_task_specs(path: Path | None = None) -> ValidationReport:
    """Validate the structural and cross-record invariants of a task catalog."""

    specs = load_task_specs(path)
    errors: list[str] = []
    ids: list[str] = []

    for index, spec in enumerate(specs):
        if not isinstance(spec, dict):
            errors.append(f"item {index} is not an object")
            continue
        task_id = str(spec.get("id", f"item {index}"))
        ids.append(task_id)
        missing = sorted(REQUIRED_FIELDS - spec.keys())
        if missing:
            errors.append(f"{task_id}: missing fields {', '.join(missing)}")
        if spec.get("difficulty") not in ALLOWED_DIFFICULTIES:
            errors.append(f"{task_id}: invalid difficulty {spec.get('difficulty')!r}")
        if not isinstance(spec.get("horizon"), int) or spec.get("horizon", 0) < 1:
            errors.append(f"{task_id}: horizon must be a positive integer")
        for field in (
            "capabilities",
            "perturbations",
            "success_criteria",
            "constraints",
            "evidence_requirements",
        ):
            if not isinstance(spec.get(field), list) or not spec.get(field):
                errors.append(f"{task_id}: {field} must be a non-empty list")

    duplicates = sorted(task_id for task_id, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate task ids: {', '.join(duplicates)}")
    if errors:
        raise ValueError("invalid task catalog:\n- " + "\n- ".join(errors))

    categories = Counter(str(spec["category"]) for spec in specs)
    return ValidationReport(task_count=len(specs), category_counts=dict(sorted(categories.items())))
