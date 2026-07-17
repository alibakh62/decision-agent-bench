"""Versioned instance catalog generation for the expanded benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decision_agent_bench.evals.cases import CASES
from decision_agent_bench.specs import load_task_specs


def expanded_instance_catalog(instances_per_family: int = 4) -> list[dict[str, Any]]:
    """Return 100 stable task instances when called with the v0.2 default."""

    if not 1 <= instances_per_family <= 4:
        raise ValueError("instances_per_family must be between 1 and 4")
    specs = {str(spec["id"]): spec for spec in load_task_specs()}
    catalog: list[dict[str, Any]] = []
    for case in CASES:
        spec = specs[case.task_id]
        for instance_index in range(instances_per_family):
            instance_id = f"{case.task_id}-i{instance_index + 1}"
            catalog.append(
                {
                    "instance_id": instance_id,
                    "family_id": case.task_id,
                    "benchmark_version": "0.2.0",
                    "contract_version": spec["version"],
                    "scenario_seed": 20260717 + instance_index,
                    "category": spec["category"],
                    "difficulty": spec["difficulty"],
                    "horizon": spec["horizon"],
                    "prompt": case.prompt,
                    "clean_sample_id": f"{instance_id}-clean",
                    "perturbed_sample_id": f"{instance_id}-perturbed",
                    "perturbation": spec["perturbations"][0],
                }
            )
    return catalog


def write_expanded_instance_catalog(path: Path, instances_per_family: int = 4) -> Path:
    """Write the deterministic expanded instance catalog as formatted JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        expanded_instance_catalog(instances_per_family), indent=2, sort_keys=True
    )
    path.write_text(
        serialized + "\n",
        encoding="utf-8",
    )
    return path
