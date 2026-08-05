"""Reproduction check for the published v0.7 closed-loop reference episode."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from decision_agent_bench.simulator.closed_loop import (
    ClosedLoopConfig,
    generate_closed_loop_world,
)


def default_closed_loop_manifest_path() -> Path:
    """Return the v0.7 manifest from a checkout or installed wheel."""

    source_manifest = (
        Path(__file__).resolve().parents[3] / "data" / "closed-loop-v0.7-manifest.json"
    )
    if source_manifest.exists():
        return source_manifest
    resource = files("decision_agent_bench").joinpath("data/closed-loop-v0.7-manifest.json")
    return Path(str(resource))


def verify_closed_loop_reference(manifest_path: Path | None = None) -> dict[str, Any]:
    """Regenerate the default v0.7 episode and require an exact manifest match."""

    expected_path = manifest_path or default_closed_loop_manifest_path()
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    with TemporaryDirectory(prefix="decision-agent-bench-v07-") as temporary_directory:
        database = generate_closed_loop_world(
            Path(temporary_directory) / "reference",
            ClosedLoopConfig(),
        )
        actual = json.loads((database.parent / "manifest.json").read_text(encoding="utf-8"))
    if actual != expected:
        expected_digest = expected.get("initial_logical_sha256", "missing")
        actual_digest = actual.get("initial_logical_sha256", "missing")
        raise ValueError(
            "closed-loop reference reproduction failed: "
            f"expected initial_logical_sha256={expected_digest}, got {actual_digest}"
        )
    return actual
