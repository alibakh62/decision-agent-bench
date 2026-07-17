"""Local release-integrity audit with machine-readable evidence."""

from __future__ import annotations

import json
import re
import struct
import subprocess
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from decision_agent_bench.evals.tools import benchmark_tools
from decision_agent_bench.integrity import (
    accepted_vex_identifiers,
    verify_pip_audit_inventory,
    verify_vulnerability_dispositions,
)
from decision_agent_bench.simulator import GenerationConfig, RetailEnvironment, generate_world
from decision_agent_bench.simulator.environment import ToolError
from decision_agent_bench.simulator.reference import verify_reference_world
from decision_agent_bench.simulator.schema import INTERNAL_TABLES, PUBLIC_TABLES
from decision_agent_bench.specs import validate_task_specs

SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    "openai_key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "bearer_token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{32,}\b"),
}
SKIP_SUFFIXES = {".eval", ".pyc", ".sqlite", ".pptx", ".whl", ".gz", ".zip"}


@dataclass(frozen=True)
class AuditCheck:
    """One independently verifiable audit result."""

    check_id: str
    status: str
    summary: str
    evidence: dict[str, Any]


def _repository_files(repository: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repository,
        check=False,
        capture_output=True,
    )
    if result.returncode == 0:
        return [
            repository / item.decode()
            for item in result.stdout.split(b"\0")
            if item
        ]
    return [path for path in repository.rglob("*") if path.is_file() and ".git" not in path.parts]


def secret_findings(paths: list[Path]) -> list[dict[str, Any]]:
    """Return high-confidence credential findings without echoing secret values."""

    findings: list[dict[str, Any]] = []
    for path in paths:
        if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    findings.append(
                        {"path": str(path), "line": line_number, "rule": rule}
                    )
    return findings


def _secret_check(repository: Path) -> AuditCheck:
    paths = _repository_files(repository)
    findings = secret_findings(paths)
    return AuditCheck(
        "secrets",
        "fail" if findings else "pass",
        "high-confidence credential patterns found" if findings else "no credential patterns found",
        {"files_scanned": len(paths), "findings": findings},
    )


def _oracle_boundary_check(repository: Path) -> AuditCheck:
    errors: list[str] = []
    if PUBLIC_TABLES & INTERNAL_TABLES:
        errors.append("public and internal table sets overlap")
    tools_source = (repository / "src/decision_agent_bench/evals/tools.py").read_text(
        encoding="utf-8"
    )
    if "simulator.oracle" in tools_source or "EconomicOracle" in tools_source:
        errors.append("agent-facing tool adapters import the economic oracle")
    tool_names = sorted(
        str(getattr(getattr(tool, "__registry_info__", None), "name", tool.__name__))
        for tool in benchmark_tools()
    )
    with tempfile.TemporaryDirectory(prefix="dab-audit-") as directory:
        database = generate_world(Path(directory) / "world", GenerationConfig())
        with RetailEnvironment(database) as environment:
            for table in sorted({*INTERNAL_TABLES, "sqlite_master"}):
                try:
                    environment.query_sql(f'SELECT * FROM "{table}" LIMIT 1')
                except ToolError:
                    continue
                errors.append(f"agent SQL accessed internal table {table}")
    return AuditCheck(
        "oracle_boundary",
        "fail" if errors else "pass",
        "oracle boundary failed" if errors else "oracle-only state is denied to agent interfaces",
        {
            "errors": errors,
            "internal_tables": sorted(INTERNAL_TABLES),
            "agent_tools": tool_names,
        },
    )


def _provenance_check(repository: Path) -> AuditCheck:
    required = ["LICENSE", "docs/data-card.md", "CITATION.cff", ".zenodo.json"]
    missing = [name for name in required if not (repository / name).is_file()]
    data_card = (repository / "docs/data-card.md").read_text(encoding="utf-8")
    assertions = {
        "synthetic_generation": "All entities and events are created by project code" in data_card,
        "no_proprietary_data": "No proprietary retailer data" in data_card,
        "privacy_limitations": "Known limitations" in data_card,
    }
    errors = [f"missing {name}" for name in missing]
    errors.extend(name for name, passed in assertions.items() if not passed)
    return AuditCheck(
        "provenance",
        "fail" if errors else "pass",
        (
            "provenance evidence incomplete"
            if errors
            else "license and synthetic-data provenance present"
        ),
        {"errors": errors, "assertions": assertions},
    )


def _artifact_check(repository: Path) -> AuditCheck:
    articles = sorted((repository / "articles").glob("*.md"))
    presentation = repository / "talk/decision-agent-bench-research-talk.pptx"
    report = repository / "report/technical-report.md"
    social_preview = repository / "docs/assets/social-preview.png"
    errors = []
    if len(articles) != 3:
        errors.append(f"expected 3 articles, found {len(articles)}")
    if not report.is_file():
        errors.append("technical report is missing")
    if not presentation.is_file() or not zipfile.is_zipfile(presentation):
        errors.append("editable presentation is missing or structurally invalid")
    preview_evidence: dict[str, Any] = {
        "path": "docs/assets/social-preview.png",
        "dimensions": None,
        "bytes": None,
        "opaque": None,
    }
    try:
        content = social_preview.read_bytes()
        header = content[:26]
        if (
            len(header) < 26
            or header[:8] != b"\x89PNG\r\n\x1a\n"
            or header[12:16] != b"IHDR"
        ):
            raise ValueError("not a PNG with an IHDR header")
        width, height = struct.unpack(">II", header[16:24])
        color_type = header[25]
        chunk_types: list[bytes] = []
        offset = 8
        while offset < len(content):
            if offset + 12 > len(content):
                raise ValueError("truncated PNG chunk")
            length = struct.unpack(">I", content[offset : offset + 4])[0]
            chunk_type = content[offset + 4 : offset + 8]
            chunk_end = offset + 12 + length
            if chunk_end > len(content):
                raise ValueError("PNG chunk exceeds file length")
            chunk_types.append(chunk_type)
            offset = chunk_end
            if chunk_type == b"IEND":
                break
        if not chunk_types or chunk_types[-1] != b"IEND":
            raise ValueError("PNG has no terminal IEND chunk")
        opaque = color_type not in {4, 6} and b"tRNS" not in chunk_types
        preview_evidence["dimensions"] = [width, height]
        preview_evidence["bytes"] = social_preview.stat().st_size
        preview_evidence["opaque"] = opaque
        if (width, height) != (1280, 640):
            errors.append("social preview must be exactly 1280x640")
        if social_preview.stat().st_size >= 1_000_000:
            errors.append("social preview must be smaller than 1 MB")
        if not opaque:
            errors.append("social preview must have a solid opaque background")
    except (OSError, ValueError, struct.error) as error:
        errors.append(f"social preview is missing or invalid: {error}")
    return AuditCheck(
        "research_artifacts",
        "fail" if errors else "pass",
        (
            "research artifact set is incomplete"
            if errors
            else "report, articles, and deck are present"
        ),
        {
            "errors": errors,
            "articles": [path.name for path in articles],
            "social_preview": preview_evidence,
        },
    )


def _benchmark_check() -> AuditCheck:
    try:
        specifications = validate_task_specs()
        reference = verify_reference_world()
    except (OSError, ValueError) as error:
        return AuditCheck(
            "benchmark", "fail", "benchmark verification failed", {"error": str(error)}
        )
    return AuditCheck(
        "benchmark",
        "pass",
        "task contracts and reference world reproduce",
        {
            "task_families": specifications.task_count,
            "reference_world_sha256": reference["logical_sha256"],
            "tables": len(reference["table_counts"]),
        },
    )


def _vex_ids(repository: Path) -> set[str]:
    path = repository / "security/openvex.json"
    if not path.is_file():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return accepted_vex_identifiers(payload)


def _dependency_check(repository: Path, report_path: Path | None) -> AuditCheck:
    if report_path is None:
        return AuditCheck(
            "dependencies",
            "pending",
            "live pip-audit report not supplied",
            {"command": "pip-audit --require-hashes --disable-pip -r requirements.lock"},
        )
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        inventory = verify_pip_audit_inventory(repository / "requirements.lock", payload)
        vex_payload = json.loads(
            (repository / "security/openvex.json").read_text(encoding="utf-8")
        )
        dispositions = verify_vulnerability_dispositions(payload, vex_payload)
    except (OSError, ValueError, TypeError) as error:
        return AuditCheck(
            "dependencies",
            "fail",
            "dependency or OpenVEX report is invalid",
            {"error": str(error)},
        )
    if not inventory["verified"]:
        return AuditCheck(
            "dependencies",
            "fail",
            "dependency audit does not cover requirements.lock",
            {"inventory": inventory, "reviewed_vex": [], "unreviewed": []},
        )
    unreviewed = dispositions["unreviewed"]
    reviewed = dispositions["reviewed_vex"]
    return AuditCheck(
        "dependencies",
        "fail" if unreviewed else "pass",
        "unreviewed dependency vulnerabilities found"
        if unreviewed
        else "no unreviewed dependency vulnerabilities",
        {
            "dependencies_scanned": len(payload.get("dependencies", [])),
            "inventory": inventory,
            "reviewed_vex": reviewed,
            "unreviewed": unreviewed,
        },
    )


def _release_gates(repository: Path) -> list[AuditCheck]:
    identity_files = (
        "pyproject.toml",
        "CITATION.cff",
        "security/openvex.json",
    )
    identity_text = "\n".join(
        (repository / path).read_text(encoding="utf-8")
        for path in identity_files
    )
    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    return [
        AuditCheck(
            "repository_identity",
            "pending" if "OWNER" in identity_text or remote.returncode else "pass",
            "GitHub owner/remote is not configured"
            if "OWNER" in identity_text or remote.returncode
            else "GitHub identity is configured",
            {
                "origin": remote.stdout.strip() or None,
                "owner_placeholders": identity_text.count("OWNER"),
            },
        ),
        AuditCheck(
            "clean_worktree",
            "pending" if status.stdout.strip() else "pass",
            "working tree contains uncommitted changes"
            if status.stdout.strip()
            else "working tree is clean",
            {"changed_entries": len(status.stdout.splitlines())},
        ),
    ]


def _container_check(image: str | None) -> AuditCheck:
    if image is None:
        return AuditCheck(
            "container",
            "pending",
            "verified container image not supplied",
            {"expected_command": "docker run --rm <image>"},
        )
    inspect_result = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    verify_result = subprocess.run(
        ["docker", "run", "--rm", image],
        check=False,
        capture_output=True,
        text=True,
    )
    user_result = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "id", image],
        check=False,
        capture_output=True,
        text=True,
    )
    expected_digest = "c362c754d6f102c76d45aecf61f6e1cec7a49134fb416e02e59f341a20305f0b"
    errors = []
    if inspect_result.returncode:
        errors.append("image inspection failed")
    if verify_result.returncode or expected_digest not in verify_result.stdout:
        errors.append("default reference-world verification failed")
    if user_result.returncode or "uid=10001(benchmark)" not in user_result.stdout:
        errors.append("container did not run as the benchmark user")
    return AuditCheck(
        "container",
        "fail" if errors else "pass",
        "container verification failed" if errors else "container is reproducible and non-root",
        {
            "image": image,
            "image_id": inspect_result.stdout.strip() or None,
            "default_output": verify_result.stdout.strip()[-500:],
            "runtime_user": user_result.stdout.strip(),
            "errors": errors,
        },
    )


def audit_repository(
    repository: Path,
    *,
    dependency_report: Path | None = None,
    container_image: str | None = None,
) -> dict[str, Any]:
    """Run deterministic local checks and return a release-readiness report."""

    repository = repository.resolve()
    checks = [
        _benchmark_check(),
        _oracle_boundary_check(repository),
        _secret_check(repository),
        _provenance_check(repository),
        _artifact_check(repository),
        _dependency_check(repository, dependency_report),
        _container_check(container_image),
        *_release_gates(repository),
    ]
    statuses = {check.status for check in checks}
    overall = "fail" if "fail" in statuses else "pending" if "pending" in statuses else "pass"
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "repository": str(repository),
        "status": overall,
        "checks": [asdict(check) for check in checks],
    }


def write_audit_report(report: dict[str, Any], output: Path) -> Path:
    """Write a formatted audit report."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
