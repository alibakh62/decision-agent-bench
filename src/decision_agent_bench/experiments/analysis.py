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

from decision_agent_bench.evals.scorer import SCORE_KEYS
from decision_agent_bench.experiments.manifest import load_manifest


@dataclass(frozen=True)
class SampleRecord:
    """Shareable sample telemetry with prompts, targets, paths, and transcripts removed."""

    run_id: str
    model: str
    model_family: str
    display_name: str
    publishable: bool
    baseline: str
    task_id: str
    category: str
    difficulty: str
    variant: str
    perturbation: str | None
    epoch: int
    scores: dict[str, float]
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
        sample_store = sample.store or {}
        tool_calls = sample_store.get("dab.tool_calls", [])
        recoveries = sample_store.get("dab.recoveries", [])
        failures = tuple(str(item) for item in (score.metadata or {}).get("failure_taxonomy", []))
        records.append(
            SampleRecord(
                run_id=run_id,
                model=model_name,
                model_family=str(model["family"]),
                display_name=str(model["display_name"]),
                publishable=bool(model["publishable"]),
                baseline=baseline,
                task_id=str(metadata.get("task_id", sample.id)),
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


def _bootstrap_ci(values: list[float], *, seed: int, draws: int = 2_000) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (values[0], values[0])
    rng = random.Random(seed)
    means = sorted(
        statistics.fmean(rng.choice(values) for _ in values)
        for _ in range(draws)
    )
    lower = means[math.floor(0.025 * (draws - 1))]
    upper = means[math.ceil(0.975 * (draws - 1))]
    return (round(lower, 6), round(upper, 6))


def _metric_summary(values: list[float], *, seed: int) -> dict[str, float]:
    lower, upper = _bootstrap_ci(values, seed=seed)
    return {
        "mean": round(statistics.fmean(values), 6) if values else 0.0,
        "std": round(statistics.stdev(values), 6) if len(values) > 1 else 0.0,
        "ci95_low": lower,
        "ci95_high": upper,
    }


def _mean_within_task_std(items: list[SampleRecord]) -> float:
    task_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for item in items:
        task_values[(item.run_id, item.task_id)].append(item.scores["composite"])
    deviations = [
        statistics.stdev(values) for values in task_values.values() if len(values) > 1
    ]
    return round(statistics.fmean(deviations), 6) if deviations else 0.0


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
                        [item.scores[key] for item in items], seed=seed + index * 101 + offset
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
                "mean_within_task_composite_std": _mean_within_task_std(items),
                "cost_usd_total": round(
                    sum(item.cost_usd or 0.0 for item in items), 6
                ),
                "failure_counts": dict(sorted(failures.items())),
            }
        )

    paired: dict[tuple[str, str], list[float]] = defaultdict(list)
    indexed = {
        (
            record.run_id,
            record.model,
            record.baseline,
            record.task_id,
            record.epoch,
            record.variant,
        ): record
        for record in records
    }
    for key, clean in indexed.items():
        run_id, model, baseline, task_id, epoch, variant = key
        if variant != "clean":
            continue
        perturbed = indexed.get(
            (run_id, model, baseline, task_id, epoch, "perturbed")
        )
        if perturbed:
            paired[(model, baseline)].append(
                perturbed.scores["composite"] - clean.scores["composite"]
            )
    robustness: list[dict[str, Any]] = []
    for index, ((model, baseline), deltas) in enumerate(sorted(paired.items())):
        robustness.append(
            {
                "model": model,
                "baseline": baseline,
                "pairs": len(deltas),
                "perturbed_minus_clean_composite": _metric_summary(
                    deltas, seed=seed + 10_000 + index
                ),
            }
        )
    return {"groups": summaries, "paired_robustness": robustness}


def _leaderboard_markdown(records: list[SampleRecord]) -> str:
    publishable = [record for record in records if record.publishable]
    lines = [
        "# DecisionAgentBench leaderboard",
        "",
        "Only runs marked publishable in an immutable experiment manifest appear here. Mock and ",
        "development runs are excluded. Scores are descriptive until the run card documents at ",
        "least three repetitions across all 50 v0.1 samples.",
        "",
    ]
    if not publishable:
        lines.append("_No publishable model runs have been analyzed yet._")
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
                "reliability_std": _mean_within_task_std(items),
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
        "mean_within_task_composite_std",
        "cost_usd_total",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for group in summary["groups"]:
            row = {key: group[key] for key in fieldnames if key in group}
            row.update(
                {f"{key}_mean": group["metrics"][key]["mean"] for key in SCORE_KEYS}
            )
            writer.writerow(row)


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
    _write_samples(records, output_directory / "samples.sanitized.jsonl")
    (output_directory / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_group_csv(summary, output_directory / "summary.csv")
    _write_robustness_matrix(records, output_directory / "robustness-matrix.csv")
    _write_failure_matrix(records, output_directory / "failure-matrix.csv")
    (output_directory / "leaderboard.md").write_text(
        _leaderboard_markdown(records), encoding="utf-8"
    )
    failures = Counter(failure for record in records for failure in record.failures)
    with (output_directory / "failure-counts.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["failure_code", "count"])
        writer.writerows(sorted(failures.items()))
    analysis_manifest = {
        "source_logs": len(paths),
        "scored_samples": len(records),
        "run_ids": sorted({record.run_id for record in records}),
        "contains_publishable_runs": any(record.publishable for record in records),
        "sanitization": (
            "Prompts, hidden targets, transcripts, tool results, environment paths, and raw "
            "provider requests are excluded."
        ),
    }
    (output_directory / "analysis-manifest.json").write_text(
        json.dumps(analysis_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return analysis_manifest
