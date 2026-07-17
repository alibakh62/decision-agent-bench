"""Reproduction check for the published reference world."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from decision_agent_bench.simulator.generator import GenerationConfig, generate_world


def default_reference_manifest_path() -> Path:
    """Return the reference manifest from a checkout or installed wheel."""

    source_manifest = Path(__file__).resolve().parents[3] / "data" / "reference-world-manifest.json"
    if source_manifest.exists():
        return source_manifest
    resource = files("decision_agent_bench").joinpath("data/reference-world-manifest.json")
    return Path(str(resource))


def verify_reference_world(manifest_path: Path | None = None) -> dict[str, Any]:
    """Regenerate the default world and require an exact manifest match."""

    expected_path = manifest_path or default_reference_manifest_path()
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    with TemporaryDirectory(prefix="decision-agent-bench-") as temporary_directory:
        database = generate_world(Path(temporary_directory) / "reference", GenerationConfig())
        actual = json.loads((database.parent / "manifest.json").read_text(encoding="utf-8"))
    if actual != expected:
        expected_digest = expected.get("logical_sha256", "missing")
        actual_digest = actual.get("logical_sha256", "missing")
        raise ValueError(
            "reference-world reproduction failed: "
            f"expected logical_sha256={expected_digest}, got {actual_digest}"
        )
    return actual
