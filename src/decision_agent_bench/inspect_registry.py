"""Offline readiness checks for an Inspect Evals Register submission."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REGISTER_GUIDE_URL = (
    "https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/register/README.md"
)
SUBMISSION_FORM_URL = (
    "https://github.com/UKGovernmentBEIS/inspect_evals/issues/new"
    "?template=register-submission.yml"
)
DEFAULT_TASK = "decision_agent_bench_v0_2"
TASK_PATH = Path("src/decision_agent_bench/evals/task.py")
ARXIV_PATTERN = re.compile(r"https://arxiv\.org/abs/\d{4}\.\d{4,5}v\d+\Z")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
GITHUB_REPOSITORY_PATTERN = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/"
    r"(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?\Z"
)
MAINTAINER_PATTERN = re.compile(r"@?[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\Z")
RUNTIME_FETCH_PATTERNS = {
    "requests": re.compile(r"\brequests\.(?:get|post|request)\s*\("),
    "httpx": re.compile(r"\bhttpx\.(?:get|post|request|stream)\s*\("),
    "urllib": re.compile(r"\burlopen\s*\("),
    "hugging_face_dataset": re.compile(r"\bload_dataset\s*\("),
    "hugging_face_hub": re.compile(r"\b(?:hf_hub_download|snapshot_download)\s*\("),
    "fsspec": re.compile(r"\bfsspec\.open\s*\("),
}


@dataclass(frozen=True)
class RegistrationCheck:
    """One local or publication-input requirement."""

    check_id: str
    status: str
    summary: str
    evidence: dict[str, Any]


def _git_state(repository: Path) -> tuple[str | None, bool]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
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
    commit = head.stdout.strip() if head.returncode == 0 else None
    return commit, status.returncode == 0 and not status.stdout.strip()


def _task_decorator_line(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int | None:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "task":
            return decorator.lineno
        if isinstance(target, ast.Attribute) and target.attr == "task":
            return decorator.lineno
    return None


def discover_tasks(source: Path) -> dict[str, int]:
    """Return ``@task`` function names and decorator line numbers."""

    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    tasks: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            line = _task_decorator_line(node)
            if line is not None:
                tasks[node.name] = line
    return dict(sorted(tasks.items()))


def _project_checks(repository: Path) -> list[RegistrationCheck]:
    project_path = repository / "pyproject.toml"
    try:
        pyproject = tomllib.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        return [
            RegistrationCheck(
                "installable_project",
                "fail",
                "pyproject.toml could not be loaded",
                {"error": str(error)},
            )
        ]
    project = pyproject.get("project")
    if not isinstance(project, dict):
        return [
            RegistrationCheck(
                "installable_project",
                "fail",
                "pyproject.toml has no [project] table",
                {"path": "pyproject.toml"},
            )
        ]
    dependencies = project.get("dependencies", [])
    names = {
        re.split(r"[<>=!~;\s\[]", str(requirement), maxsplit=1)[0]
        .lower()
        .replace("_", "-")
        .replace(".", "-")
        for requirement in dependencies
    }
    return [
        RegistrationCheck(
            "installable_project",
            "pass",
            "PEP 517 project metadata is present",
            {"path": "pyproject.toml", "project_name": project.get("name")},
        ),
        RegistrationCheck(
            "inspect_dependency",
            "pass" if "inspect-ai" in names else "fail",
            (
                "inspect-ai is a declared runtime dependency"
                if "inspect-ai" in names
                else "inspect-ai is not a declared runtime dependency"
            ),
            {"dependencies": sorted(str(item) for item in dependencies)},
        ),
    ]


def _asset_check(repository: Path) -> RegistrationCheck:
    try:
        pyproject = tomllib.loads(
            (repository / "pyproject.toml").read_text(encoding="utf-8")
        )
    except (OSError, tomllib.TOMLDecodeError) as error:
        return RegistrationCheck(
            "asset_pinning",
            "fail",
            "asset packaging could not be inspected",
            {"error": str(error), "packaged_assets": [], "runtime_fetches": []},
        )
    force_include = (
        pyproject.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
        .get("force-include", {})
    )
    packaged_assets: list[dict[str, str]] = []
    missing: list[str] = []
    if isinstance(force_include, dict):
        for source, destination in sorted(force_include.items()):
            if str(destination).startswith("decision_agent_bench/data/"):
                packaged_assets.append(
                    {"source": str(source), "destination": str(destination)}
                )
                if not (repository / str(source)).is_file():
                    missing.append(str(source))

    runtime_fetches: list[dict[str, str]] = []
    for root in (repository / "src", repository / "data"):
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".json"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for fetcher, pattern in RUNTIME_FETCH_PATTERNS.items():
                if pattern.search(text):
                    runtime_fetches.append(
                        {"path": str(path.relative_to(repository)), "fetcher": fetcher}
                    )
    errors = []
    if not packaged_assets:
        errors.append("no benchmark assets are included in the wheel")
    if missing:
        errors.append("declared packaged assets are missing")
    if runtime_fetches:
        errors.append("runtime network assets require a manual immutable-revision review")
    return RegistrationCheck(
        "asset_pinning",
        "fail" if errors else "pass",
        (
            "asset packaging or pinning is incomplete"
            if errors
            else "benchmark assets are local, versioned, and included in the wheel"
        ),
        {
            "errors": errors,
            "packaged_assets": packaged_assets,
            "missing": missing,
            "runtime_fetches": runtime_fetches,
        },
    )


def _publication_checks(
    *,
    repository_url: str | None,
    commit: str | None,
    local_commit: str | None,
    arxiv_url: str | None,
    maintainers: tuple[str, ...],
    working_tree_clean: bool,
) -> list[RegistrationCheck]:
    repository_match = (
        GITHUB_REPOSITORY_PATTERN.fullmatch(repository_url) if repository_url else None
    )
    repository_status = "pass" if repository_match and "OWNER" not in repository_url else (
        "pending" if not repository_url else "fail"
    )
    if not commit:
        commit_status = "pending"
        commit_summary = "a source commit is required"
    elif not COMMIT_PATTERN.fullmatch(commit):
        commit_status = "fail"
        commit_summary = "source commit must be a lowercase 40-character SHA"
    elif commit != local_commit:
        commit_status = "fail"
        commit_summary = "source commit must equal the checked-out HEAD"
    else:
        commit_status = "pass"
        commit_summary = "source is pinned to the checked-out 40-character commit"
    arxiv_status = "pass" if arxiv_url and ARXIV_PATTERN.fullmatch(arxiv_url) else (
        "pending" if not arxiv_url else "fail"
    )
    invalid_maintainers = [
        maintainer for maintainer in maintainers if not MAINTAINER_PATTERN.fullmatch(maintainer)
    ]
    return [
        RegistrationCheck(
            "repository_url",
            repository_status,
            {
                "pass": "public GitHub repository URL is syntactically valid",
                "pending": "public GitHub repository URL is required",
                "fail": "repository URL must identify a non-placeholder GitHub repository",
            }[repository_status],
            {"repository_url": repository_url},
        ),
        RegistrationCheck(
            "repository_commit",
            commit_status,
            commit_summary,
            {"commit": commit, "local_head": local_commit},
        ),
        RegistrationCheck(
            "clean_worktree",
            "pass" if working_tree_clean else "pending",
            (
                "working tree is clean"
                if working_tree_clean
                else "commit the current work before preparing a pinned source URL"
            ),
            {"working_tree_clean": working_tree_clean},
        ),
        RegistrationCheck(
            "versioned_arxiv",
            arxiv_status,
            {
                "pass": "versioned arXiv abstract URL is present",
                "pending": "versioned arXiv abstract URL is required by the submission form",
                "fail": "arXiv URL must use a versioned /abs/<id>v<n> form",
            }[arxiv_status],
            {"arxiv_url": arxiv_url},
        ),
        RegistrationCheck(
            "maintainers",
            "fail" if invalid_maintainers else "pass",
            (
                "maintainer usernames are invalid"
                if invalid_maintainers
                else "optional additional maintainer usernames are valid"
            ),
            {
                "maintainers": [item.removeprefix("@") for item in maintainers],
                "invalid": invalid_maintainers,
                "submitter_included_automatically": True,
            },
        ),
    ]


def audit_inspect_registration(
    repository: Path,
    *,
    repository_url: str | None = None,
    commit: str | None = None,
    arxiv_url: str | None = None,
    maintainers: tuple[str, ...] = (),
    task_name: str = DEFAULT_TASK,
) -> dict[str, Any]:
    """Audit local requirements and publication inputs for one register issue."""

    repository = repository.resolve()
    local_commit, working_tree_clean = _git_state(repository)
    selected_commit = commit or local_commit
    task_source = repository / TASK_PATH
    try:
        tasks = discover_tasks(task_source)
        task_error = None
    except (OSError, SyntaxError) as error:
        tasks = {}
        task_error = str(error)
    task_status = "pass" if task_name in tasks else "fail"
    checks = [
        *_project_checks(repository),
        RegistrationCheck(
            "decorated_task",
            task_status,
            (
                "selected task is defined with @task"
                if task_status == "pass"
                else "selected @task function was not found"
            ),
            {
                "task": task_name,
                "task_path": str(TASK_PATH),
                "decorator_line": tasks.get(task_name),
                "discovered_tasks": tasks,
                "error": task_error,
            },
        ),
        _asset_check(repository),
        *_publication_checks(
            repository_url=repository_url,
            commit=selected_commit,
            local_commit=local_commit,
            arxiv_url=arxiv_url,
            maintainers=maintainers,
            working_tree_clean=working_tree_clean,
        ),
    ]
    statuses = {check.status for check in checks}
    overall = "fail" if "fail" in statuses else "pending" if "pending" in statuses else "pass"
    source_url = None
    if (
        repository_url
        and "OWNER" not in repository_url
        and GITHUB_REPOSITORY_PATTERN.fullmatch(repository_url)
        and selected_commit
        and COMMIT_PATTERN.fullmatch(selected_commit)
        and selected_commit == local_commit
        and working_tree_clean
        and task_name in tasks
    ):
        source_url = (
            f"{repository_url.removesuffix('.git')}/blob/{selected_commit}/{TASK_PATH}"
            f"#L{tasks[task_name]}"
        )
    return {
        "schema_version": "1.0.0",
        "status": overall,
        "task": task_name,
        "source_url": source_url,
        "register_guide": REGISTER_GUIDE_URL,
        "submission_form": SUBMISSION_FORM_URL,
        "checks": [asdict(check) for check in checks],
        "upstream_verification": [
            "submitter has at least one commit in the public repository",
            "repository and commit resolve publicly",
            "task constructs a runnable Inspect Task with a dataset and scorer",
            "description and security properties pass the register workflow",
        ],
    }


def prepare_inspect_submission(
    repository: Path,
    output: Path,
    *,
    repository_url: str,
    arxiv_url: str,
    commit: str | None = None,
    maintainers: tuple[str, ...] = (),
    task_name: str = DEFAULT_TASK,
) -> dict[str, Any]:
    """Write exact issue-form inputs after all offline gates pass."""

    report = audit_inspect_registration(
        repository,
        repository_url=repository_url,
        commit=commit,
        arxiv_url=arxiv_url,
        maintainers=maintainers,
        task_name=task_name,
    )
    if report["status"] != "pass":
        blockers = [
            check["check_id"]
            for check in report["checks"]
            if check["status"] != "pass"
        ]
        raise ValueError("Inspect registration is not ready: " + ", ".join(blockers))

    normalized_maintainers = [item.removeprefix("@") for item in maintainers]
    submission = {
        "schema_version": "1.0.0",
        "task": task_name,
        "form_url": SUBMISSION_FORM_URL,
        "form_fields": {
            "arxiv_url": arxiv_url,
            "source_url": report["source_url"],
            "maintainers": normalized_maintainers,
        },
        "audit": report,
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "submission.json").write_text(
        json.dumps(submission, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    maintainer_text = "\n".join(normalized_maintainers) or "_None; submitter is automatic._"
    (output / "issue-form-values.md").write_text(
        "# Inspect Evals Register issue values\n\n"
        f"Form: {SUBMISSION_FORM_URL}\n\n"
        "## arXiv URL\n\n"
        f"{arxiv_url}\n\n"
        "## Source URL\n\n"
        f"{report['source_url']}\n\n"
        "## Maintainers\n\n"
        f"{maintainer_text}\n",
        encoding="utf-8",
    )
    return submission
