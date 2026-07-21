"""Versioned instance catalog generation for the expanded benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decision_agent_bench.evals.cases import CASES
from decision_agent_bench.specs import load_task_specs

EXPANDED_VERSION = "0.2.1"
EXPANDED_CATEGORY_ALIASES = {"long_horizon_workflow": "workflow_planning"}


def expanded_category(category: str) -> str:
    """Return the v0.2.1 category without rewriting the frozen v0.1 specs."""

    return EXPANDED_CATEGORY_ALIASES.get(category, category)


def scheduled_perturbation(perturbations: list[str], instance_index: int) -> str:
    """Select perturbations cyclically so four seeds exercise every named concept."""

    if not perturbations:
        raise ValueError("each task family must declare at least one perturbation")
    return perturbations[instance_index % len(perturbations)]


def expanded_instance_catalog(instances_per_family: int = 4) -> list[dict[str, Any]]:
    """Return 100 stable seeded instances when called with the v0.2 default."""

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
                    "benchmark_version": EXPANDED_VERSION,
                    "contract_version": EXPANDED_VERSION,
                    "family_spec_version": spec["version"],
                    "scenario_seed": 20260717 + instance_index,
                    "category": expanded_category(str(spec["category"])),
                    "difficulty": spec["difficulty"],
                    "declared_workflow_steps": spec["horizon"],
                    "optimal_tool_calls": case.optimal_tool_calls,
                    "enforced_dependency_depth": 0,
                    "horizon_claim": "not_established",
                    "prompt": case.prompt,
                    "clean_sample_id": f"{instance_id}-clean",
                    "perturbed_sample_id": f"{instance_id}-perturbed",
                    "perturbation": scheduled_perturbation(
                        [str(value) for value in spec["perturbations"]], instance_index
                    ),
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
