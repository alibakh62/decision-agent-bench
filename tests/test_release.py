from __future__ import annotations

import json
from pathlib import Path

import pytest

from decision_agent_bench.experiments.analysis import ANALYSIS_ARTIFACTS
from decision_agent_bench.integrity import digest_payload, file_evidence
from decision_agent_bench.release import assemble_release_bundle, verify_release_bundle


def _write_fake_repository(root: Path, version: str = "0.2.0.dev0") -> Path:
    files = {
        "pyproject.toml": f'[project]\nname = "decision-agent-bench"\nversion = "{version}"\n',
        "data/task_specs/v0.1.json": json.dumps([{"id": "one"}, {"id": "two"}]),
        "data/task_specs/v0.2-instances.json": json.dumps(
            [{"instance_id": str(index)} for index in range(3)]
        ),
        "data/reference-world-manifest.json": json.dumps({"logical_sha256": "a" * 64}),
        "report/technical-report.md": "# Report\n",
        "talk/decision-agent-bench-research-talk.pptx": "presentation",
        "docs/assets/social-preview.png": "preview",
        "CITATION.cff": "cff-version: 1.2.0\n",
        ".zenodo.json": "{}\n",
        "LICENSE": "MIT\n",
        "security/openvex.json": "{}\n",
        "requirements.lock": "inspect-ai==0.3.247\n",
        "Dockerfile": "FROM scratch\n",
        "articles/one.md": "# One\n",
        "articles/two.md": "# Two\n",
        "articles/three.md": "# Three\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    distribution = root / "dist"
    distribution.mkdir()
    (distribution / f"decision_agent_bench-{version}-py3-none-any.whl").write_bytes(b"wheel")
    (distribution / f"decision_agent_bench-{version}.tar.gz").write_bytes(b"source")
    return distribution


def _clean_state(version: str = "0.2.0.dev0") -> dict[str, object]:
    return {
        "git_commit": "b" * 40,
        "working_tree_clean": True,
        "commit_timestamp": "2026-07-17T12:00:00-05:00",
        "tags": [f"v{version}"],
    }


def _write_publishable_analysis(directory: Path) -> None:
    directory.mkdir()
    for name in ANALYSIS_ARTIFACTS:
        (directory / name).write_text(f"published: {name}\n", encoding="utf-8")
    payload: dict[str, object] = {
        "schema_version": "2.0.0",
        "source_log_count": 0,
        "source_logs": [],
        "source_log_status_counts": {},
        "contains_publishable_runs": True,
        "experiment_manifest": None,
        "artifacts": [
            file_evidence(directory / name, relative_to=directory)
            for name in ANALYSIS_ARTIFACTS
        ],
    }
    payload["manifest_sha256"] = digest_payload(payload)
    (directory / "analysis-manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_release_bundle_is_exact_and_detects_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    distribution = _write_fake_repository(repository)
    monkeypatch.setattr(
        "decision_agent_bench.release._git_release_state", lambda _repository: _clean_state()
    )
    bundle = tmp_path / "bundle"

    manifest = assemble_release_bundle(
        repository,
        distribution,
        bundle,
        allow_prerelease=True,
    )
    verified = verify_release_bundle(bundle)
    (bundle / "research/technical-report.md").write_text("tampered\n", encoding="utf-8")
    tampered = verify_release_bundle(bundle)

    assert manifest["benchmark"] == {
        "task_families": 2,
        "v0_2_instances": 3,
        "v0_2_paired_samples": 6,
        "reference_world_sha256": "a" * 64,
    }
    assert verified["verified"] is True
    assert verified["artifact_count"] == 17
    assert tampered["verified"] is False
    assert "sha256 mismatch: research/technical-report.md" in tampered["issues"]
    assert "SHA256SUMS does not match release contents" in tampered["issues"]


def test_release_bundle_rejects_unexpected_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    distribution = _write_fake_repository(repository)
    monkeypatch.setattr(
        "decision_agent_bench.release._git_release_state", lambda _repository: _clean_state()
    )
    bundle = tmp_path / "bundle"
    assemble_release_bundle(repository, distribution, bundle, allow_prerelease=True)
    (bundle / "unexpected.txt").write_text("not declared\n", encoding="utf-8")

    report = verify_release_bundle(bundle)

    assert report["verified"] is False
    assert "release file set differs from the manifest" in report["issues"]


def test_release_assembly_requires_clean_source_and_final_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    distribution = _write_fake_repository(repository, version="1.0.0")
    dirty = {**_clean_state("1.0.0"), "working_tree_clean": False}
    monkeypatch.setattr(
        "decision_agent_bench.release._git_release_state", lambda _repository: dirty
    )

    with pytest.raises(ValueError, match="clean Git working tree"):
        assemble_release_bundle(repository, distribution, tmp_path / "dirty")

    monkeypatch.setattr(
        "decision_agent_bench.release._git_release_state",
        lambda _repository: _clean_state("1.0.0"),
    )
    with pytest.raises(ValueError, match="requires SBOM, dependency audit, and container"):
        assemble_release_bundle(repository, distribution, tmp_path / "missing-evidence")


def test_final_release_accepts_complete_tagged_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    distribution = _write_fake_repository(repository, version="1.0.0")
    monkeypatch.setattr(
        "decision_agent_bench.release._git_release_state",
        lambda _repository: _clean_state("1.0.0"),
    )
    monkeypatch.setattr(
        "decision_agent_bench.release._container_provenance",
        lambda _repository, image: {"status": "pass", "image": image},
    )
    sbom = tmp_path / "sbom.json"
    sbom.write_text(
        json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.6", "components": []}),
        encoding="utf-8",
    )
    dependency_report = tmp_path / "pip-audit.json"
    dependency_report.write_text(json.dumps({"dependencies": []}), encoding="utf-8")
    analysis = tmp_path / "primary"
    _write_publishable_analysis(analysis)

    manifest = assemble_release_bundle(
        repository,
        distribution,
        tmp_path / "bundle",
        sbom_path=sbom,
        dependency_report=dependency_report,
        container_image="decision-agent-bench:release",
        analysis_directories=(analysis,),
    )
    verified = verify_release_bundle(tmp_path / "bundle")

    assert manifest["contains_publishable_results"] is True
    assert verified["verified"] is True
    assert verified["artifact_count"] == 29
