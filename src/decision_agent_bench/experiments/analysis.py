"""Sanitized sample extraction, uncertainty estimates, and leaderboard generation."""

from __future__ import annotations

import csv
import json
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, fields
from pathlib import Path, PurePosixPath
from typing import Any

from inspect_ai.log import EvalLog, read_eval_log

from decision_agent_bench.evals.instances import expanded_instance_catalog
from decision_agent_bench.evals.scorer import SCORE_KEYS, parse_submission
from decision_agent_bench.experiments.manifest import load_manifest
from decision_agent_bench.experiments.schema import ExperimentConfig
from decision_agent_bench.integrity import (
    digest_payload as _digest_payload,
)
from decision_agent_bench.integrity import (
    file_evidence as _file_evidence,
)
from decision_agent_bench.integrity import (
    sha256_file as _sha256_file,
)
from decision_agent_bench.integrity import (
    verify_evidence_files as _verify_evidence_files,
)
from decision_agent_bench.specs import load_task_specs

ANALYSIS_ARTIFACTS = (
    "calibration.csv",
    "failure-counts.csv",
    "failure-matrix.csv",
    "leaderboard.md",
    "paired-effects.csv",
    "robustness-matrix.csv",
    "samples.sanitized.jsonl",
    "summary.csv",
    "summary.json",
)


def _source_log_evidence(paths: list[Path], log_directory: Path) -> list[dict[str, Any]]:
    evidence = []
    for path in sorted(paths):
        item = _file_evidence(path, relative_to=log_directory)
        item["status"] = str(read_eval_log(str(path)).status)
        evidence.append(item)
    return evidence


@dataclass(frozen=True)
class SampleRecord:
    """Shareable sample telemetry with prompts, targets, paths, and transcripts removed."""

    run_id: str
    benchmark_version: str
    task_version: str
    model: str
    model_family: str
    display_name: str
    publishable: bool
    baseline: str
    sample_id: str
    instance_id: str
    task_id: str
    scenario_seed: int
    category: str
    difficulty: str
    variant: str
    perturbation: str | None
    epoch: int
    scores: dict[str, float]
    confidence: float | None
    correct: bool
    failures: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_seconds: float
    working_seconds: float
    tool_calls: int
    recoveries: int
    turn_count: int


def _model_lookup(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not manifest:
        return {}
    return {
        str(model["model"]): model
        for model in manifest["config"]["models"]
        if model.get("enabled")
    }


def records_from_eval_log(
    log: EvalLog,
    *,
    manifest: dict[str, Any] | None = None,
) -> list[SampleRecord]:
    """Extract only publishable numeric telemetry from one Inspect log."""

    model_lookup = _model_lookup(manifest)
    model_name = str(log.eval.model)
    model = model_lookup.get(
        model_name,
        {
            "family": model_name.split("/", maxsplit=1)[0],
            "display_name": model_name,
            "publishable": not model_name.startswith("mockllm/"),
        },
    )
    task_args = log.eval.task_args or {}
    config = (manifest or {}).get("config", {})
    baseline = str(task_args.get("baseline", "custom"))
    run_id = str((manifest or {}).get("run_id", log.eval.run_id))
    records: list[SampleRecord] = []
    for sample in log.samples or []:
        score = (sample.scores or {}).get("decision_agent_scorer")
        if score is None or not isinstance(score.value, dict):
            continue
        values = {
            key: float(score.value.get(key, 0.0))
            for key in SCORE_KEYS
        }
        usage = sample.model_usage or {}
        input_tokens = sum(int(item.input_tokens or 0) for item in usage.values())
        output_tokens = sum(int(item.output_tokens or 0) for item in usage.values())
        costs = [float(item.total_cost) for item in usage.values() if item.total_cost is not None]
        metadata = sample.metadata or {}
        sample_id = str(sample.id)
        task_id = str(metadata.get("task_id", sample_id))
        instance_id = str(metadata.get("instance_id", f"{task_id}-i1"))
        sample_store = sample.store or {}
        tool_calls = sample_store.get("dab.tool_calls", [])
        recoveries = sample_store.get("dab.recoveries", [])
        failures = tuple(str(item) for item in (score.metadata or {}).get("failure_taxonomy", []))
        completion = str(getattr(sample.output, "completion", ""))
        submission = parse_submission(completion)
        raw_confidence = submission.get("confidence") if submission else None
        confidence = (
            max(0.0, min(1.0, float(raw_confidence)))
            if isinstance(raw_confidence, int | float)
            else None
        )
        correct = values["task_effectiveness"] >= 0.8 and values["safety"] == 1.0
        records.append(
            SampleRecord(
                run_id=run_id,
                benchmark_version=str(config.get("benchmark_version", log.eval.task_version)),
                task_version=str(
                    metadata.get("task_version", config.get("task_version", "unknown"))
                ),
                model=model_name,
                model_family=str(model["family"]),
                display_name=str(model["display_name"]),
                publishable=bool(model["publishable"]),
                baseline=baseline,
                sample_id=sample_id,
                instance_id=instance_id,
                task_id=task_id,
                scenario_seed=int(metadata.get("scenario_seed", 0)),
                category=str(metadata.get("category", "unknown")),
                difficulty=str(metadata.get("difficulty", "unknown")),
                variant=str(metadata.get("variant", task_args.get("variant", "unknown"))),
                perturbation=(
                    str(metadata["perturbation"])
                    if metadata.get("perturbation") is not None
                    else None
                ),
                epoch=int(sample.epoch or 1),
                scores=values,
                confidence=confidence,
                correct=correct,
                failures=failures,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=sum(costs) if costs else None,
                latency_seconds=float(sample.total_time or 0.0),
                working_seconds=float(sample.working_time or 0.0),
                tool_calls=len(tool_calls) if isinstance(tool_calls, list) else 0,
                recoveries=len(recoveries) if isinstance(recoveries, list) else 0,
                turn_count=int(sample.turn_count or 0),
            )
        )
    return records


def records_from_paths(
    paths: Iterable[Path],
    *,
    manifest: dict[str, Any] | None = None,
) -> list[SampleRecord]:
    """Read all successful Inspect logs and return sanitized records."""

    records: list[SampleRecord] = []
    for path in sorted(paths):
        log = read_eval_log(str(path))
        if log.status == "success":
            records.extend(records_from_eval_log(log, manifest=manifest))
    return records


def _cluster_bootstrap_ci(
    values: list[float],
    clusters: list[str],
    *,
    seed: int,
    draws: int = 2_000,
) -> tuple[float, float]:
    """Bootstrap whole task-family clusters to preserve within-family dependence."""

    if not values:
        return (0.0, 0.0)
    if len(values) != len(clusters):
        raise ValueError("values and clusters must have the same length")
    clustered: dict[str, list[float]] = defaultdict(list)
    for value, cluster in zip(values, clusters, strict=True):
        clustered[cluster].append(value)
    cluster_ids = sorted(clustered)
    observed = round(statistics.fmean(values), 6)
    if len(cluster_ids) == 1:
        return (observed, observed)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(draws):
        sampled = [rng.choice(cluster_ids) for _ in cluster_ids]
        draw_values = [value for cluster in sampled for value in clustered[cluster]]
        means.append(statistics.fmean(draw_values))
    means.sort()
    lower = means[math.floor(0.025 * (draws - 1))]
    upper = means[math.ceil(0.975 * (draws - 1))]
    return (round(lower, 6), round(upper, 6))


def _metric_summary(
    values: list[float], clusters: list[str], *, seed: int
) -> dict[str, float]:
    lower, upper = _cluster_bootstrap_ci(values, clusters, seed=seed)
    return {
        "mean": round(statistics.fmean(values), 6) if values else 0.0,
        "std": round(statistics.stdev(values), 6) if len(values) > 1 else 0.0,
        "ci95_low": lower,
        "ci95_high": upper,
    }


def _mean_within_instance_std(items: list[SampleRecord]) -> float:
    instance_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for item in items:
        instance_values[(item.run_id, item.instance_id)].append(item.scores["composite"])
    deviations = [
        statistics.stdev(values) for values in instance_values.values() if len(values) > 1
    ]
    return round(statistics.fmean(deviations), 6) if deviations else 0.0


def _wilson_interval(successes: int, total: int) -> tuple[float, float]:
    """Return the two-sided 95% Wilson score interval for a binomial proportion."""

    if total < 0 or not 0 <= successes <= total:
        raise ValueError("successes and total must define a valid binomial count")
    if total == 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    half_width = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2))
        / denominator
    )
    return (round(max(0.0, centre - half_width), 6), round(min(1.0, centre + half_width), 6))


def _calibration_summary(items: list[SampleRecord]) -> dict[str, Any]:
    eligible = [item for item in items if item.confidence is not None]
    bins: list[dict[str, Any]] = []
    for index in range(5):
        lower = index / 5
        upper = (index + 1) / 5
        members = [
            item
            for item in eligible
            if item.confidence is not None
            and lower <= item.confidence <= upper
            and (index == 4 or item.confidence < upper)
        ]
        mean_confidence = (
            statistics.fmean(float(item.confidence) for item in members) if members else None
        )
        accuracy = statistics.fmean(float(item.correct) for item in members) if members else None
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "n": len(members),
                "mean_confidence": (
                    round(mean_confidence, 6) if mean_confidence is not None else None
                ),
                "accuracy": round(accuracy, 6) if accuracy is not None else None,
                "absolute_gap": (
                    round(abs(mean_confidence - accuracy), 6)
                    if mean_confidence is not None and accuracy is not None
                    else None
                ),
            }
        )
    brier = (
        statistics.fmean((float(item.confidence) - float(item.correct)) ** 2 for item in eligible)
        if eligible
        else None
    )
    return {
        "eligible_n": len(eligible),
        "missing_or_invalid_n": len(items) - len(eligible),
        "brier_score": round(brier, 6) if brier is not None else None,
        "bins": bins,
    }


def summarize_records(records: list[SampleRecord], *, seed: int = 20260717) -> dict[str, Any]:
    """Aggregate metrics and paired robustness deltas with deterministic bootstrap CIs."""

    groups: dict[tuple[str, str, str], list[SampleRecord]] = defaultdict(list)
    for record in records:
        groups[(record.model, record.baseline, record.variant)].append(record)
    summaries: list[dict[str, Any]] = []
    for index, ((model, baseline, variant), items) in enumerate(sorted(groups.items())):
        failures = Counter(failure for item in items for failure in item.failures)
        summaries.append(
            {
                "model": model,
                "model_family": items[0].model_family,
                "display_name": items[0].display_name,
                "publishable": items[0].publishable,
                "baseline": baseline,
                "variant": variant,
                "n": len(items),
                "metrics": {
                    key: _metric_summary(
                        [item.scores[key] for item in items],
                        [item.task_id for item in items],
                        seed=seed + index * 101 + offset,
                    )
                    for offset, key in enumerate(SCORE_KEYS)
                },
                "input_tokens_mean": round(
                    statistics.fmean(item.input_tokens for item in items), 3
                ),
                "output_tokens_mean": round(
                    statistics.fmean(item.output_tokens for item in items), 3
                ),
                "latency_seconds_mean": round(
                    statistics.fmean(item.latency_seconds for item in items), 6
                ),
                "mean_within_instance_composite_std": _mean_within_instance_std(items),
                "cost_usd_total": round(
                    sum(item.cost_usd or 0.0 for item in items), 6
                ),
                "safety_violations": {
                    "count": sum(item.scores["safety"] < 1.0 for item in items),
                    "rate": round(
                        sum(item.scores["safety"] < 1.0 for item in items) / len(items), 6
                    ),
                    "wilson95_low": _wilson_interval(
                        sum(item.scores["safety"] < 1.0 for item in items), len(items)
                    )[0],
                    "wilson95_high": _wilson_interval(
                        sum(item.scores["safety"] < 1.0 for item in items), len(items)
                    )[1],
                },
                "calibration": _calibration_summary(items),
                "failure_counts": dict(sorted(failures.items())),
            }
        )

    indexed: dict[tuple[str, str, str, str, int, str], SampleRecord] = {}
    for record in records:
        key = (
            record.run_id,
            record.model,
            record.baseline,
            record.instance_id,
            record.epoch,
            record.variant,
        )
        if key in indexed:
            raise ValueError(f"duplicate analysis record for {key}")
        indexed[key] = record
    paired: dict[tuple[str, str], list[tuple[SampleRecord, SampleRecord]]] = defaultdict(list)
    for key, clean in indexed.items():
        run_id, model, baseline, instance_id, epoch, variant = key
        if variant != "clean":
            continue
        perturbed = indexed.get(
            (run_id, model, baseline, instance_id, epoch, "perturbed")
        )
        if perturbed:
            paired[(model, baseline)].append((clean, perturbed))
    robustness: list[dict[str, Any]] = []
    for index, ((model, baseline), paired_items) in enumerate(sorted(paired.items())):
        clusters = [clean.task_id for clean, _perturbed in paired_items]
        metric_deltas = {
            key: _metric_summary(
                [perturbed.scores[key] - clean.scores[key] for clean, perturbed in paired_items],
                clusters,
                seed=seed + 10_000 + index * 101 + offset,
            )
            for offset, key in enumerate(SCORE_KEYS)
        }
        resource_deltas = {
            "tool_calls": _metric_summary(
                [
                    float(perturbed.tool_calls - clean.tool_calls)
                    for clean, perturbed in paired_items
                ],
                clusters,
                seed=seed + 20_000 + index * 11,
            ),
            "total_tokens": _metric_summary(
                [
                    float(
                        perturbed.input_tokens
                        + perturbed.output_tokens
                        - clean.input_tokens
                        - clean.output_tokens
                    )
                    for clean, perturbed in paired_items
                ],
                clusters,
                seed=seed + 20_001 + index * 11,
            ),
            "latency_seconds": _metric_summary(
                [
                    perturbed.latency_seconds - clean.latency_seconds
                    for clean, perturbed in paired_items
                ],
                clusters,
                seed=seed + 20_002 + index * 11,
            ),
        }
        robustness.append(
            {
                "model": model,
                "baseline": baseline,
                "pairs": len(paired_items),
                "metric_deltas": metric_deltas,
                "resource_deltas": resource_deltas,
                "perturbed_minus_clean_composite": metric_deltas["composite"],
            }
        )
    return {
        "analysis_schema_version": "2.0.0",
        "uncertainty_method": "task-family cluster bootstrap (2,000 draws)",
        "groups": summaries,
        "paired_robustness": robustness,
    }


def _leaderboard_markdown(records: list[SampleRecord], coverage: dict[str, Any]) -> str:
    publishable = (
        [record for record in records if record.publishable]
        if coverage["publication_eligible"]
        else []
    )
    lines = [
        "# DecisionAgentBench leaderboard",
        "",
        "Only runs marked publishable in an immutable experiment manifest appear here. Mock and ",
        "development runs are excluded. Scores are descriptive until the run card documents at ",
        "least three repetitions across every sample in the claimed suite.",
        "",
    ]
    if not publishable:
        reason = coverage.get("reason", "No publishable model runs have been analyzed yet.")
        lines.append(f"_No publishable model runs: {reason}_")
        lines.append("")
        return "\n".join(lines)
    groups: dict[tuple[str, str, str], list[SampleRecord]] = defaultdict(list)
    for record in publishable:
        groups[(record.display_name, record.model, record.baseline)].append(record)
    rows = []
    for (display_name, model, baseline), items in groups.items():
        rows.append(
            {
                "display_name": display_name,
                "model": model,
                "baseline": baseline,
                "n": len(items),
                "composite": statistics.fmean(item.scores["composite"] for item in items),
                "safety": statistics.fmean(item.scores["safety"] for item in items),
                "robustness": statistics.fmean(item.scores["robustness"] for item in items),
                "reliability_std": _mean_within_instance_std(items),
                "tokens": statistics.fmean(
                    item.input_tokens + item.output_tokens for item in items
                ),
            }
        )
    rows.sort(key=lambda row: (-row["composite"], -row["safety"], row["model"]))
    lines.extend(
        [
            "| Rank | Model | Baseline | n | Composite | Safety | Robustness | "
            "Within-task SD | Mean tokens |",
            "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for rank, row in enumerate(rows, start=1):
        lines.append(
            f"| {rank} | {row['display_name']} | `{row['baseline']}` | {row['n']} | "
            f"{row['composite']:.3f} | {row['safety']:.3f} | {row['robustness']:.3f} | "
            f"{row['reliability_std']:.3f} | {row['tokens']:.0f} |"
        )
    lines.append("")
    return "\n".join(lines)


def _write_samples(records: list[SampleRecord], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")


def _portable_publication_plan(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip runtime paths/commands while retaining enough plan state to recompute coverage."""

    if manifest is None:
        return None
    return {
        "run_id": manifest["run_id"],
        "config": manifest["config"],
        "source": {
            "git_commit": manifest["source"]["git_commit"],
            "working_tree_clean": bool(manifest["source"].get("working_tree_clean", False)),
            "reference_world_sha256": manifest["source"]["reference_world_sha256"],
        },
        "cells": [
            {
                key: cell[key]
                for key in (
                    "cell_id",
                    "model",
                    "model_family",
                    "display_name",
                    "publishable",
                    "baseline",
                    "variant",
                    "category",
                )
            }
            for cell in manifest["cells"]
        ],
    }


def _read_sanitized_records(path: Path) -> tuple[list[SampleRecord], list[str]]:
    records: list[SampleRecord] = []
    issues: list[str] = []
    expected_fields = {field.name for field in fields(SampleRecord)}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return [], [f"sanitized samples are unreadable: {error}"]
    identities: set[tuple[str, str, str, str, str, int]] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            issues.append(f"sanitized sample line {line_number} is empty")
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            issues.append(f"sanitized sample line {line_number} is invalid JSON: {error}")
            continue
        if not isinstance(item, dict) or set(item) != expected_fields:
            issues.append(f"sanitized sample line {line_number} has an invalid field set")
            continue
        string_fields = {
            "run_id",
            "benchmark_version",
            "task_version",
            "model",
            "model_family",
            "display_name",
            "baseline",
            "sample_id",
            "instance_id",
            "task_id",
            "category",
            "difficulty",
            "variant",
        }
        if any(not isinstance(item[key], str) or not item[key] for key in string_fields):
            issues.append(f"sanitized sample line {line_number} has invalid text fields")
            continue
        integer_fields = {
            "scenario_seed",
            "epoch",
            "input_tokens",
            "output_tokens",
            "tool_calls",
            "recoveries",
            "turn_count",
        }
        if any(
            not isinstance(item[key], int) or isinstance(item[key], bool)
            for key in integer_fields
        ):
            issues.append(f"sanitized sample line {line_number} has invalid integer fields")
            continue
        if item["epoch"] < 1 or any(
            item[key] < 0 for key in integer_fields if key != "epoch"
        ):
            issues.append(f"sanitized sample line {line_number} has negative count fields")
            continue
        scores = item.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(SCORE_KEYS) or not all(
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and 0.0 <= float(value) <= 1.0
            for value in scores.values()
        ):
            issues.append(f"sanitized sample line {line_number} has invalid scores")
            continue
        failures = item.get("failures")
        if not isinstance(failures, list) or not all(
            isinstance(value, str) for value in failures
        ):
            issues.append(f"sanitized sample line {line_number} has invalid failures")
            continue
        confidence = item.get("confidence")
        if confidence is not None and (
            not isinstance(confidence, int | float)
            or isinstance(confidence, bool)
            or not math.isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            issues.append(f"sanitized sample line {line_number} has invalid confidence")
            continue
        cost = item.get("cost_usd")
        if cost is not None and (
            not isinstance(cost, int | float)
            or isinstance(cost, bool)
            or not math.isfinite(float(cost))
            or cost < 0
        ):
            issues.append(f"sanitized sample line {line_number} has invalid cost")
            continue
        durations = (item.get("latency_seconds"), item.get("working_seconds"))
        if any(
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or value < 0
            for value in durations
        ):
            issues.append(f"sanitized sample line {line_number} has invalid durations")
            continue
        if not isinstance(item.get("publishable"), bool) or not isinstance(
            item.get("correct"), bool
        ):
            issues.append(f"sanitized sample line {line_number} has invalid booleans")
            continue
        if item.get("perturbation") is not None and not isinstance(
            item["perturbation"], str
        ):
            issues.append(f"sanitized sample line {line_number} has invalid perturbation")
            continue
        item["failures"] = tuple(failures)
        try:
            record = SampleRecord(**item)
        except TypeError as error:
            issues.append(f"sanitized sample line {line_number} is invalid: {error}")
            continue
        if record.publishable and record.model.startswith("mockllm/"):
            issues.append(f"sanitized sample line {line_number} marks a mock model publishable")
            continue
        identity = (
            record.run_id,
            record.model,
            record.baseline,
            record.variant,
            record.sample_id,
            record.epoch,
        )
        if identity in identities:
            issues.append(f"sanitized sample line {line_number} duplicates a scored sample")
            continue
        identities.add(identity)
        records.append(record)
    return records, issues


def _manifest_from_publication_plan(
    plan: Any, records: list[SampleRecord]
) -> tuple[dict[str, Any] | None, list[str]]:
    if plan is None:
        return None, []
    if not isinstance(plan, dict):
        return None, ["publication plan must be an object"]
    issues: list[str] = []
    if set(plan) != {"run_id", "config", "source", "cells"}:
        issues.append("publication plan has an invalid field set")
    config_payload = plan.get("config")
    try:
        if not isinstance(config_payload, dict):
            raise ValueError("config must be an object")
        config = ExperimentConfig.from_dict(config_payload)
    except (TypeError, ValueError) as error:
        return None, [f"publication plan config is invalid: {error}"]
    if _digest_payload(config.to_dict()) != _digest_payload(config_payload):
        issues.append("publication plan config is not canonical and complete")
    run_id = plan.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        issues.append("publication plan run_id is missing")
    source = plan.get("source")
    if not isinstance(source, dict):
        issues.append("publication plan source must be an object")
        source = {}
    elif set(source) != {
        "git_commit",
        "working_tree_clean",
        "reference_world_sha256",
    }:
        issues.append("publication plan source has an invalid field set")
    if re.fullmatch(r"[0-9a-f]{40}", str(source.get("git_commit", ""))) is None:
        issues.append("publication plan source commit must be a full Git SHA")
    if source.get("working_tree_clean") is not True:
        issues.append("publication plan source is not clean")
    if re.fullmatch(
        r"[0-9a-f]{64}", str(source.get("reference_world_sha256", ""))
    ) is None:
        issues.append("publication plan reference-world digest is invalid")

    cells = plan.get("cells")
    if not isinstance(cells, list):
        return None, [*issues, "publication plan cells must be a list"]
    enabled_models = {model.model: model for model in config.models if model.enabled}
    categories: tuple[str | None, ...] = config.categories or (None,)
    expected_cells = {
        (model.model, baseline, variant, category)
        for model in enabled_models.values()
        for baseline in config.baselines
        for variant in config.variants
        for category in categories
    }
    observed_cells: set[tuple[str, str, str, str | None]] = set()
    cell_ids: set[str] = set()
    required_cell_fields = {
        "cell_id",
        "model",
        "model_family",
        "display_name",
        "publishable",
        "baseline",
        "variant",
        "category",
    }
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict) or set(cell) != required_cell_fields:
            issues.append(f"publication plan cell {index} has an invalid field set")
            continue
        identity = (
            str(cell["model"]),
            str(cell["baseline"]),
            str(cell["variant"]),
            str(cell["category"]) if cell["category"] is not None else None,
        )
        if identity in observed_cells:
            issues.append(f"publication plan cell {index} duplicates a grid cell")
        observed_cells.add(identity)
        cell_id = str(cell["cell_id"])
        if not cell_id or cell_id in cell_ids:
            issues.append(f"publication plan cell {index} has a duplicate or empty cell_id")
        cell_ids.add(cell_id)
        model = enabled_models.get(str(cell["model"]))
        if model is None:
            issues.append(f"publication plan cell {index} uses a disabled or unknown model")
        elif (
            cell["publishable"] is not model.publishable
            or cell["model_family"] != model.family
            or cell["display_name"] != model.display_name
        ):
            issues.append(f"publication plan cell {index} model metadata is inconsistent")
    if observed_cells != expected_cells:
        issues.append("publication plan cells do not match the configured experiment grid")
    for index, record in enumerate(records):
        model = enabled_models.get(record.model)
        if model is None:
            issues.append(f"sanitized record {index} uses a disabled or unknown model")
        elif (
            record.publishable is not model.publishable
            or record.model_family != model.family
            or record.display_name != model.display_name
        ):
            issues.append(f"sanitized record {index} model metadata is inconsistent")
    if issues:
        return None, issues
    return {
        "run_id": run_id,
        "config": config_payload,
        "cells": cells,
    }, []


def _write_group_csv(summary: dict[str, Any], path: Path) -> None:
    fieldnames = [
        "model",
        "model_family",
        "display_name",
        "baseline",
        "variant",
        "n",
        *[f"{key}_mean" for key in SCORE_KEYS],
        "input_tokens_mean",
        "output_tokens_mean",
        "latency_seconds_mean",
        "mean_within_instance_composite_std",
        "cost_usd_total",
        "safety_violation_count",
        "safety_violation_rate",
        "safety_violation_wilson95_low",
        "safety_violation_wilson95_high",
        "calibration_eligible_n",
        "brier_score",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for group in summary["groups"]:
            row = {key: group[key] for key in fieldnames if key in group}
            row.update(
                {f"{key}_mean": group["metrics"][key]["mean"] for key in SCORE_KEYS}
            )
            row.update(
                {
                    "safety_violation_count": group["safety_violations"]["count"],
                    "safety_violation_rate": group["safety_violations"]["rate"],
                    "safety_violation_wilson95_low": group["safety_violations"][
                        "wilson95_low"
                    ],
                    "safety_violation_wilson95_high": group["safety_violations"][
                        "wilson95_high"
                    ],
                    "calibration_eligible_n": group["calibration"]["eligible_n"],
                    "brier_score": group["calibration"]["brier_score"],
                }
            )
            writer.writerow(row)


def _write_calibration_csv(summary: dict[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "model",
                "baseline",
                "variant",
                "bin_lower",
                "bin_upper",
                "n",
                "mean_confidence",
                "accuracy",
                "absolute_gap",
            ]
        )
        for group in summary["groups"]:
            for item in group["calibration"]["bins"]:
                writer.writerow(
                    [
                        group["model"],
                        group["baseline"],
                        group["variant"],
                        item["lower"],
                        item["upper"],
                        item["n"],
                        item["mean_confidence"],
                        item["accuracy"],
                        item["absolute_gap"],
                    ]
                )


def _write_paired_effects_csv(summary: dict[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "model",
                "baseline",
                "pairs",
                "measure",
                "mean_delta",
                "std_delta",
                "ci95_low",
                "ci95_high",
            ]
        )
        for comparison in summary["paired_robustness"]:
            measures = {
                **comparison["metric_deltas"],
                **{
                    f"resource:{key}": value
                    for key, value in comparison["resource_deltas"].items()
                },
            }
            for measure, values in measures.items():
                writer.writerow(
                    [
                        comparison["model"],
                        comparison["baseline"],
                        comparison["pairs"],
                        measure,
                        values["mean"],
                        values["std"],
                        values["ci95_low"],
                        values["ci95_high"],
                    ]
                )


def _coverage_report(
    records: list[SampleRecord], manifest: dict[str, Any] | None
) -> dict[str, Any]:
    """Verify result counts against every immutable manifest cell."""

    if manifest is None:
        return {
            "verified": False,
            "publication_eligible": False,
            "reason": "an immutable experiment manifest was not supplied",
            "cells": [],
            "unexpected_records": len(records),
        }
    config = manifest["config"]
    repetitions = int(config["repetitions"])
    sample_limit = config.get("sample_limit")
    cell_reports: list[dict[str, Any]] = []
    claimed_records: set[int] = set()
    for cell in manifest["cells"]:
        category = cell.get("category")
        task_name = str(config["task_name"])
        selected_category = str(category) if category is not None else None
        if task_name == "decision_agent_bench_v0_2":
            catalog = [
                {
                    "sample_id": item[f"{cell['variant']}_sample_id"],
                    "instance_id": item["instance_id"],
                    "task_id": item["family_id"],
                    "task_version": item["contract_version"],
                    "scenario_seed": item["scenario_seed"],
                    "category": item["category"],
                    "difficulty": item["difficulty"],
                    "perturbation": (
                        item["perturbation"] if cell["variant"] == "perturbed" else None
                    ),
                }
                for item in expanded_instance_catalog()
                if selected_category is None or item["category"] == selected_category
            ]
        else:
            catalog = [
                {
                    "sample_id": f"{spec['id']}-{cell['variant']}",
                    "instance_id": f"{spec['id']}-i1",
                    "task_id": spec["id"],
                    "task_version": spec["version"],
                    "scenario_seed": 20260717,
                    "category": spec["category"],
                    "difficulty": spec["difficulty"],
                    "perturbation": (
                        spec["perturbations"][0]
                        if cell["variant"] == "perturbed"
                        else None
                    ),
                }
                for spec in load_task_specs()
                if selected_category is None or spec["category"] == selected_category
            ]
        if sample_limit is not None:
            catalog = catalog[: int(sample_limit)]
        samples_per_epoch = len(catalog)
        expected = samples_per_epoch * repetitions
        matching = [
            (position, record)
            for position, record in enumerate(records)
            if record.run_id == manifest["run_id"]
            and record.model == cell["model"]
            and record.baseline == cell["baseline"]
            and record.variant == cell["variant"]
            and (category is None or record.category == category)
        ]
        claimed_records.update(position for position, _record in matching)
        observed = len(matching)
        expected_identities = {
            (str(sample["sample_id"]), epoch)
            for sample in catalog
            for epoch in range(1, repetitions + 1)
        }
        observed_identities = {(record.sample_id, record.epoch) for _, record in matching}
        expected_metadata = {str(sample["sample_id"]): sample for sample in catalog}
        invalid_metadata = sum(
            expected_metadata.get(record.sample_id) is None
            or any(
                getattr(record, key) != expected_metadata[record.sample_id][key]
                for key in (
                    "instance_id",
                    "task_id",
                    "task_version",
                    "scenario_seed",
                    "category",
                    "difficulty",
                    "perturbation",
                )
            )
            or record.variant != cell["variant"]
            or (
                "benchmark_version" in config
                and record.benchmark_version != config["benchmark_version"]
            )
            for _, record in matching
        )
        cell_reports.append(
            {
                "cell_id": cell["cell_id"],
                "publishable": bool(cell["publishable"]),
                "expected": expected,
                "observed": observed,
                "invalid_records": invalid_metadata,
                "complete": (
                    observed == expected
                    and observed_identities == expected_identities
                    and invalid_metadata == 0
                ),
            }
        )
    unexpected = len(records) - len(claimed_records)
    publishable_cells = [cell for cell in cell_reports if cell["publishable"]]
    publication_eligible = (
        bool(publishable_cells)
        and all(cell["complete"] for cell in publishable_cells)
        and unexpected == 0
    )
    if publication_eligible:
        reason = "all publishable manifest cells have complete expected coverage"
    elif not publishable_cells:
        reason = "the manifest contains no publishable model cells"
    elif unexpected:
        reason = f"{unexpected} records do not match a manifest cell"
    else:
        incomplete = sum(not cell["complete"] for cell in publishable_cells)
        reason = f"{incomplete} publishable manifest cells have incomplete coverage"
    return {
        "verified": True,
        "publication_eligible": publication_eligible,
        "reason": reason,
        "cells": cell_reports,
        "unexpected_records": unexpected,
    }


def _write_robustness_matrix(records: list[SampleRecord], path: Path) -> None:
    groups: dict[tuple[str, str, str, str, str], list[SampleRecord]] = defaultdict(list)
    for record in records:
        groups[
            (
                record.model,
                record.baseline,
                record.category,
                record.variant,
                record.perturbation or "none",
            )
        ].append(record)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "model",
                "baseline",
                "category",
                "variant",
                "perturbation",
                "n",
                "composite_mean",
                "safety_mean",
                "recovery_mean",
            ]
        )
        for key, items in sorted(groups.items()):
            writer.writerow(
                [
                    *key,
                    len(items),
                    round(statistics.fmean(item.scores["composite"] for item in items), 6),
                    round(statistics.fmean(item.scores["safety"] for item in items), 6),
                    round(statistics.fmean(item.scores["recovery"] for item in items), 6),
                ]
            )


def _write_failure_matrix(records: list[SampleRecord], path: Path) -> None:
    all_failures = sorted({failure for record in records for failure in record.failures})
    groups: dict[tuple[str, str, str], list[SampleRecord]] = defaultdict(list)
    for record in records:
        groups[(record.model, record.baseline, record.variant)].append(record)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", "baseline", "variant", "n", *all_failures])
        for key, items in sorted(groups.items()):
            counts = Counter(failure for item in items for failure in item.failures)
            writer.writerow([*key, len(items), *[counts[failure] for failure in all_failures]])


def analyze_logs(
    log_directory: Path,
    output_directory: Path,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Analyze `.eval` logs and write only sanitized, shareable result artifacts."""

    manifest = load_manifest(manifest_path) if manifest_path else None
    log_directory = log_directory.resolve()
    output_directory = output_directory.resolve()
    paths = sorted(log_directory.rglob("*.eval"))
    source_log_evidence = _source_log_evidence(paths, log_directory)
    records = records_from_paths(paths, manifest=manifest)
    if not records:
        raise ValueError(f"no completed scored samples found under {log_directory}")
    if output_directory.exists() and any(output_directory.iterdir()):
        raise ValueError(f"analysis output directory is not empty: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)
    summary = summarize_records(records)
    coverage = _coverage_report(records, manifest)
    _write_samples(records, output_directory / "samples.sanitized.jsonl")
    (output_directory / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_group_csv(summary, output_directory / "summary.csv")
    _write_calibration_csv(summary, output_directory / "calibration.csv")
    _write_paired_effects_csv(summary, output_directory / "paired-effects.csv")
    _write_robustness_matrix(records, output_directory / "robustness-matrix.csv")
    _write_failure_matrix(records, output_directory / "failure-matrix.csv")
    (output_directory / "leaderboard.md").write_text(
        _leaderboard_markdown(records, coverage), encoding="utf-8"
    )
    failures = Counter(failure for record in records for failure in record.failures)
    if source_log_evidence != _source_log_evidence(paths, log_directory):
        raise ValueError("source logs changed while analysis was running")
    log_status_counts = Counter(str(item["status"]) for item in source_log_evidence)
    with (output_directory / "failure-counts.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["failure_code", "count"])
        writer.writerows(sorted(failures.items()))
    experiment_manifest = None
    if manifest is not None and manifest_path is not None:
        experiment_manifest = {
            "sha256": _sha256_file(manifest_path),
            "manifest_sha256": manifest["manifest_sha256"],
            "run_id": manifest["run_id"],
            "source_git_commit": manifest["source"]["git_commit"],
            "source_working_tree_clean": bool(
                manifest["source"].get("working_tree_clean", False)
            ),
            "publication_plan": _portable_publication_plan(manifest),
        }
    analysis_manifest = {
        "schema_version": "2.0.0",
        "source_log_count": len(paths),
        "source_logs": source_log_evidence,
        "source_log_status_counts": dict(sorted(log_status_counts.items())),
        "scored_samples": len(records),
        "run_ids": sorted({record.run_id for record in records}),
        "contains_publishable_runs": (
            coverage["publication_eligible"]
            and bool(source_log_evidence)
            and log_status_counts["success"] > 0
        ),
        "coverage": coverage,
        "experiment_manifest": experiment_manifest,
        "artifacts": [
            _file_evidence(output_directory / name, relative_to=output_directory)
            for name in ANALYSIS_ARTIFACTS
        ],
        "sanitization": (
            "Prompts, hidden targets, transcripts, tool results, environment paths, and raw "
            "provider requests are excluded."
        ),
    }
    analysis_manifest["manifest_sha256"] = _digest_payload(analysis_manifest)
    (output_directory / "analysis-manifest.json").write_text(
        json.dumps(analysis_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return analysis_manifest


def verify_analysis_bundle(
    analysis_directory: Path,
    *,
    log_directory: Path | None = None,
    manifest_path: Path | None = None,
    require_sources: bool = False,
) -> dict[str, Any]:
    """Verify a result bundle and, when supplied, its raw-log and experiment provenance."""

    analysis_directory = analysis_directory.resolve()
    try:
        payload = json.loads(
            (analysis_directory / "analysis-manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        return {
            "schema_version": "1.0.0",
            "verified": False,
            "full_provenance_verified": False,
            "analysis_manifest_sha256": None,
            "artifact_count": 0,
            "contains_publishable_runs": False,
            "source_log_count": 0,
            "source_logs_supplied": log_directory is not None,
            "experiment_manifest_supplied": manifest_path is not None,
            "issues": [f"analysis manifest is missing or invalid: {error}"],
        }
    if not isinstance(payload, dict):
        return {
            "schema_version": "1.0.0",
            "verified": False,
            "full_provenance_verified": False,
            "analysis_manifest_sha256": None,
            "artifact_count": 0,
            "contains_publishable_runs": False,
            "source_log_count": 0,
            "source_logs_supplied": log_directory is not None,
            "experiment_manifest_supplied": manifest_path is not None,
            "issues": ["analysis manifest must be a JSON object"],
        }
    issues: list[str] = []
    expected_manifest_fields = {
        "schema_version",
        "source_log_count",
        "source_logs",
        "source_log_status_counts",
        "scored_samples",
        "run_ids",
        "contains_publishable_runs",
        "coverage",
        "experiment_manifest",
        "artifacts",
        "sanitization",
        "manifest_sha256",
    }
    if set(payload) != expected_manifest_fields:
        issues.append("analysis manifest has an invalid field set")
    if not isinstance(payload.get("sanitization"), str) or not payload["sanitization"]:
        issues.append("analysis sanitization statement is missing")
    expected_manifest_sha256 = payload.get("manifest_sha256")
    unsigned_payload = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    if payload.get("schema_version") != "2.0.0":
        issues.append("unsupported analysis manifest schema")
    if expected_manifest_sha256 != _digest_payload(unsigned_payload):
        issues.append("analysis manifest hash mismatch")

    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        issues.append("analysis artifacts must be a list")
        artifacts = []
    artifact_issues, artifact_paths = _verify_evidence_files(analysis_directory, artifacts)
    issues.extend(artifact_issues)
    if artifact_paths != set(ANALYSIS_ARTIFACTS):
        issues.append("declared artifact set does not match the analysis schema")
    actual_artifact_paths = {
        path.relative_to(analysis_directory).as_posix()
        for path in analysis_directory.rglob("*")
        if path.is_file() and path.name != "analysis-manifest.json"
    }
    if actual_artifact_paths != artifact_paths:
        missing = sorted(artifact_paths - actual_artifact_paths)
        unexpected = sorted(actual_artifact_paths - artifact_paths)
        if missing:
            issues.append(f"artifact set is missing entries: {missing}")
        if unexpected:
            issues.append(f"artifact set has unexpected entries: {unexpected}")

    records, record_issues = _read_sanitized_records(
        analysis_directory / "samples.sanitized.jsonl"
    )
    issues.extend(record_issues)
    if payload.get("scored_samples") != len(records):
        issues.append("scored-sample count does not match sanitized records")
    run_ids = sorted({record.run_id for record in records})
    if payload.get("run_ids") != run_ids:
        issues.append("run IDs do not match sanitized records")

    source_log_issues: list[str] | None = None
    source_logs = payload.get("source_logs", [])
    source_evidence_valid = True
    if not isinstance(source_logs, list):
        issues.append("source logs must be a list")
        source_logs = []
        source_evidence_valid = False
    source_paths_seen: set[str] = set()
    for index, item in enumerate(source_logs):
        if not isinstance(item, dict) or set(item) != {
            "path",
            "bytes",
            "sha256",
            "status",
        }:
            issues.append(f"source-log evidence {index} has an invalid field set")
            source_evidence_valid = False
            continue
        path = item["path"]
        portable_path = PurePosixPath(path) if isinstance(path, str) else None
        if (
            portable_path is None
            or portable_path.is_absolute()
            or not portable_path.parts
            or ".." in portable_path.parts
            or portable_path.suffix != ".eval"
            or path in source_paths_seen
        ):
            issues.append(f"source-log evidence {index} has an unsafe or duplicate path")
            source_evidence_valid = False
        else:
            source_paths_seen.add(path)
        if (
            not isinstance(item["bytes"], int)
            or isinstance(item["bytes"], bool)
            or item["bytes"] < 0
            or re.fullmatch(r"[0-9a-f]{64}", str(item["sha256"])) is None
            or not isinstance(item["status"], str)
            or not item["status"]
        ):
            issues.append(f"source-log evidence {index} has invalid metadata")
            source_evidence_valid = False
    if payload.get("source_log_count") != len(source_logs):
        issues.append("source-log count does not match the evidence list")
        source_evidence_valid = False
    declared_status_counts = Counter(
        str(item.get("status")) for item in source_logs if isinstance(item, dict)
    )
    if payload.get("source_log_status_counts") != dict(sorted(declared_status_counts.items())):
        issues.append("source-log status counts do not match the evidence list")
        source_evidence_valid = False
    if log_directory is not None:
        resolved_logs = log_directory.resolve()
        source_log_issues, source_paths = _verify_evidence_files(
            resolved_logs, source_logs, suffix=".eval"
        )
        actual_source_paths = {
            path.relative_to(resolved_logs).as_posix()
            for path in resolved_logs.rglob("*.eval")
            if path.is_file()
        }
        if actual_source_paths != source_paths:
            source_log_issues.append("source-log file set differs from the analysis manifest")
        for item in source_logs:
            if not isinstance(item, dict) or str(item.get("path")) not in source_paths:
                continue
            path = resolved_logs / str(item["path"])
            if not path.is_file():
                continue
            try:
                status = str(read_eval_log(str(path)).status)
            except (OSError, ValueError) as error:
                source_log_issues.append(f"unreadable source log {item['path']}: {error}")
            else:
                if status != item.get("status"):
                    source_log_issues.append(f"status mismatch: {item['path']}")
        issues.extend(source_log_issues)
        if source_log_issues:
            source_evidence_valid = False
    elif require_sources:
        issues.append("source-log directory is required")

    experiment_manifest_issues: list[str] | None = None
    expected_experiment_manifest = payload.get("experiment_manifest")
    if expected_experiment_manifest is not None:
        required_evidence_fields = {
            "sha256",
            "manifest_sha256",
            "run_id",
            "source_git_commit",
            "source_working_tree_clean",
            "publication_plan",
        }
        if (
            not isinstance(expected_experiment_manifest, dict)
            or set(expected_experiment_manifest) != required_evidence_fields
        ):
            issues.append("experiment manifest evidence has an invalid field set")
        else:
            if re.fullmatch(
                r"[0-9a-f]{64}", str(expected_experiment_manifest["sha256"])
            ) is None or re.fullmatch(
                r"[0-9a-f]{64}", str(expected_experiment_manifest["manifest_sha256"])
            ) is None:
                issues.append("experiment manifest evidence has invalid digests")
            if not isinstance(expected_experiment_manifest["run_id"], str) or not isinstance(
                expected_experiment_manifest["source_working_tree_clean"], bool
            ):
                issues.append("experiment manifest evidence has invalid control fields")
            if re.fullmatch(
                r"[0-9a-f]{40}",
                str(expected_experiment_manifest["source_git_commit"]),
            ) is None:
                issues.append("experiment manifest evidence has an invalid source commit")
    publication_plan = (
        expected_experiment_manifest.get("publication_plan")
        if isinstance(expected_experiment_manifest, dict)
        else None
    )
    portable_manifest, plan_issues = _manifest_from_publication_plan(
        publication_plan, records
    )
    issues.extend(plan_issues)
    if isinstance(expected_experiment_manifest, dict) and isinstance(publication_plan, dict):
        plan_source = publication_plan.get("source")
        if (
            expected_experiment_manifest.get("run_id") != publication_plan.get("run_id")
            or not isinstance(plan_source, dict)
            or expected_experiment_manifest.get("source_git_commit")
            != plan_source.get("git_commit")
            or expected_experiment_manifest.get("source_working_tree_clean")
            is not plan_source.get("working_tree_clean")
        ):
            issues.append("experiment manifest evidence does not match the publication plan")
    recomputed_coverage = _coverage_report(records, portable_manifest)
    if payload.get("coverage") != recomputed_coverage:
        issues.append("coverage report does not match sanitized records and publication plan")
    evidence_is_publishable = (
        recomputed_coverage["publication_eligible"]
        and bool(source_logs)
        and declared_status_counts["success"] > 0
        and source_evidence_valid
        and isinstance(expected_experiment_manifest, dict)
        and not plan_issues
    )
    if payload.get("contains_publishable_runs") is not evidence_is_publishable:
        issues.append("publishable-results claim does not match recomputed evidence")
    if manifest_path is not None:
        experiment_manifest_issues = []
        try:
            experiment_manifest = load_manifest(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            experiment_manifest_issues.append(f"invalid experiment manifest: {error}")
        else:
            if expected_experiment_manifest is None:
                experiment_manifest_issues.append(
                    "analysis did not declare an experiment manifest"
                )
            else:
                comparisons = {
                    "sha256": _sha256_file(manifest_path),
                    "manifest_sha256": experiment_manifest["manifest_sha256"],
                    "run_id": experiment_manifest["run_id"],
                    "source_git_commit": experiment_manifest["source"]["git_commit"],
                    "source_working_tree_clean": bool(
                        experiment_manifest["source"].get("working_tree_clean", False)
                    ),
                    "publication_plan": _portable_publication_plan(experiment_manifest),
                }
                if comparisons != expected_experiment_manifest:
                    experiment_manifest_issues.append("experiment manifest evidence mismatch")
        issues.extend(experiment_manifest_issues)
    elif require_sources:
        issues.append(
            "experiment manifest is required"
            if expected_experiment_manifest is not None
            else "analysis did not declare an experiment manifest"
        )

    return {
        "schema_version": "1.0.0",
        "verified": not issues,
        "full_provenance_verified": (
            not issues
            and log_directory is not None
            and expected_experiment_manifest is not None
            and manifest_path is not None
        ),
        "analysis_manifest_sha256": expected_manifest_sha256,
        "artifact_count": len(artifact_paths),
        "contains_publishable_runs": evidence_is_publishable,
        "source_log_count": len(source_logs),
        "source_logs_supplied": log_directory is not None,
        "experiment_manifest_supplied": manifest_path is not None,
        "issues": issues,
    }
