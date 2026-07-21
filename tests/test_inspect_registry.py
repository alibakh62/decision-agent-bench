from __future__ import annotations

import json
from pathlib import Path

import pytest

from decision_agent_bench.inspect_registry import (
    audit_inspect_registration,
    discover_tasks,
    prepare_inspect_submission,
)


def _checks(report: dict[str, object]) -> dict[str, dict[str, object]]:
    return {item["check_id"]: item for item in report["checks"]}  # type: ignore[index]


def test_registration_audit_verifies_local_upstream_requirements() -> None:
    repository = Path(__file__).parents[1]

    report = audit_inspect_registration(repository)
    checks = _checks(report)

    assert report["status"] == "pending"
    assert checks["installable_project"]["status"] == "pass"
    assert checks["inspect_dependency"]["status"] == "pass"
    assert checks["decorated_task"]["status"] == "pass"
    assert checks["asset_pinning"]["status"] == "pass"
    assert checks["repository_url"]["status"] == "pass"
    assert checks["repository_url"]["evidence"] == {
        "repository_url": "https://github.com/alibakh62/decision-agent-bench"
    }
    assert checks["versioned_arxiv"]["status"] == "pending"
    assert report["source_url"] is None


def test_task_discovery_returns_decorator_lines() -> None:
    repository = Path(__file__).parents[1]

    tasks = discover_tasks(repository / "src/decision_agent_bench/evals/task.py")

    assert set(tasks) == {"decision_agent_bench", "decision_agent_bench_v0_2"}
    assert all(line > 0 for line in tasks.values())


def test_registration_audit_rejects_unversioned_paper_and_placeholder_repo() -> None:
    repository = Path(__file__).parents[1]

    report = audit_inspect_registration(
        repository,
        repository_url="https://github.com/OWNER/decision-agent-bench",
        arxiv_url="https://arxiv.org/abs/2607.12345",
    )
    checks = _checks(report)

    assert report["status"] == "fail"
    assert checks["repository_url"]["status"] == "fail"
    assert checks["versioned_arxiv"]["status"] == "fail"


def test_registration_audit_rejects_commit_other_than_checked_out_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[1]
    monkeypatch.setattr(
        "decision_agent_bench.inspect_registry._git_state",
        lambda _repository: ("a" * 40, True),
    )

    report = audit_inspect_registration(repository, commit="b" * 40)

    assert _checks(report)["repository_commit"]["status"] == "fail"
    assert "checked-out HEAD" in _checks(report)["repository_commit"]["summary"]


def test_prepare_registration_writes_exact_issue_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = Path(__file__).parents[1]
    commit = "a" * 40
    monkeypatch.setattr(
        "decision_agent_bench.inspect_registry._git_state",
        lambda _repository: (commit, True),
    )

    submission = prepare_inspect_submission(
        repository,
        tmp_path / "submission",
        repository_url="https://github.com/example/decision-agent-bench",
        arxiv_url="https://arxiv.org/abs/2607.12345v1",
        maintainers=("@maintainer-one",),
    )
    on_disk = json.loads(
        (tmp_path / "submission/submission.json").read_text(encoding="utf-8")
    )
    issue_values = (tmp_path / "submission/issue-form-values.md").read_text(
        encoding="utf-8"
    )

    assert submission == on_disk
    assert submission["form_fields"]["source_url"].startswith(
        f"https://github.com/example/decision-agent-bench/blob/{commit}/"
    )
    assert "#L" in submission["form_fields"]["source_url"]
    assert submission["form_fields"]["maintainers"] == ["maintainer-one"]
    assert "https://arxiv.org/abs/2607.12345v1" in issue_values


def test_prepare_registration_refuses_pending_inputs(tmp_path: Path) -> None:
    repository = Path(__file__).parents[1]

    with pytest.raises(ValueError, match="versioned_arxiv"):
        prepare_inspect_submission(
            repository,
            tmp_path / "submission",
            repository_url="https://github.com/example/decision-agent-bench",
            arxiv_url="https://arxiv.org/abs/2607.12345",
        )
