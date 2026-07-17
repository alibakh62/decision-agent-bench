"""Sanitized sample extraction, uncertainty estimates, and leaderboard generation."""

from __future__ import annotations

import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalLog, read_eval_log

from decision_agent_bench.evals.scorer import SCORE_KEYS, parse_submission
from decision_agent_bench.experiments.manifest import load_manifest
from decision_agent_bench.specs import load_task_specs


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
    instances_per_family = 4 if config["task_name"] == "decision_agent_bench_v0_2" else 1
    category_counts = Counter(str(spec["category"]) for spec in load_task_specs())
    repetitions = int(config["repetitions"])
    sample_limit = config.get("sample_limit")
    cell_reports: list[dict[str, Any]] = []
    claimed_records: set[int] = set()
    for cell in manifest["cells"]:
        category = cell.get("category")
        family_count = category_counts[str(category)] if category else sum(category_counts.values())
        samples_per_epoch = family_count * instances_per_family
        if sample_limit is not None:
            samples_per_epoch = min(samples_per_epoch, int(sample_limit))
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
        cell_reports.append(
            {
                "cell_id": cell["cell_id"],
                "publishable": bool(cell["publishable"]),
                "expected": expected,
                "observed": observed,
                "complete": observed == expected,
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
    paths = list(log_directory.rglob("*.eval"))
    records = records_from_paths(paths, manifest=manifest)
    if not records:
        raise ValueError(f"no completed scored samples found under {log_directory}")
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
    log_status_counts = Counter(str(read_eval_log(str(path)).status) for path in paths)
    with (output_directory / "failure-counts.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["failure_code", "count"])
        writer.writerows(sorted(failures.items()))
    analysis_manifest = {
        "source_logs": len(paths),
        "source_log_status_counts": dict(sorted(log_status_counts.items())),
        "scored_samples": len(records),
        "run_ids": sorted({record.run_id for record in records}),
        "contains_publishable_runs": coverage["publication_eligible"],
        "coverage": coverage,
        "sanitization": (
            "Prompts, hidden targets, transcripts, tool results, environment paths, and raw "
            "provider requests are excluded."
        ),
    }
    (output_directory / "analysis-manifest.json").write_text(
        json.dumps(analysis_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return analysis_manifest
