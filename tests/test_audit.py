from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from decision_agent_bench.audit import (
    _container_check,
    _dependency_check,
    _vex_ids,
    audit_repository,
    secret_findings,
)


def test_secret_scanner_detects_high_confidence_key_without_echoing_value(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.env"
    fake_key = "sk-" + "a" * 32
    path.write_text(f"OPENAI_API_KEY={fake_key}\n", encoding="utf-8")

    findings = secret_findings([path])

    assert findings == [{"path": str(path), "line": 1, "rule": "openai_key"}]
    assert fake_key not in str(findings)


def test_repository_audit_passes_deterministic_safety_checks() -> None:
    repository = Path(__file__).parents[1]

    report = audit_repository(repository)
    checks = {item["check_id"]: item for item in report["checks"]}

    assert checks["benchmark"]["status"] == "pass"
    assert checks["oracle_boundary"]["status"] == "pass"
    assert checks["oracle_boundary"]["evidence"]["agent_tools"] == [
        "change_store_price",
        "forecast_demand",
        "recommend_inventory",
        "request_approval",
        "retail_sql",
        "search_documents",
    ]
    assert checks["secrets"]["status"] == "pass"
    assert checks["provenance"]["status"] == "pass"
    assert checks["research_artifacts"]["status"] == "pass"
    assert checks["research_artifacts"]["evidence"]["social_preview"] == {
        "path": "docs/assets/social-preview.png",
        "dimensions": [1280, 640],
        "bytes": (repository / "docs/assets/social-preview.png").stat().st_size,
        "opaque": True,
    }
    assert checks["dependencies"]["status"] == "pending"
    assert checks["container"]["status"] == "pending"
    assert report["status"] == "pending"


def test_container_audit_uses_allow_listed_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        output = (
            "sha256:image\n"
            if command[1:3] == ["image", "inspect"]
            else "uid=10001(benchmark) gid=10001(benchmark)\n"
            if command[-1] == "image" and "id" in command
            else "verified reference world logical_sha256="
            "c362c754d6f102c76d45aecf61f6e1cec7a49134fb416e02e59f341a20305f0b\n"
        )
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr("decision_agent_bench.audit.subprocess.run", run)

    result = _container_check("image", "podman")

    assert result.status == "pass"
    assert result.evidence["runtime"] == "podman"
    assert all(command[0] == "podman" for command in commands)
    with pytest.raises(ValueError, match="docker or podman"):
        _container_check("image", "nerdctl")


def test_dependency_audit_requires_vex_for_every_vulnerability(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / "security").mkdir(parents=True)
    (repository / "requirements.lock").write_text("click==8.2.1\n", encoding="utf-8")
    (repository / "security/openvex.json").write_text(
        json.dumps(
            {
                "statements": [
                    {
                        "vulnerability": {
                            "@id": "PYSEC-2026-2132",
                            "aliases": ["CVE-2026-7246"],
                        },
                        "status": "not_affected",
                        "justification": "component_not_present",
                        "impact_statement": "The benchmark does not call click.edit().",
                        "x_review_by": "2099-01-01",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = tmp_path / "pip-audit.json"
    report.write_text(
        json.dumps(
            {
                "dependencies": [
                    {
                        "name": "click",
                        "version": "8.2.1",
                        "vulns": [
                            {
                                "id": "PYSEC-2026-2132",
                                "aliases": ["CVE-2026-7246"],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    reviewed = _dependency_check(repository, report)
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["dependencies"][0]["vulns"][0] = {"id": "CVE-2099-0001", "aliases": []}
    report.write_text(json.dumps(payload), encoding="utf-8")
    unreviewed = _dependency_check(repository, report)

    assert reviewed.status == "pass"
    assert reviewed.evidence["reviewed_vex"][0]["package"] == "click"
    assert reviewed.evidence["inventory"]["verified"] is True
    assert unreviewed.status == "fail"


def test_dependency_audit_rejects_incomplete_or_mismatched_inventory(tmp_path: Path) -> None:
    (tmp_path / "security").mkdir()
    (tmp_path / "security/openvex.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "requirements.lock").write_text(
        "click==8.2.1\nrequests==2.34.2\n", encoding="utf-8"
    )
    report = tmp_path / "pip-audit.json"
    report.write_text(
        json.dumps(
            {
                "dependencies": [
                    {"name": "click", "version": "8.3.0", "vulns": []}
                ]
            }
        ),
        encoding="utf-8",
    )

    result = _dependency_check(tmp_path, report)

    assert result.status == "fail"
    assert result.evidence["inventory"]["missing"] == ["requests"]
    assert result.evidence["inventory"]["version_mismatches"] == ["click==8.3.0"]


def test_expired_not_affected_vex_statement_is_not_accepted(tmp_path: Path) -> None:
    security = tmp_path / "security"
    security.mkdir()
    (security / "openvex.json").write_text(
        json.dumps(
            {
                "statements": [
                    {
                        "vulnerability": {"@id": "CVE-2099-0001"},
                        "status": "not_affected",
                        "x_review_by": "2020-01-01",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert _vex_ids(tmp_path) == set()
