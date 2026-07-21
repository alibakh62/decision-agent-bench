"""Blinded annotation export and inter-rater agreement analysis."""

from __future__ import annotations

import csv
import hashlib
import json
import secrets
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalLog, read_eval_log

DIMENSIONS = ("task_effectiveness", "decision_quality", "safety", "recovery")
RATER_TYPES = ("human", "llm")
RATING_FIELDS = ("blind_id", "rater_id", "rater_type", *DIMENSIONS, "failure_codes", "notes")


def _json_dump_line(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _message_text(message: Any) -> str:
    text = getattr(message, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else json.dumps(content, default=str)


def _prompt_text(sample: Any) -> str:
    for message in sample.messages or []:
        if getattr(message, "role", None) == "user":
            return _message_text(message)
    sample_input = sample.input
    return sample_input if isinstance(sample_input, str) else json.dumps(sample_input, default=str)


def _final_answer(sample: Any) -> str:
    for message in reversed(sample.messages or []):
        if getattr(message, "role", None) == "assistant":
            return _message_text(message)
    output = sample.output
    return str(getattr(output, "completion", ""))


def _tool_evidence(sample: Any) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for message in sample.messages or []:
        if getattr(message, "role", None) != "tool":
            continue
        error = getattr(message, "error", None)
        evidence.append(
            {
                "function": getattr(message, "function", None),
                "content": _message_text(message),
                "error": None if error is None else str(error),
            }
        )
    return evidence


def _scores(sample: Any) -> dict[str, float]:
    score = (sample.scores or {}).get("decision_agent_scorer")
    if score is None or not isinstance(score.value, dict):
        return {}
    return {
        dimension: float(score.value.get(dimension, 0.0))
        for dimension in DIMENSIONS
    }


def annotation_entries(log: EvalLog) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Convert a successful Inspect log into blinded packet/private-key entry pairs."""

    if log.status != "success":
        return []
    baseline = str((log.eval.task_args or {}).get("baseline", "custom"))
    entries = []
    for sample in log.samples or []:
        blind_id = f"DAB-A-{secrets.token_hex(8)}"
        metadata = sample.metadata or {}
        packet = {
            "blind_id": blind_id,
            "prompt": _prompt_text(sample),
            "tool_evidence": _tool_evidence(sample),
            "final_answer": _final_answer(sample),
        }
        key = {
            "blind_id": blind_id,
            "run_id": str(log.eval.run_id),
            "model": str(log.eval.model),
            "baseline": baseline,
            "sample_id": str(sample.id),
            "task_id": str(metadata.get("task_id", sample.id)),
            "variant": str(metadata.get("variant", "unknown")),
            "epoch": int(sample.epoch or 1),
            "deterministic_scores": _scores(sample),
        }
        entries.append((packet, key))
    return entries


def _eval_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(candidate for candidate in path.rglob("*.eval") if candidate.is_file())


def export_annotation_bundle(logs: Path, output: Path) -> dict[str, Any]:
    """Export blinded packets, a private re-identification key, and a rating template."""

    paths = _eval_paths(logs)
    if not paths:
        raise ValueError(f"no .eval logs found under {logs}")
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    skipped_logs = 0
    for path in paths:
        log = read_eval_log(str(path))
        if log.status != "success":
            skipped_logs += 1
            continue
        pairs.extend(annotation_entries(log))
    if not pairs:
        raise ValueError("no completed samples with successful logs were found")

    output.mkdir(parents=True, exist_ok=True)
    packet_path = output / "annotation-packets.jsonl"
    key_path = output / "annotation-key.private.jsonl"
    ratings_path = output / "ratings-template.csv"
    manifest_path = output / "annotation-manifest.json"
    existing = [
        path
        for path in (packet_path, key_path, ratings_path, manifest_path)
        if path.exists()
    ]
    if existing:
        raise FileExistsError(
            "annotation export will not overwrite existing study files: "
            + ", ".join(path.name for path in existing)
        )
    with packet_path.open("w", encoding="utf-8") as handle:
        for packet, _ in pairs:
            handle.write(_json_dump_line(packet))
    with key_path.open("w", encoding="utf-8") as handle:
        for _, key in pairs:
            handle.write(_json_dump_line(key))
    key_path.chmod(0o600)
    with ratings_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RATING_FIELDS)
        writer.writeheader()
        for packet, _ in pairs:
            writer.writerow({"blind_id": packet["blind_id"], "rater_type": "human"})

    digest = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "1.0",
        "samples": len(pairs),
        "source_logs": len(paths),
        "skipped_logs": skipped_logs,
        "packet_sha256": digest,
        "blinding": ["model", "baseline", "task_id", "variant", "deterministic_scores"],
        "private_key": key_path.name,
        "ratings_template": ratings_path.name,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _parse_rating(value: str, *, field: str, line: int) -> int | None:
    value = value.strip()
    if not value:
        return None
    if value not in {"0", "1"}:
        raise ValueError(f"line {line}: {field} must be blank, 0, or 1")
    return int(value)


def load_ratings(path: Path, valid_ids: set[str]) -> list[dict[str, Any]]:
    """Load and strictly validate the wide CSV annotation format."""

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(RATING_FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"ratings CSV is missing fields: {sorted(missing)}")
        for line, raw in enumerate(reader, start=2):
            blind_id = raw["blind_id"].strip()
            rater_id = raw["rater_id"].strip()
            rater_type = raw["rater_type"].strip()
            if blind_id not in valid_ids:
                raise ValueError(f"line {line}: unknown blind_id {blind_id!r}")
            if not rater_id:
                continue
            if rater_type not in RATER_TYPES:
                raise ValueError(f"line {line}: rater_type must be human or llm")
            identity = (blind_id, rater_id)
            if identity in seen:
                raise ValueError(f"line {line}: duplicate rating for {blind_id}/{rater_id}")
            seen.add(identity)
            rows.append(
                {
                    "blind_id": blind_id,
                    "rater_id": rater_id,
                    "rater_type": rater_type,
                    **{
                        dimension: _parse_rating(raw[dimension], field=dimension, line=line)
                        for dimension in DIMENSIONS
                    },
                }
            )
    return rows


def _fleiss_kappa(groups: list[list[int]]) -> float | None:
    eligible = [group for group in groups if len(group) >= 2]
    if len(eligible) < 2:
        return None
    counts = {len(group) for group in eligible}
    if len(counts) != 1:
        raise ValueError("Fleiss kappa requires the same number of ratings for each included item")
    n = len(eligible[0])
    observed = statistics.fmean(
        sum(count * (count - 1) for count in Counter(group).values()) / (n * (n - 1))
        for group in eligible
    )
    positive_rate = sum(sum(group) for group in eligible) / (len(eligible) * n)
    expected = positive_rate**2 + (1 - positive_rate) ** 2
    if expected == 1:
        return 1.0 if observed == 1 else 0.0
    return round((observed - expected) / (1 - expected), 6)


def _majority(values: Iterable[int | None]) -> int | None:
    observed = [value for value in values if value is not None]
    if not observed:
        return None
    ones = sum(observed)
    if ones * 2 == len(observed):
        return None
    return int(ones * 2 > len(observed))


def _comparison(reference: Mapping[str, int], candidate: Mapping[str, int]) -> dict[str, Any]:
    shared = sorted(set(reference) & set(candidate))
    tp = sum(reference[key] == candidate[key] == 1 for key in shared)
    tn = sum(reference[key] == candidate[key] == 0 for key in shared)
    fp = sum(reference[key] == 0 and candidate[key] == 1 for key in shared)
    fn = sum(reference[key] == 1 and candidate[key] == 0 for key in shared)
    return {
        "n": len(shared),
        "agreement": round((tp + tn) / len(shared), 6) if shared else None,
        "confusion": {
            "true_positive": tp,
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
        },
    }


def agreement_report(
    ratings_path: Path,
    key_path: Path,
    output_path: Path | None = None,
    *,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Measure human agreement and compare human, LLM-judge, and deterministic labels."""

    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    keys = _read_jsonl(key_path)
    indexed_keys = {str(item["blind_id"]): item for item in keys}
    if len(indexed_keys) != len(keys):
        raise ValueError("private key contains duplicate blind_id values")
    ratings = load_ratings(ratings_path, set(indexed_keys))
    if not ratings:
        raise ValueError("ratings CSV contains no completed ratings")
    by_type: dict[str, dict[str, list[dict[str, Any]]]] = {
        kind: defaultdict(list) for kind in RATER_TYPES
    }
    for row in ratings:
        by_type[row["rater_type"]][row["blind_id"]].append(row)

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "threshold": threshold,
        "rated_samples": len({row["blind_id"] for row in ratings}),
        "rater_counts": dict(Counter(row["rater_type"] for row in ratings)),
        "dimensions": {},
    }
    for dimension in DIMENSIONS:
        human_groups = {
            blind_id: [row[dimension] for row in rows if row[dimension] is not None]
            for blind_id, rows in by_type["human"].items()
        }
        human_majority = {
            blind_id: majority
            for blind_id, values in human_groups.items()
            if (majority := _majority(values)) is not None
        }
        llm_majority = {
            blind_id: majority
            for blind_id, rows in by_type["llm"].items()
            if (majority := _majority(row[dimension] for row in rows)) is not None
        }
        deterministic = {
            blind_id: int(
                float(item.get("deterministic_scores", {}).get(dimension, 0.0)) >= threshold
            )
            for blind_id, item in indexed_keys.items()
            if dimension in item.get("deterministic_scores", {})
        }
        eligible_groups = [values for values in human_groups.values() if len(values) >= 2]
        report["dimensions"][dimension] = {
            "human": {
                "samples_with_two_or_more_ratings": len(eligible_groups),
                "majority_labels": len(human_majority),
                "fleiss_kappa": _fleiss_kappa(eligible_groups),
            },
            "deterministic_vs_human": _comparison(human_majority, deterministic),
            "llm_judge_vs_human": _comparison(human_majority, llm_majority),
            "llm_judge_vs_deterministic": _comparison(deterministic, llm_majority),
        }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return report
