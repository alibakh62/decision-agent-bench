"""Explicit-cost-gated execution for planned Inspect experiment cells."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from decision_agent_bench.experiments.manifest import load_manifest

REDACTIONS = (
    re.compile(r"(?i)(api[_-]?key|authorization|password|secret)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._-]+"),
)


def _redact(value: str, limit: int = 8_000) -> str:
    sanitized = value[-limit:]
    for pattern in REDACTIONS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def _eval_statuses(stdout: str) -> list[str]:
    """Extract terminal Inspect log statuses from JSON-lines launch output."""

    statuses: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event") == "done":
            statuses.extend(
                str(log.get("status", "unknown"))
                for log in event.get("logs", [])
                if isinstance(log, dict)
            )
    return statuses


def execute_manifest(
    manifest_path: Path,
    *,
    execute: bool = False,
    acknowledge_costs: bool = False,
) -> dict[str, Any]:
    """Print or execute every cell, requiring two explicit flags for paid work."""

    manifest = load_manifest(manifest_path)
    if execute and not acknowledge_costs:
        raise ValueError("--execute also requires --acknowledge-costs")
    if not execute:
        return {
            "run_id": manifest["run_id"],
            "mode": "dry-run",
            "commands": [cell["command"] for cell in manifest["cells"]],
        }

    repository = Path(__file__).resolve().parents[3]
    execution_path = manifest_path.parent / "execution.json"
    runtime_home = manifest_path.parent / ".runtime-home"
    runtime_home.mkdir(parents=True, exist_ok=True)
    execution_environment = os.environ.copy()
    execution_environment["HOME"] = str(runtime_home)
    execution_environment["XDG_CACHE_HOME"] = str(runtime_home / ".cache")
    execution_environment["TIKTOKEN_CACHE_DIR"] = str(runtime_home / ".cache" / "tiktoken")
    execution: dict[str, Any] = {
        "run_id": manifest["run_id"],
        "started_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "status": "running",
        "cells": [],
    }
    for cell in manifest["cells"]:
        result = subprocess.run(
            list(cell["command"]),
            cwd=repository,
            env=execution_environment,
            check=False,
            capture_output=True,
            text=True,
        )
        eval_statuses = _eval_statuses(result.stdout)
        succeeded = (
            result.returncode == 0
            and bool(eval_statuses)
            and all(status == "success" for status in eval_statuses)
        )
        cell_result = {
            "cell_id": cell["cell_id"],
            "exit_code": result.returncode,
            "eval_statuses": eval_statuses,
            "status": "success" if succeeded else "error",
            "stdout_tail": _redact(result.stdout),
            "stderr_tail": _redact(result.stderr),
            "completed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        }
        execution["cells"].append(cell_result)
        execution_path.write_text(
            json.dumps(execution, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if not succeeded:
            execution["status"] = "error"
            break
    else:
        execution["status"] = "success"
    execution["completed_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    execution_path.write_text(
        json.dumps(execution, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return execution
