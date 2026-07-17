"""Shared content-addressing primitives for public benchmark artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest_payload(payload: Any) -> str:
    """Hash a stable canonical JSON representation."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def file_evidence(path: Path, *, relative_to: Path) -> dict[str, Any]:
    """Describe one file by portable path, byte size, and SHA-256."""

    return {
        "path": path.relative_to(relative_to).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def verify_evidence_files(
    base_directory: Path,
    expected: list[dict[str, Any]],
    *,
    suffix: str | None = None,
) -> tuple[list[str], set[str]]:
    """Verify a path-safe exact list of content-addressed files."""

    issues: list[str] = []
    expected_paths: set[str] = set()
    for item in expected:
        if not isinstance(item, dict):
            issues.append("evidence entry is not an object")
            continue
        relative = Path(str(item.get("path", "")))
        relative_text = relative.as_posix()
        if not relative_text or relative.is_absolute() or ".." in relative.parts:
            issues.append(f"unsafe evidence path: {relative_text!r}")
            continue
        if suffix is not None and relative.suffix != suffix:
            issues.append(f"unexpected evidence suffix: {relative_text}")
            continue
        if relative_text in expected_paths:
            issues.append(f"duplicate evidence path: {relative_text}")
            continue
        expected_paths.add(relative_text)
        path = base_directory / relative
        if not path.is_file():
            issues.append(f"missing file: {relative_text}")
            continue
        if path.stat().st_size != item.get("bytes"):
            issues.append(f"size mismatch: {relative_text}")
        if sha256_file(path) != item.get("sha256"):
            issues.append(f"sha256 mismatch: {relative_text}")
    return issues, expected_paths
