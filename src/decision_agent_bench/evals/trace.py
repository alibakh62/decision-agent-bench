"""Portable causal trace records for construct-valid evaluations."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

TRACE_CONTRACT_VERSION = "1.0.0"
ROOT_SPAN_ID = "SPAN-ROOT"

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b(?:api[_ -]?key|authorization|bearer)\s*[:=]\s*[^\s,;]+"),
)


@dataclass(frozen=True)
class TraceValidation:
    """Machine-checkable completeness result for one sample trace."""

    complete: bool
    issues: tuple[str, ...]
    trace_id: str | None
    span_count: int


def trace_id_for(task_id: str, scenario_seed: int, variant: str) -> str:
    """Return a deterministic, non-secret trace identifier for one sample."""

    material = f"{TRACE_CONTRACT_VERSION}|{task_id}|{scenario_seed}|{variant}"
    return "TRACE-" + hashlib.sha256(material.encode()).hexdigest()[:20].upper()


def root_trace_event(task_id: str, scenario_seed: int, variant: str) -> dict[str, Any]:
    """Create the root event shared by built-in and adapted agents."""

    trace_id = trace_id_for(task_id, scenario_seed, variant)
    return {
        "trace_contract_version": TRACE_CONTRACT_VERSION,
        "trace_id": trace_id,
        "span_id": ROOT_SPAN_ID,
        "parent_span_id": None,
        "event_type": "run.started",
        "actor": "benchmark",
        "role": "system",
        "sequence": 0,
        "privacy_class": "synthetic",
        "task_id": task_id,
        "scenario_seed": scenario_seed,
        "variant": variant,
        "usage": None,
        "latency_ms": None,
        "cost_usd": None,
        "state_mutations": [],
        "approval": None,
    }


def sanitize_trace_value(value: Any) -> Any:
    """Minimize obvious credentials before a value enters durable trace state."""

    if isinstance(value, dict):
        return {str(key): sanitize_trace_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [sanitize_trace_value(item) for item in value]
    if isinstance(value, str):
        sanitized = value
        for pattern in _SECRET_PATTERNS:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        return sanitized
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)


def tool_trace_event(
    *,
    root: dict[str, Any],
    index: int,
    tool_name: str,
    status: str,
    arguments: dict[str, Any],
    result: Any | None = None,
    error: str | None = None,
    evidence_id: str | None = None,
) -> dict[str, Any]:
    """Create one causally linked, privacy-minimized tool span."""

    safe_arguments = sanitize_trace_value(arguments)
    safe_result = sanitize_trace_value(result) if result is not None else None
    linked_evidence = sorted(
        {
            str(item)
            for item in _walk_values(safe_arguments)
            if isinstance(item, str) and re.fullmatch(r"E\d{3,}", item)
        }
    )
    payload: dict[str, Any] = {
        "trace_contract_version": TRACE_CONTRACT_VERSION,
        "trace_id": str(root["trace_id"]),
        "span_id": f"SPAN-{index:04d}",
        "parent_span_id": ROOT_SPAN_ID,
        "event_type": "tool.execution",
        "actor": "evaluated-agent",
        "role": "tool",
        "sequence": index,
        "privacy_class": "synthetic",
        "tool": tool_name,
        "status": status,
        "arguments": safe_arguments,
        "linked_evidence_ids": linked_evidence,
        "usage": None,
        "latency_ms": None,
        "cost_usd": None,
        "state_mutations": [],
        "approval": None,
    }
    if evidence_id is not None:
        payload["evidence_id"] = evidence_id
    if safe_result is not None:
        payload["result"] = safe_result
        payload["result_sha256"] = _payload_hash(safe_result)
    if error is not None:
        payload["error"] = str(sanitize_trace_value(error))
    return payload


def submission_trace_event(
    root: dict[str, Any], calls: list[dict[str, Any]], submission: dict[str, Any]
) -> dict[str, Any]:
    """Create the public terminal decision event without private chain-of-thought."""

    evidence_ids = sorted(
        {
            str(evidence_id)
            for claim in submission.get("claims", [])
            if isinstance(claim, dict)
            for evidence_id in claim.get("evidence_ids", [])
            if isinstance(evidence_id, str)
        }
    )
    sequence = len(calls) + 1
    return {
        "trace_contract_version": TRACE_CONTRACT_VERSION,
        "trace_id": str(root["trace_id"]),
        "span_id": f"SPAN-{sequence:04d}",
        "parent_span_id": ROOT_SPAN_ID,
        "event_type": "decision.submitted",
        "actor": "evaluated-agent",
        "role": "model",
        "sequence": sequence,
        "privacy_class": "synthetic",
        "linked_evidence_ids": evidence_ids,
        "public_output": sanitize_trace_value(
            {
                "summary": submission.get("summary"),
                "confidence": submission.get("confidence"),
                "claims": submission.get("claims"),
                "actions": submission.get("actions"),
                "data_quality_issues": submission.get("data_quality_issues"),
            }
        ),
        "usage": None,
        "latency_ms": None,
        "cost_usd": None,
        "state_mutations": [],
        "approval": None,
    }


def validate_trace(
    root: Any,
    calls: list[dict[str, Any]],
    submission: dict[str, Any] | None = None,
) -> TraceValidation:
    """Validate trace identity, causal lineage, payload integrity, and event order."""

    issues: list[str] = []
    if not isinstance(root, dict):
        return TraceValidation(False, ("missing_root_event",), None, len(calls))
    trace_id = root.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id.startswith("TRACE-"):
        issues.append("invalid_trace_id")
        trace_id = None
    if root.get("trace_contract_version") != TRACE_CONTRACT_VERSION:
        issues.append("trace_contract_version")
    if root.get("span_id") != ROOT_SPAN_ID or root.get("parent_span_id") is not None:
        issues.append("invalid_root_span")

    seen_spans: set[str] = set()
    seen_evidence: set[str] = set()
    for expected_index, call in enumerate(calls, start=1):
        prefix = f"call_{expected_index}"
        if call.get("trace_contract_version") != TRACE_CONTRACT_VERSION:
            issues.append(f"{prefix}_contract")
        if trace_id is not None and call.get("trace_id") != trace_id:
            issues.append(f"{prefix}_trace_id")
        span_id = call.get("span_id")
        if not isinstance(span_id, str) or span_id in seen_spans:
            issues.append(f"{prefix}_span_id")
        else:
            seen_spans.add(span_id)
        if call.get("parent_span_id") != ROOT_SPAN_ID:
            issues.append(f"{prefix}_parent")
        if call.get("sequence") != expected_index:
            issues.append(f"{prefix}_sequence")
        if call.get("event_type") != "tool.execution":
            issues.append(f"{prefix}_event_type")
        if call.get("status") not in {"success", "error"}:
            issues.append(f"{prefix}_status")
        if not isinstance(call.get("arguments"), dict):
            issues.append(f"{prefix}_arguments")
        if call.get("status") == "success":
            evidence_id = call.get("evidence_id")
            if not isinstance(evidence_id, str) or evidence_id in seen_evidence:
                issues.append(f"{prefix}_evidence_id")
            else:
                seen_evidence.add(evidence_id)
            if "result" not in call:
                issues.append(f"{prefix}_result")
            elif call.get("result_sha256") != _payload_hash(call["result"]):
                issues.append(f"{prefix}_result_hash")
        elif not isinstance(call.get("error"), str) or not call.get("error"):
            issues.append(f"{prefix}_error")
        linked = call.get("linked_evidence_ids", [])
        if not isinstance(linked, list) or not all(item in seen_evidence for item in linked):
            issues.append(f"{prefix}_evidence_lineage")

    span_count = len(calls)
    if submission is not None:
        if "trace_id" not in root:
            issues.append("submission_trace_id")
        else:
            terminal = submission_trace_event(root, calls, submission)
            span_count += 1
            if terminal["trace_id"] != trace_id:
                issues.append("submission_trace_id")
            if terminal["sequence"] != len(calls) + 1:
                issues.append("submission_sequence")
            if not isinstance(terminal["public_output"], dict):
                issues.append("submission_output")

    return TraceValidation(not issues, tuple(issues), trace_id, span_count)


def _walk_values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        flattened: list[Any] = []
        for item in value.values():
            flattened.extend(_walk_values(item))
        return flattened
    if isinstance(value, list):
        flattened = []
        for item in value:
            flattened.extend(_walk_values(item))
        return flattened
    return [value]


def _payload_hash(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()
