"""Live Inspect runtime and log-to-Lab adapters for the interactive workbench."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from inspect_ai import eval as inspect_eval
from inspect_ai.solver import SolverSpec

from decision_agent_bench.evals.task import decision_agent_bench_v0_2
from decision_agent_bench.lab import REPLAY_AGENTS_BY_KEY, SCORE_WEIGHTS

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_SYMBOL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SYSTEM_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
_TRUSTED_SOLVER_DIRECTORIES = ("agents", "examples")
_SUBMISSION_FIELDS = {
    "conclusion",
    "confidence",
    "evidence_ids",
    "selected_ids",
    "numeric_values",
    "escalate",
    "data_quality_issues",
}


def safe_model_name(model_name: str) -> str:
    """Validate an Inspect model identifier without interpreting it as a path or command."""

    value = str(model_name).strip()
    if not _MODEL_PATTERN.fullmatch(value):
        raise ValueError(
            "model must be an Inspect identifier such as mockllm/model or openai/gpt-5.6-luna"
        )
    return value


def safe_system_name(system_name: str) -> str:
    """Validate the stable system label recorded in the Inspect log."""

    value = str(system_name).strip()
    if not _SYSTEM_PATTERN.fullmatch(value):
        raise ValueError(
            "system name must be 1-96 characters using letters, numbers, dots, colons, _ or -"
        )
    return value


def _trusted_solver_files() -> dict[str, Path]:
    """Discover Python files only under the repository's explicit agent directories."""

    discovered: dict[str, Path] = {}
    for directory_name in _TRUSTED_SOLVER_DIRECTORIES:
        directory = _PROJECT_ROOT / directory_name
        if not directory.is_dir():
            continue
        trusted_root = directory.resolve()
        for candidate in directory.rglob("*.py"):
            resolved = candidate.resolve()
            if candidate.is_file() and resolved.is_relative_to(trusted_root):
                discovered[candidate.relative_to(_PROJECT_ROOT).as_posix()] = resolved
    return discovered


def trusted_solver_spec(reference: str) -> SolverSpec:
    """Resolve a trusted local ``path.py@solver`` reference without user-controlled paths."""

    value = str(reference).strip()
    if value.count("@") != 1:
        raise ValueError("custom solver must use path.py@registered_solver syntax")
    relative_name, symbol = value.rsplit("@", maxsplit=1)
    if not _SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError("custom solver function must be a valid Python identifier")
    candidates = _trusted_solver_files()
    candidate = candidates.get(relative_name)
    if candidate is None:
        directories = " or ".join(f"{name}/" for name in _TRUSTED_SOLVER_DIRECTORIES)
        raise ValueError(
            f"custom solver file must already exist under {directories}; got {relative_name!r}"
        )
    return SolverSpec(solver=f"{candidate}@{symbol}")


def _iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _elapsed(timestamp: Any, started_at: Any) -> str:
    timestamp_value = _iso_datetime(timestamp)
    start_value = _iso_datetime(started_at)
    seconds = (
        max(0.0, (timestamp_value - start_value).total_seconds())
        if timestamp_value and start_value
        else 0.0
    )
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{seconds:05.2f}"


def _as_json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _as_json(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_as_json(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return _as_json(value)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _evidence_id(result: Any) -> str | None:
    parsed = _parse_json(result)
    if isinstance(parsed, dict) and parsed.get("evidence_id"):
        return str(parsed["evidence_id"])
    return None


def _content_summary(content: Any) -> str:
    parts: list[str] = []
    values = content if isinstance(content, list) else [content]
    for item in values:
        if isinstance(item, str):
            parts.append(item)
            continue
        summary = getattr(item, "summary", None)
        text = getattr(item, "text", None)
        if summary:
            parts.append(str(summary))
        elif text:
            parts.append(str(text))
    compact = " ".join(" ".join(parts).split())
    return (
        compact[:420] if compact else "Model selected its next action from the available context."
    )


def _event(
    trace: list[dict[str, Any]],
    *,
    timestamp: str,
    actor: str,
    event: str,
    summary: str,
    evidence_id: str | None = None,
    outcome: str = "Success",
    arguments: dict[str, Any] | None = None,
    result: Any = None,
    supports: tuple[str, ...] = (),
    latency_ms: int | None = None,
) -> None:
    trace.append(
        {
            "step": len(trace) + 1,
            "timestamp": timestamp,
            "actor": actor,
            "event": event,
            "summary": summary,
            "evidence_id": evidence_id,
            "outcome": outcome,
            "arguments": arguments or {},
            "result": _as_json(result),
            "supports": list(supports),
            "latency_ms": latency_ms,
        }
    )


def _trace_from_sample(
    sample: Any, model_name: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trace: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    started_at = getattr(sample, "started_at", None)
    _event(
        trace,
        timestamp="00:00:00.00",
        actor="System",
        event="Run started",
        summary=f"Inspect initialized sample {sample.id} with {model_name}.",
        result={"sample_id": sample.id, "model": model_name},
    )
    for raw_event in getattr(sample, "events", []):
        event_type = type(raw_event).__name__
        timestamp = _elapsed(getattr(raw_event, "timestamp", None), started_at)
        if event_type == "ModelEvent":
            output = getattr(raw_event, "output", None)
            choices = getattr(output, "choices", []) if output is not None else []
            message = choices[0].message if choices else None
            content = getattr(message, "content", "") if message is not None else ""
            tool_intents = (
                (getattr(message, "tool_calls", None) or []) if message is not None else []
            )
            submission = _parse_json(getattr(output, "completion", ""))
            if isinstance(submission, dict) and _SUBMISSION_FIELDS <= submission.keys():
                evidence_ids = submission.get("evidence_ids", [])
                _event(
                    trace,
                    timestamp=timestamp,
                    actor="Model",
                    event="Final decision",
                    summary=str(submission.get("conclusion", "Submitted structured decision."))[
                        :420
                    ],
                    evidence_id=(
                        ",".join(str(value) for value in evidence_ids)
                        if isinstance(evidence_ids, list)
                        else None
                    ),
                    outcome="Submitted",
                    result=submission,
                    supports=(
                        "task_effectiveness",
                        "decision_quality",
                        "safety",
                        "calibration",
                        "explainability",
                    ),
                    latency_ms=round(float(getattr(output, "time", 0) or 0) * 1000),
                )
                continue
            summary = _content_summary(content)
            if tool_intents and summary.startswith("Model selected"):
                functions = ", ".join(str(call.function) for call in tool_intents)
                summary = f"Selected {functions} as the next evidence action."
            _event(
                trace,
                timestamp=timestamp,
                actor="Model",
                event="Thought",
                summary=summary,
                result={
                    "model": getattr(raw_event, "model", model_name),
                    "stop_reason": getattr(choices[0], "stop_reason", None) if choices else None,
                },
                latency_ms=round(float(getattr(output, "time", 0) or 0) * 1000),
            )
        elif event_type == "ToolEvent":
            function = str(getattr(raw_event, "function", "tool"))
            arguments = _as_json(getattr(raw_event, "arguments", {}))
            result = _parse_json(getattr(raw_event, "result", None))
            error = getattr(raw_event, "error", None)
            latency_ms = round(float(getattr(raw_event, "working_time", 0) or 0) * 1000)
            if function == "submit":
                answer = arguments.get("answer") if isinstance(arguments, dict) else None
                submission = _parse_json(answer)
                evidence_ids = (
                    submission.get("evidence_ids", []) if isinstance(submission, dict) else []
                )
                _event(
                    trace,
                    timestamp=timestamp,
                    actor="Model",
                    event="Final decision",
                    summary=(
                        str(submission.get("conclusion", "Submitted structured decision."))[:420]
                        if isinstance(submission, dict)
                        else "Submitted structured decision."
                    ),
                    evidence_id=",".join(str(value) for value in evidence_ids) or None,
                    outcome="Submitted",
                    arguments=arguments if isinstance(arguments, dict) else {},
                    result=submission,
                    supports=(
                        "task_effectiveness",
                        "decision_quality",
                        "safety",
                        "calibration",
                        "explainability",
                    ),
                    latency_ms=latency_ms,
                )
                continue
            evidence_id = _evidence_id(result)
            _event(
                trace,
                timestamp=timestamp,
                actor="Tool",
                event=function,
                summary=f"Called {function} with the recorded Inspect arguments.",
                evidence_id=evidence_id,
                outcome="Warning" if error else "Success",
                arguments=arguments if isinstance(arguments, dict) else {},
                result={"error": str(error)} if error else result,
                latency_ms=latency_ms,
            )
            result_timestamp = _elapsed(getattr(raw_event, "completed", None), started_at)
            error_message = getattr(error, "message", str(error)) if error else None
            outcome = "Warning" if error else "Success"
            result_event = f"{function}.error" if error else f"{function}.results"
            summary = (
                str(error_message)[:420]
                if error
                else f"{function} returned auditable benchmark output"
                + (f" as {evidence_id}." if evidence_id else ".")
            )
            _event(
                trace,
                timestamp=result_timestamp,
                actor="Tool",
                event=result_event,
                summary=summary,
                evidence_id=evidence_id,
                outcome=outcome,
                arguments=arguments if isinstance(arguments, dict) else {},
                result={"error": error_message} if error else result,
                supports=("explainability", "efficiency") if not error else ("recovery",),
                latency_ms=latency_ms,
            )
            tool_calls.append(
                {
                    "index": len(tool_calls) + 1,
                    "tool": function,
                    "status": "error" if error else "success",
                    "arguments": arguments,
                    "evidence_id": evidence_id,
                    "error": error_message,
                    "latency_ms": latency_ms,
                }
            )
        elif event_type == "ScoreEvent":
            score = getattr(raw_event, "score", None)
            values = _as_json(getattr(score, "value", {})) if score is not None else {}
            if not isinstance(values, dict):
                continue
            _event(
                trace,
                timestamp=timestamp,
                actor="Evaluator",
                event="DecisionAgentBench score",
                summary=(
                    "The deterministic scorer reported composite "
                    f"{float(values.get('composite', 0)):.4f}."
                ),
                outcome="Scored",
                result=values,
                supports=tuple(SCORE_WEIGHTS),
            )
    return trace, tool_calls


def _agent_payload(
    *,
    agent_source: str,
    baseline: str,
    solver_reference: str,
    system_name: str,
) -> dict[str, str]:
    if agent_source == "Built-in baseline":
        agent = REPLAY_AGENTS_BY_KEY[baseline]
        return {
            "key": agent.key,
            "label": agent.label,
            "architecture": agent.architecture,
            "description": agent.description,
            "source": "built-in",
        }
    return {
        "key": system_name,
        "label": system_name,
        "architecture": "Custom Inspect solver",
        "description": solver_reference,
        "source": "custom",
    }


def payload_from_eval_log(
    log: Any,
    *,
    agent_source: str,
    baseline: str,
    solver_reference: str,
    system_name: str,
    instance: dict[str, Any],
    variant: str,
) -> dict[str, Any]:
    """Convert one completed Inspect log into the Lab's transparent presentation schema."""

    samples = getattr(log, "samples", None) or []
    if not samples:
        raise RuntimeError("Inspect returned no sample log")
    sample = samples[0]
    model_name = str(getattr(log.eval, "model", "unknown/model"))
    trace, tool_calls = _trace_from_sample(sample, model_name)
    scores = getattr(sample, "scores", None) or {}
    score = scores.get("decision_agent_scorer")
    raw_values = _as_json(getattr(score, "value", {})) if score is not None else {}
    failures = (
        list((getattr(score, "metadata", None) or {}).get("failure_taxonomy", []))
        if score is not None
        else []
    )
    score_breakdown = (
        (getattr(score, "metadata", None) or {}).get("score_breakdown", {})
        if score is not None
        else {}
    )
    answer = getattr(score, "answer", None) if score is not None else None
    completion = getattr(getattr(sample, "output", None), "completion", "")
    submission = _parse_json(answer or completion)
    if not isinstance(submission, dict):
        submission = {}
    grade_available = bool(raw_values) and bool(submission)
    values = raw_values
    if not grade_available:
        values = {
            **{key: 0.0 for key in SCORE_WEIGHTS},
            "robustness": 0.0,
            "composite": 0.0,
        }
    raw_weighted = round(
        sum(float(weight) * float(values.get(key, 0)) for key, weight in SCORE_WEIGHTS.items()),
        6,
    )
    status = str(getattr(log, "status", "error"))
    error = getattr(sample, "error", None) or getattr(log, "error", None)
    availability_reason: str | None = None
    if status == "success" and not error and not submission:
        status = "incomplete"
        limit = getattr(sample, "limit", None)
        limit_type = getattr(limit, "type", None)
        availability_reason = (
            f"The agent reached its {limit_type} limit before submitting the required JSON."
            if limit_type
            else "The agent ended without submitting the required JSON."
        )
        trace = [event for event in trace if event.get("event") != "DecisionAgentBench score"]
        _event(
            trace,
            timestamp=_elapsed(getattr(sample, "completed_at", None), sample.started_at),
            actor="Evaluator",
            event="Submission incomplete",
            summary=(
                "No final structured decision was received. DecisionAgentBench did not report "
                "dimension scores for this incomplete run."
            ),
            outcome="Not scored",
            result={
                "reason": availability_reason,
                "scorer_failures": failures,
            },
        )
    sample_id = str(getattr(sample, "id", instance[f"{variant}_sample_id"]))
    run_identity = f"{getattr(log.eval, 'run_id', '')}:{sample_id}:{model_name}"
    run_id = "RUN-" + hashlib.sha256(run_identity.encode()).hexdigest()[:8].upper()
    return {
        "run_id": run_id,
        "status": status,
        "error": _as_json(error) if error else None,
        "agent": _agent_payload(
            agent_source=agent_source,
            baseline=baseline,
            solver_reference=solver_reference,
            system_name=system_name,
        ),
        "model": model_name,
        "instance_id": str(instance["instance_id"]),
        "family_id": str(instance["family_id"]),
        "sample_id": sample_id,
        "variant": variant,
        "scenario_seed": int(instance["scenario_seed"]),
        "perturbation": str(instance["perturbation"]) if variant == "perturbed" else None,
        "task_version": str(getattr(log.eval, "task_version", instance["benchmark_version"])),
        "started_at": str(getattr(sample, "started_at", "")),
        "completed_at": str(getattr(sample, "completed_at", "")),
        "duration_seconds": float(getattr(sample, "total_time", 0) or 0),
        "prompt": str(instance["prompt"]),
        "trace": trace,
        "submission": submission,
        "tool_calls": tool_calls,
        "recoveries": [],
        "grade": {
            "available": grade_available,
            "availability_reason": availability_reason,
            "values": values,
            "raw_scorer_values": raw_values if not grade_available else None,
            "failures": failures,
            "explanation": str(getattr(score, "explanation", "")) if score is not None else "",
            "breakdown": _as_json(score_breakdown),
            "decision_outcome": (
                (getattr(score, "metadata", None) or {}).get("decision_outcome")
                if score is not None
                else None
            ),
        },
        "evidence_eligible": bool(submission) and "F-EVID" not in failures and grade_available,
        "format_eligible": "F-FORMAT" not in failures and grade_available,
        "raw_weighted_score": raw_weighted,
        "runtime_notice": (
            "Live Inspect evaluation. The selected model and solver produced this trace."
        ),
        "log_path": str(getattr(log, "location", "")),
        "model_usage": _as_json(getattr(sample, "model_usage", {})),
    }


def run_live_evaluation(
    *,
    agent_source: str,
    baseline: str,
    solver_reference: str,
    system_name: str,
    model_name: str,
    instance: dict[str, Any],
    variant: str,
) -> dict[str, Any]:
    """Execute one real Inspect sample and return its trace and deterministic score payload."""

    model = safe_model_name(model_name)
    if agent_source not in {"Built-in baseline", "Custom Inspect solver"}:
        raise ValueError("unknown agent source")
    if baseline not in REPLAY_AGENTS_BY_KEY:
        raise ValueError("unknown built-in baseline")
    system = safe_system_name(system_name)
    solver = (
        trusted_solver_spec(solver_reference) if agent_source == "Custom Inspect solver" else None
    )
    instance_id = str(instance["instance_id"])
    if re.search(r"-i[1-4]$", instance_id) is None:
        raise ValueError("selected instance does not have a supported seed index")
    sample_id = str(instance[f"{variant}_sample_id"])
    task = decision_agent_bench_v0_2(
        category=str(instance["category"]),
        variant=variant,
        baseline=baseline,
        instances_per_family=4,
        system_name=system,
    )
    log_directory = _PROJECT_ROOT / "logs" / "lab" / uuid.uuid4().hex
    log_directory.mkdir(parents=True, exist_ok=False)
    logs = inspect_eval(
        task,
        model=model,
        solver=solver,
        sample_id=sample_id,
        log_dir=str(log_directory),
        log_realtime=True,
        display="none",
    )
    if len(logs) != 1:
        raise RuntimeError(f"Inspect returned {len(logs)} logs; expected exactly one")
    return payload_from_eval_log(
        logs[0],
        agent_source=agent_source,
        baseline=baseline,
        solver_reference=solver_reference,
        system_name=system,
        instance=instance,
        variant=variant,
    )
