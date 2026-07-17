"""Deterministic experiment-grid sizing and whole-study cost preflight."""

from __future__ import annotations

from collections import Counter
from decimal import ROUND_CEILING, Decimal
from typing import Any

from decision_agent_bench.evals.instances import expanded_instance_catalog
from decision_agent_bench.experiments.schema import ExperimentConfig
from decision_agent_bench.specs import load_task_specs


def sample_count_for_cell(
    task_name: str,
    *,
    category: str | None,
    sample_limit: int | None,
) -> int:
    """Return the number of unique samples in one model/baseline/variant cell."""

    if task_name == "decision_agent_bench_v0_2":
        category_counts = Counter(
            str(instance["category"]) for instance in expanded_instance_catalog()
        )
    elif task_name == "decision_agent_bench":
        category_counts = Counter(str(spec["category"]) for spec in load_task_specs())
    else:
        raise ValueError(f"unknown task_name {task_name!r}")
    samples = category_counts[str(category)] if category else sum(category_counts.values())
    return min(samples, sample_limit) if sample_limit is not None else samples


def estimate_experiment(config: ExperimentConfig) -> dict[str, Any]:
    """Return the exact grid size and configured aggregate budget exposure."""

    enabled_models = [model for model in config.models if model.enabled]
    categories: tuple[str | None, ...] = config.categories or (None,)
    samples_per_grid_slice = sum(
        sample_count_for_cell(
            config.task_name,
            category=category,
            sample_limit=config.sample_limit,
        )
        for category in categories
    )
    cell_count = (
        len(enabled_models) * len(config.baselines) * len(config.variants) * len(categories)
    )
    sample_executions_per_model = (
        len(config.baselines)
        * len(config.variants)
        * samples_per_grid_slice
        * config.repetitions
    )
    sample_executions = len(enabled_models) * sample_executions_per_model
    configured_cost_exposure = None
    if config.budget.cost_limit_usd is not None:
        configured_cost_exposure = float(
            (Decimal(str(config.budget.cost_limit_usd)) * sample_executions).quantize(
                Decimal("0.01"), rounding=ROUND_CEILING
            )
        )
    study_limit = config.budget.study_cost_limit_usd
    return {
        "schema_version": "1.0.0",
        "experiment_name": config.name,
        "task_name": config.task_name,
        "contains_publishable_models": any(model.publishable for model in enabled_models),
        "enabled_models": len(enabled_models),
        "enabled_model_ids": [model.model for model in enabled_models],
        "enabled_model_families": sorted({model.family for model in enabled_models}),
        "baselines": len(config.baselines),
        "variants": len(config.variants),
        "repetitions": config.repetitions,
        "unique_samples_per_variant": samples_per_grid_slice,
        "cell_count": cell_count,
        "sample_executions_per_model": sample_executions_per_model,
        "sample_executions": sample_executions,
        "per_sample_cost_limit_usd": config.budget.cost_limit_usd,
        "configured_cost_exposure_usd": configured_cost_exposure,
        "study_cost_limit_usd": study_limit,
        "within_study_cost_limit": (
            configured_cost_exposure <= study_limit
            if configured_cost_exposure is not None and study_limit is not None
            else None
        ),
        "aggregate_token_limit": sample_executions * config.budget.token_limit,
        "note": (
            "Configured exposure multiplies sample executions by Inspect's per-sample cost limit. "
            "Provider metering and the final in-flight request can produce small overruns."
        ),
    }


def validate_cost_preflight(config: ExperimentConfig, estimate: dict[str, Any]) -> None:
    """Reject a publishable grid whose configured exposure exceeds its study authorization."""

    if not estimate["contains_publishable_models"]:
        return
    if estimate["configured_cost_exposure_usd"] is None:
        raise ValueError("publishable experiments require a per-sample cost limit")
    if estimate["study_cost_limit_usd"] is None:
        raise ValueError("publishable experiments require a study cost limit")
    if not estimate["within_study_cost_limit"]:
        raise ValueError(
            "configured experiment exposure "
            f"${estimate['configured_cost_exposure_usd']:.2f} exceeds study cost limit "
            f"${estimate['study_cost_limit_usd']:.2f}"
        )
