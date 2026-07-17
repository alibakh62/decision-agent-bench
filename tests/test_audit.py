from __future__ import annotations

import json
from pathlib import Path

from decision_agent_bench.audit import (
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
    assert checks["dependencies"]["status"] == "pending"
    assert checks["container"]["status"] == "pending"
    assert report["status"] == "pending"


def test_dependency_audit_requires_vex_for_every_vulnerability(tmp_path: Path) -> None:
    repository = Path(__file__).parents[1]
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
    assert unreviewed.status == "fail"


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
