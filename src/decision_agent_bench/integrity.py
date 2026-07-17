"""Shared content-addressing primitives for public benchmark artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

LOCK_REQUIREMENT_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s;\\]+)"
    r"(?:\s*;\s*(?P<marker>.*?))?\s*\\?$"
)


def normalize_distribution_name(name: str) -> str:
    """Return the PEP 503-normalized form used to compare inventories."""

    return re.sub(r"[-_.]+", "-", name).lower()


def locked_requirements(path: Path) -> list[dict[str, str | None]]:
    """Parse pinned name/version/marker entries from a generated requirements lock."""

    requirements: list[dict[str, str | None]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line or raw_line[0].isspace() or raw_line.startswith("#"):
            continue
        match = LOCK_REQUIREMENT_PATTERN.fullmatch(raw_line)
        if match is None:
            raise ValueError(f"unsupported requirement at {path}:{line_number}")
        marker = match.group("marker")
        requirements.append(
            {
                "name": normalize_distribution_name(match.group("name")),
                "version": match.group("version"),
                "marker": marker.strip() if marker else None,
            }
        )
    if not requirements:
        raise ValueError(f"requirements lock has no pinned dependencies: {path}")
    return requirements


def _observed_inventory(
    records: Any,
) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    if not isinstance(records, list):
        raise ValueError("dependency inventory must be a list")
    pairs: list[tuple[str, str]] = []
    invalid: list[str] = []
    names: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            invalid.append(f"entry {index} is not an object")
            continue
        name = normalize_distribution_name(str(record.get("name", "")))
        version = str(record.get("version", ""))
        if not name or not version or name == "none" or version == "None":
            invalid.append(f"entry {index} has no package name or version")
            continue
        names.append(name)
        pairs.append((name, version))
    duplicates = sorted(name for name in set(names) if names.count(name) > 1)
    return pairs, invalid, duplicates


def verify_pip_audit_inventory(lock_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Verify that pip-audit covers one valid environment from a universal lock."""

    if not isinstance(payload, dict):
        raise ValueError("pip-audit report must be a JSON object")
    locked = locked_requirements(lock_path)
    by_name: dict[str, list[dict[str, str | None]]] = defaultdict(list)
    for requirement in locked:
        by_name[str(requirement["name"])].append(requirement)
    observed, invalid, duplicates = _observed_inventory(payload.get("dependencies"))
    observed_by_name = {name: version for name, version in observed}
    required_names = {
        name
        for name, requirements in by_name.items()
        if any(
            requirement["marker"] is None
            or "python_version" in str(requirement["marker"])
            or "python_full_version" in str(requirement["marker"])
            for requirement in requirements
        )
    }
    missing = sorted(required_names - observed_by_name.keys())
    unexpected = sorted(observed_by_name.keys() - by_name.keys())
    version_mismatches = sorted(
        {
            f"{name}=={version}"
            for name, version in observed
            if name in by_name
            and version
            not in {str(requirement["version"]) for requirement in by_name[name]}
        }
    )
    issues = [*invalid]
    if duplicates:
        issues.append("duplicate audited packages: " + ", ".join(duplicates))
    if missing:
        issues.append("missing audited packages: " + ", ".join(missing))
    if unexpected:
        issues.append("unexpected audited packages: " + ", ".join(unexpected))
    if version_mismatches:
        issues.append("audited versions not in lock: " + ", ".join(version_mismatches))
    return {
        "verified": not issues,
        "locked_requirement_entries": len(locked),
        "required_packages": len(required_names),
        "audited_packages": len(observed),
        "missing": missing,
        "unexpected": unexpected,
        "version_mismatches": version_mismatches,
        "duplicates": duplicates,
        "issues": issues,
    }


def verify_sbom_inventory(lock_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Verify that a universal CycloneDX SBOM exactly covers the lock entries."""

    if not isinstance(payload, dict):
        raise ValueError("CycloneDX SBOM must be a JSON object")
    locked = locked_requirements(lock_path)
    expected = {
        (str(requirement["name"]), str(requirement["version"]))
        for requirement in locked
    }
    observed, invalid, multi_version_names = _observed_inventory(payload.get("components"))
    observed_set = set(observed)
    duplicate_pairs = sorted({pair for pair in observed if observed.count(pair) > 1})
    missing_pairs = sorted(expected - observed_set)
    unexpected_pairs = sorted(observed_set - expected)
    issues = [*invalid]
    if duplicate_pairs:
        issues.append(
            "duplicate SBOM components: "
            + ", ".join(f"{name}=={version}" for name, version in duplicate_pairs)
        )
    if missing_pairs:
        issues.append(
            "missing SBOM components: "
            + ", ".join(f"{name}=={version}" for name, version in missing_pairs)
        )
    if unexpected_pairs:
        issues.append(
            "unexpected SBOM components: "
            + ", ".join(f"{name}=={version}" for name, version in unexpected_pairs)
        )
    return {
        "verified": not issues,
        "locked_requirement_entries": len(locked),
        "sbom_components": len(observed),
        "missing": [f"{name}=={version}" for name, version in missing_pairs],
        "unexpected": [f"{name}=={version}" for name, version in unexpected_pairs],
        "multi_version_names": multi_version_names,
        "duplicate_pairs": [f"{name}=={version}" for name, version in duplicate_pairs],
        "issues": issues,
    }


def accepted_vex_identifiers(
    payload: dict[str, Any], *, on_date: date | None = None
) -> set[str]:
    """Return vulnerability IDs covered by a current fixed/not-affected statement."""

    if not isinstance(payload, dict):
        raise ValueError("OpenVEX document must be a JSON object")
    statements = payload.get("statements", [])
    if not isinstance(statements, list):
        raise ValueError("OpenVEX statements must be a list")
    today = on_date or datetime.now(UTC).date()
    identifiers: set[str] = set()
    for index, statement in enumerate(statements):
        if not isinstance(statement, dict):
            raise ValueError(f"OpenVEX statement {index} is not an object")
        status = statement.get("status")
        if status not in {"fixed", "not_affected"}:
            continue
        if status == "not_affected":
            review_by = statement.get("x_review_by")
            if not review_by:
                continue
            try:
                review_date = datetime.fromisoformat(str(review_by)).date()
            except ValueError as error:
                raise ValueError(
                    f"OpenVEX statement {index} has invalid x_review_by"
                ) from error
            if review_date < today:
                continue
        vulnerability = statement.get("vulnerability")
        if not isinstance(vulnerability, dict):
            raise ValueError(f"OpenVEX statement {index} has no vulnerability object")
        aliases = vulnerability.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError(f"OpenVEX statement {index} aliases must be a list")
        identifiers.add(str(vulnerability.get("@id", "")))
        identifiers.update(str(alias) for alias in aliases)
    return identifiers - {""}


def verify_vulnerability_dispositions(
    audit_payload: dict[str, Any],
    vex_payload: dict[str, Any],
    *,
    on_date: date | None = None,
) -> dict[str, Any]:
    """Require every vulnerability in a pip-audit report to have current VEX coverage."""

    if not isinstance(audit_payload, dict):
        raise ValueError("pip-audit report must be a JSON object")
    accepted = accepted_vex_identifiers(vex_payload, on_date=on_date)
    dependencies = audit_payload.get("dependencies")
    if not isinstance(dependencies, list):
        raise ValueError("pip-audit dependencies must be a list")
    reviewed: list[dict[str, str]] = []
    unreviewed: list[dict[str, str]] = []
    for dependency_index, dependency in enumerate(dependencies):
        if not isinstance(dependency, dict):
            raise ValueError(f"pip-audit dependency {dependency_index} is not an object")
        vulnerabilities = dependency.get("vulns", [])
        if not isinstance(vulnerabilities, list):
            raise ValueError(
                f"pip-audit dependency {dependency_index} vulnerabilities must be a list"
            )
        for vulnerability_index, vulnerability in enumerate(vulnerabilities):
            if not isinstance(vulnerability, dict):
                raise ValueError(
                    f"pip-audit vulnerability {dependency_index}:{vulnerability_index} "
                    "is not an object"
                )
            aliases = vulnerability.get("aliases", [])
            if not isinstance(aliases, list):
                raise ValueError(
                    f"pip-audit vulnerability {dependency_index}:{vulnerability_index} "
                    "aliases must be a list"
                )
            vulnerability_id = str(vulnerability.get("id", ""))
            identifiers = {vulnerability_id, *(str(alias) for alias in aliases)} - {""}
            item = {
                "package": str(dependency.get("name", "")),
                "version": str(dependency.get("version", "")),
                "vulnerability": vulnerability_id,
            }
            (reviewed if identifiers & accepted else unreviewed).append(item)
    return {
        "verified": not unreviewed,
        "accepted_vex_identifiers": sorted(accepted),
        "reviewed_vex": reviewed,
        "unreviewed": unreviewed,
    }


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
