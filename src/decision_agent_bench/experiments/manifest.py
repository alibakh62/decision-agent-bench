"""Immutable experiment manifests and portable Inspect command plans."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from decision_agent_bench import __version__
from decision_agent_bench.experiments.schema import ExperimentConfig
from decision_agent_bench.simulator.reference import default_reference_manifest_path

TASK_FILE = "src/decision_agent_bench/evals/task.py"


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def _git_commit(repository: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _cell_command(
    *,
    config: ExperimentConfig,
    run_id: str,
    model: dict[str, Any],
    baseline: str,
    variant: str,
    category: str | None,
    log_dir: str,
) -> list[str]:
    budget = config.budget
    command = [
        "inspect",
        "eval",
        f"{TASK_FILE}@{config.task_name}",
        "--model",
        str(model["model"]),
        "--epochs",
        str(config.repetitions),
        "--no-epochs-reducer",
        "--token-limit",
        str(budget.token_limit),
        "--max-tokens",
        str(budget.max_output_tokens),
        "--time-limit",
        str(budget.time_limit_seconds),
        "--max-connections",
        str(budget.max_connections),
        "--max-samples",
        str(budget.max_samples),
        "--temperature",
        str(budget.temperature),
        "--seed",
        str(budget.seed),
        "--display",
        "none",
        "--json",
        "--no-log-model-api",
        "--no-log-realtime",
        "--log-dir",
        log_dir,
        "--metadata",
        f"dab_run_id={run_id}",
        "--metadata",
        f"model_family={model['family']}",
        "-T",
        f"variant={variant}",
        "-T",
        f"baseline={baseline}",
    ]
    if category:
        command.extend(["-T", f"category={category}"])
    if config.sample_limit is not None:
        command.extend(["--limit", str(config.sample_limit)])
    if budget.cost_limit_usd is not None:
        command.extend(["--cost-limit", str(budget.cost_limit_usd)])
    for key, value in sorted(model["model_args"].items()):
        command.extend(["-M", f"{key}={value}"])
    return command


def plan_experiment(config: ExperimentConfig, output_directory: Path) -> Path:
    """Write an immutable run manifest and return its path."""

    repository = Path(__file__).resolve().parents[3]
    now = datetime.now(UTC)
    created_at = now.isoformat()
    config_payload = config.to_dict()
    plan_sha256 = _digest(config_payload)
    run_nonce = _digest({"plan_sha256": plan_sha256, "created_at": created_at})[:12]
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{run_nonce}"
    run_directory = output_directory / run_id
    reference = json.loads(default_reference_manifest_path().read_text(encoding="utf-8"))
    enabled_models = [model for model in config_payload["models"] if model["enabled"]]
    categories = list(config.categories) or [None]
    cells: list[dict[str, Any]] = []
    for model in enabled_models:
        for baseline in config.baselines:
            for variant in config.variants:
                for category in categories:
                    identity = "-".join(
                        part
                        for part in (
                            _slug(str(model["family"])),
                            _slug(str(model["display_name"])),
                            baseline,
                            variant,
                            _slug(category) if category else None,
                        )
                        if part
                    )
                    log_dir = str(run_directory / "logs" / identity)
                    cell = {
                        "cell_id": identity,
                        "model": model["model"],
                        "model_family": model["family"],
                        "display_name": model["display_name"],
                        "publishable": model["publishable"],
                        "baseline": baseline,
                        "variant": variant,
                        "category": category,
                        "log_dir": log_dir,
                    }
                    cell["command"] = _cell_command(
                        config=config,
                        run_id=run_id,
                        model=model,
                        baseline=baseline,
                        variant=variant,
                        category=category,
                        log_dir=log_dir,
                    )
                    cells.append(cell)
    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "created_at": created_at,
        "status": "planned",
        "plan_sha256": plan_sha256,
        "config": config_payload,
        "source": {
            "git_commit": _git_commit(repository),
            "task_entrypoint": f"{TASK_FILE}@{config.task_name}",
            "reference_world_sha256": reference["logical_sha256"],
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "inspect_ai": importlib.metadata.version("inspect-ai"),
            "decision_agent_bench": __version__,
        },
        "cells": cells,
    }
    manifest["manifest_sha256"] = _digest(manifest)
    run_directory.mkdir(parents=True, exist_ok=False)
    manifest_path = run_directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path


def load_manifest(path: Path) -> dict[str, Any]:
    """Load an experiment manifest and verify its immutable content hash."""

    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("experiment manifest must be a JSON object")
    expected = manifest.pop("manifest_sha256", None)
    actual = _digest(manifest)
    manifest["manifest_sha256"] = expected
    if not expected or actual != expected:
        raise ValueError("experiment manifest hash mismatch")
    return manifest
