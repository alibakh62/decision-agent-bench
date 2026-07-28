"""Structural and empirical dependence audit for benchmark score dimensions."""

from __future__ import annotations

import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from decision_agent_bench.evals.scorer import SCORE_KEYS
from decision_agent_bench.integrity import digest_payload, sha256_file

METRIC_DEPENDENCE_SCHEMA_VERSION = "1.0.0"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON object key: {key}")
        payload[key] = value
    return payload


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant: {value}")


def _strict_json(value: str) -> Any:
    return json.loads(
        value,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_nonstandard_constant,
    )


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_ss = sum((value - left_mean) ** 2 for value in left)
    right_ss = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_ss * right_ss)
    if denominator == 0:
        return None
    return max(-1.0, min(1.0, numerator / denominator))


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2
        for original_index, _value in ordered[index:end]:
            ranks[original_index] = average_rank
        index = end
    return ranks


def _spearman(left: list[float], right: list[float]) -> float | None:
    return _pearson(_ranks(left), _ranks(right))


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def _round_optional(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = _strict_json(line)
        except (ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid JSON on line {line_number}: {error}") from error
        if not isinstance(payload, dict):
            raise ValueError(f"line {line_number} must be a JSON object")
        task_id = payload.get("task_id")
        scores = payload.get("scores")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError(f"line {line_number} has no task-family identifier")
        if not isinstance(scores, dict):
            raise ValueError(f"line {line_number} has no score object")
        numeric_scores: dict[str, float] = {}
        for metric in SCORE_KEYS:
            value = scores.get(metric)
            if (
                not isinstance(value, int | float)
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                raise ValueError(f"line {line_number} has invalid score {metric!r}")
            numeric_scores[metric] = float(value)
        rows.append({"task_id": task_id, "scores": numeric_scores})
    if not rows:
        raise ValueError("metric-dependence input contains no scored samples")
    return rows


def _bootstrap_correlations(
    rows: list[dict[str, Any]],
    left_metric: str,
    right_metric: str,
    *,
    seed: int,
    draws: int,
) -> tuple[tuple[float | None, float | None], tuple[float | None, float | None]]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[str(row["task_id"])].append(row)
    cluster_ids = sorted(clusters)
    if len(cluster_ids) < 2:
        return ((None, None), (None, None))
    rng = random.Random(seed)
    pearson_draws: list[float] = []
    spearman_draws: list[float] = []
    for _ in range(draws):
        selected = [rng.choice(cluster_ids) for _ in cluster_ids]
        sampled = [row for cluster_id in selected for row in clusters[cluster_id]]
        left = [float(row["scores"][left_metric]) for row in sampled]
        right = [float(row["scores"][right_metric]) for row in sampled]
        pearson = _pearson(left, right)
        spearman = _spearman(left, right)
        if pearson is not None:
            pearson_draws.append(pearson)
        if spearman is not None:
            spearman_draws.append(spearman)
    return (
        (_quantile(pearson_draws, 0.025), _quantile(pearson_draws, 0.975)),
        (_quantile(spearman_draws, 0.025), _quantile(spearman_draws, 0.975)),
    )


def metric_dependence_report(
    rows: list[dict[str, Any]],
    *,
    seed: int = 20260717,
    draws: int = 2_000,
    high_correlation_threshold: float = 0.9,
) -> dict[str, Any]:
    """Calculate pairwise correlations with whole-family bootstrap uncertainty."""

    if draws < 100:
        raise ValueError("at least 100 bootstrap draws are required")
    if not 0 < high_correlation_threshold <= 1:
        raise ValueError("high_correlation_threshold must be in (0, 1]")
    pairs: list[dict[str, Any]] = []
    for left_index, left_metric in enumerate(SCORE_KEYS):
        for right_index, right_metric in enumerate(SCORE_KEYS[left_index + 1 :], start=1):
            left = [float(row["scores"][left_metric]) for row in rows]
            right = [float(row["scores"][right_metric]) for row in rows]
            pearson = _pearson(left, right)
            spearman = _spearman(left, right)
            pearson_ci, spearman_ci = _bootstrap_correlations(
                rows,
                left_metric,
                right_metric,
                seed=seed + left_index * 101 + right_index,
                draws=draws,
            )
            high = any(
                value is not None and abs(value) >= high_correlation_threshold
                for value in (pearson, spearman)
            )
            pairs.append(
                {
                    "left": left_metric,
                    "right": right_metric,
                    "n": len(rows),
                    "task_families": len({str(row["task_id"]) for row in rows}),
                    "pearson": _round_optional(pearson),
                    "pearson_ci95_low": _round_optional(pearson_ci[0]),
                    "pearson_ci95_high": _round_optional(pearson_ci[1]),
                    "spearman": _round_optional(spearman),
                    "spearman_ci95_low": _round_optional(spearman_ci[0]),
                    "spearman_ci95_high": _round_optional(spearman_ci[1]),
                    "identical_value_rate": round(
                        sum(
                            left_value == right_value
                            for left_value, right_value in zip(left, right, strict=True)
                        )
                        / len(rows),
                        6,
                    ),
                    "high_correlation_review": high,
                }
            )
    report: dict[str, Any] = {
        "schema_version": METRIC_DEPENDENCE_SCHEMA_VERSION,
        "sample_count": len(rows),
        "independent_task_families": len({str(row["task_id"]) for row in rows}),
        "bootstrap": {
            "method": "whole-task-family cluster bootstrap",
            "draws": draws,
            "seed": seed,
        },
        "high_correlation_threshold": high_correlation_threshold,
        "structural_relationships": [
            {
                "metrics": [
                    "composite",
                    "task_effectiveness",
                    "decision_quality",
                    "safety",
                    "recovery",
                    "explainability",
                    "calibration",
                    "efficiency",
                ],
                "relationship": (
                    "historical composite is a gated weighted function of the listed "
                    "component scores"
                ),
                "consequence": (
                    "composite correlations are descriptive dependence, not evidence of "
                    "duplicate constructs"
                ),
            },
            {
                "metrics": ["task_effectiveness", "decision_quality"],
                "relationship": (
                    "historical decision quality defaults to effectiveness when no independent "
                    "oracle applies"
                ),
                "consequence": (
                    "identity rates must be reported by task applicability before interpreting "
                    "correlation"
                ),
            },
            {
                "metrics": ["robustness", "recovery"],
                "relationship": (
                    "historical robustness equals recovery for perturbed samples and is fixed at "
                    "one for clean samples"
                ),
                "consequence": (
                    "the two outputs are not independent measurements in the historical contract"
                ),
            },
            {
                "metrics": ["efficiency", "task_effectiveness"],
                "relationship": "historical efficiency is multiplicatively scaled by effectiveness",
                "consequence": "observed dependence is partly structural",
            },
        ],
        "pairs": pairs,
        "high_correlation_pairs": [
            {"left": item["left"], "right": item["right"]}
            for item in pairs
            if item["high_correlation_review"]
        ],
        "interpretation": (
            "High correlation triggers construct review; it does not by itself justify merging, "
            "dropping, or renaming a metric. Structural overlap is interpreted before empirical "
            "correlation."
        ),
    }
    report["report_sha256"] = digest_payload(report)
    return report


def write_metric_dependence_report(
    samples_path: Path,
    output_path: Path,
    *,
    seed: int = 20260717,
    draws: int = 2_000,
    high_correlation_threshold: float = 0.9,
) -> dict[str, Any]:
    """Audit a sanitized sample JSONL file and write a content-addressed report."""

    rows = _load_rows(samples_path)
    report = metric_dependence_report(
        rows,
        seed=seed,
        draws=draws,
        high_correlation_threshold=high_correlation_threshold,
    )
    report["source_samples"] = {
        "path": samples_path.name,
        "sha256": sha256_file(samples_path),
    }
    report.pop("report_sha256")
    report["report_sha256"] = digest_payload(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def verify_metric_dependence_report(
    report_path: Path,
    samples_path: Path | None = None,
) -> dict[str, Any]:
    """Verify report self-integrity and, optionally, its sanitized source samples."""

    try:
        payload = _strict_json(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "verified": False,
            "issues": [f"metric-dependence report is unreadable: {error}"],
        }
    if not isinstance(payload, dict):
        return {
            "verified": False,
            "issues": ["metric-dependence report is not a JSON object"],
        }
    issues: list[str] = []
    expected = payload.pop("report_sha256", None)
    actual = digest_payload(payload)
    payload["report_sha256"] = expected
    if expected != actual:
        issues.append("metric-dependence report digest mismatch")
    if payload.get("schema_version") != METRIC_DEPENDENCE_SCHEMA_VERSION:
        issues.append("unsupported metric-dependence report schema")
    if samples_path is not None:
        source = payload.get("source_samples")
        if not isinstance(source, dict) or source.get("sha256") != sha256_file(samples_path):
            issues.append("metric-dependence source-sample digest mismatch")
    return {"verified": not issues, "issues": issues}
