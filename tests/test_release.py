from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from decision_agent_bench.experiments.analysis import (
    ANALYSIS_ARTIFACTS,
    SampleRecord,
    _coverage_report,
    verify_analysis_bundle,
)
from decision_agent_bench.experiments.schema import ExperimentConfig
from decision_agent_bench.integrity import digest_payload, file_evidence, sha256_file
from decision_agent_bench.release import assemble_release_bundle, verify_release_bundle
from decision_agent_bench.specs import load_task_specs


def _write_fake_repository(root: Path, version: str = "0.2.1.dev0") -> Path:
    files = {
        "pyproject.toml": f'[project]\nname = "decision-agent-bench"\nversion = "{version}"\n',
        "data/task_specs/v0.1.json": json.dumps([{"id": "one"}, {"id": "two"}]),
        "data/task_specs/v0.2-instances.json": json.dumps(
            [{"instance_id": str(index)} for index in range(3)]
        ),
        "data/task_specs/v0.3-workflows.json": json.dumps(
            [
                {"workflow_id": "one", "instance_id": str(index)}
                for index in range(2)
            ]
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


def _clean_state(version: str = "0.2.1.dev0") -> dict[str, object]:
    return {
        "git_commit": "b" * 40,
        "working_tree_clean": True,
        "commit_timestamp": "2026-07-17T12:00:00-05:00",
        "tags": [f"v{version}"],
    }


def _write_publishable_analysis(directory: Path) -> None:
    directory.mkdir()
    run_id = "20260717T170000Z-publication"
    config = ExperimentConfig.from_dict(
        {
            "name": "primary-study",
            "models": [
                {
                    "model": f"provider-{index}/model",
                    "family": f"provider-{index}",
                    "display_name": f"Provider {index}",
                    "publishable": True,
                }
                for index in range(1, 4)
            ],
            "repetitions": 3,
            "budget": {"cost_limit_usd": 0.01, "study_cost_limit_usd": 9.0},
        }
    )
    config_payload = config.to_dict()
    cells = [
        {
            "cell_id": f"{model.family}-{baseline}-{variant}",
            "model": model.model,
            "model_family": model.family,
            "display_name": model.display_name,
            "publishable": model.publishable,
            "baseline": baseline,
            "variant": variant,
            "category": None,
        }
        for model in config.models
        for baseline in config.baselines
        for variant in config.variants
    ]
    scores = {
        "task_effectiveness": 0.9,
        "decision_quality": 0.9,
        "safety": 1.0,
        "robustness": 0.8,
        "calibration": 0.9,
        "efficiency": 0.8,
        "recovery": 0.8,
        "explainability": 0.9,
        "composite": 0.875,
    }
    records = [
        SampleRecord(
            run_id=run_id,
            benchmark_version=config.benchmark_version,
            task_version=str(spec["version"]),
            model=model.model,
            model_family=model.family,
            display_name=model.display_name,
            publishable=model.publishable,
            baseline=baseline,
            sample_id=f"{spec['id']}-{variant}",
            instance_id=f"{spec['id']}-i1",
            task_id=str(spec["id"]),
            scenario_seed=20260717,
            category=str(spec["category"]),
            difficulty=str(spec["difficulty"]),
            variant=variant,
            perturbation=(
                str(spec["perturbations"][0]) if variant == "perturbed" else None
            ),
            epoch=epoch,
            scores=scores,
            confidence=0.9,
            correct=True,
            failures=(),
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.001,
            latency_seconds=1.0,
            working_seconds=0.9,
            tool_calls=2,
            recoveries=1 if variant == "perturbed" else 0,
            turn_count=3,
        )
        for model in config.models
        for baseline in config.baselines
        for variant in config.variants
        for spec in load_task_specs()
        for epoch in range(1, config.repetitions + 1)
    ]
    for name in ANALYSIS_ARTIFACTS:
        if name != "samples.sanitized.jsonl":
            (directory / name).write_text(f"published: {name}\n", encoding="utf-8")
    (directory / "samples.sanitized.jsonl").write_text(
        "".join(json.dumps(asdict(record), sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    plan = {
        "run_id": run_id,
        "config": config_payload,
        "source": {
            "git_commit": "b" * 40,
            "working_tree_clean": True,
            "reference_world_sha256": "a" * 64,
        },
        "cells": cells,
    }
    coverage = _coverage_report(
        records, {"run_id": run_id, "config": config_payload, "cells": cells}
    )
    source_logs = [
        {
            "path": f"{cell['cell_id']}/results.eval",
            "bytes": 1,
            "sha256": "c" * 64,
            "status": "success",
        }
        for cell in cells
    ]
    payload: dict[str, object] = {
        "schema_version": "3.0.0",
        "source_log_count": len(source_logs),
        "source_logs": source_logs,
        "source_log_status_counts": {"success": len(source_logs)},
        "scored_samples": len(records),
        "run_ids": [run_id],
        "contains_publishable_runs": True,
        "coverage": coverage,
        "experiment_manifest": {
            "sha256": "d" * 64,
            "manifest_sha256": "e" * 64,
            "run_id": run_id,
            "source_git_commit": "b" * 40,
            "source_working_tree_clean": True,
            "publication_plan": plan,
        },
        "artifacts": [
            file_evidence(directory / name, relative_to=directory)
            for name in ANALYSIS_ARTIFACTS
        ],
        "sanitization": "test fixture excludes raw provider content",
    }
    payload["manifest_sha256"] = digest_payload(payload)
    (directory / "analysis-manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _resign_outer_bundle(directory: Path) -> None:
    manifest_path = directory / "release-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in payload["artifacts"]:
        path = directory / artifact["path"]
        artifact["bytes"] = path.stat().st_size
        artifact["sha256"] = sha256_file(path)
    unsigned = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    payload["manifest_sha256"] = digest_payload(unsigned)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksum_paths = sorted(
        [str(artifact["path"]) for artifact in payload["artifacts"]]
        + ["release-manifest.json"]
    )
    (directory / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(directory / path)}  {path}\n" for path in checksum_paths),
        encoding="utf-8",
    )


def _resign_analysis_bundle(directory: Path) -> None:
    manifest_path = directory / "analysis-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["artifacts"] = [
        file_evidence(directory / name, relative_to=directory)
        for name in ANALYSIS_ARTIFACTS
    ]
    payload.pop("manifest_sha256", None)
    payload["manifest_sha256"] = digest_payload(payload)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_publishable_analysis_rejects_rehashed_model_identity_tamper(
    tmp_path: Path,
) -> None:
    analysis = tmp_path / "primary"
    _write_publishable_analysis(analysis)
    samples_path = analysis / "samples.sanitized.jsonl"
    lines = samples_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["model_family"] = "counterfeit-family"
    lines[0] = json.dumps(first, sort_keys=True)
    samples_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _resign_analysis_bundle(analysis)

    report = verify_analysis_bundle(analysis)

    assert report["verified"] is False
    assert report["contains_publishable_runs"] is False
    assert "sanitized record 0 model metadata is inconsistent" in report["issues"]


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
        "v0_3_workflow_concepts": 1,
        "v0_3_instances": 2,
        "v0_3_paired_samples": 4,
        "reference_world_sha256": "a" * 64,
    }
    assert verified["verified"] is True
    assert verified["artifact_count"] == 18
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


def test_verifier_reports_missing_artifacts_and_malformed_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    distribution = _write_fake_repository(repository)
    monkeypatch.setattr(
        "decision_agent_bench.release._git_release_state", lambda _repository: _clean_state()
    )
    bundle = tmp_path / "bundle"
    assemble_release_bundle(repository, distribution, bundle, allow_prerelease=True)
    (bundle / "research/articles/one.md").unlink()

    missing = verify_release_bundle(bundle)
    absent = verify_release_bundle(tmp_path / "absent")
    (bundle / "release-manifest.json").write_text("not json\n", encoding="utf-8")
    malformed = verify_release_bundle(bundle)

    assert missing["verified"] is False
    assert "missing file: research/articles/one.md" in missing["issues"]
    assert absent["issues"] == ["release manifest is missing"]
    assert malformed["verified"] is False
    assert malformed["issues"][0].startswith("release manifest is invalid JSON:")


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


def test_stable_version_preview_bundle_verifies_without_final_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    distribution = _write_fake_repository(repository, version="1.0.0")
    monkeypatch.setattr(
        "decision_agent_bench.release._git_release_state",
        lambda _repository: {**_clean_state("1.0.0"), "tags": []},
    )

    manifest = assemble_release_bundle(
        repository,
        distribution,
        tmp_path / "bundle",
        allow_prerelease=True,
    )
    verified = verify_release_bundle(tmp_path / "bundle")

    assert manifest["prerelease"] is False
    assert manifest["release_mode"] == "preview"
    assert verified["verified"] is True


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
        lambda _repository, image, runtime: {
            "status": "pass",
            "image": image,
            "runtime": runtime,
        },
    )
    sbom = tmp_path / "sbom.json"
    sbom.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "components": [{"name": "inspect-ai", "version": "0.3.247"}],
            }
        ),
        encoding="utf-8",
    )
    dependency_report = tmp_path / "pip-audit.json"
    dependency_report.write_text(
        json.dumps(
            {
                "dependencies": [
                    {"name": "inspect-ai", "version": "0.3.247", "vulns": []}
                ]
            }
        ),
        encoding="utf-8",
    )
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
    assert manifest["release_mode"] == "final"
    assert verified["verified"] is True
    assert verified["artifact_count"] == 30

    result_path = tmp_path / "bundle/results/primary" / ANALYSIS_ARTIFACTS[0]
    result_path.write_text("outer manifest was recomputed\n", encoding="utf-8")
    _resign_outer_bundle(tmp_path / "bundle")
    semantic_tamper = verify_release_bundle(tmp_path / "bundle")
    assert semantic_tamper["verified"] is False
    assert any(
        issue.startswith("analysis bundle primary:")
        for issue in semantic_tamper["issues"]
    )


def test_final_release_rejects_unbound_sbom_and_dependency_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    distribution = _write_fake_repository(repository, version="1.0.0")
    monkeypatch.setattr(
        "decision_agent_bench.release._git_release_state",
        lambda _repository: _clean_state("1.0.0"),
    )
    sbom = tmp_path / "sbom.json"
    sbom.write_text(
        json.dumps({"bomFormat": "CycloneDX", "components": []}), encoding="utf-8"
    )
    dependency_report = tmp_path / "pip-audit.json"
    dependency_report.write_text(json.dumps({"dependencies": []}), encoding="utf-8")

    with pytest.raises(ValueError, match=r"SBOM does not cover requirements\.lock"):
        assemble_release_bundle(
            repository,
            distribution,
            tmp_path / "bad-sbom",
            sbom_path=sbom,
            dependency_report=dependency_report,
            container_image="image",
        )

    sbom.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "components": [{"name": "inspect-ai", "version": "0.3.247"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"dependency audit does not cover requirements\.lock"):
        assemble_release_bundle(
            repository,
            distribution,
            tmp_path / "bad-audit",
            sbom_path=sbom,
            dependency_report=dependency_report,
            container_image="image",
        )


def test_verifier_recomputes_security_and_benchmark_semantics_after_resigning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    distribution = _write_fake_repository(repository)
    monkeypatch.setattr(
        "decision_agent_bench.release._git_release_state", lambda _repository: _clean_state()
    )
    sbom = tmp_path / "sbom.json"
    sbom.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "components": [{"name": "inspect-ai", "version": "0.3.247"}],
            }
        ),
        encoding="utf-8",
    )
    dependency_report = tmp_path / "pip-audit.json"
    dependency_report.write_text(
        json.dumps(
            {
                "dependencies": [
                    {"name": "inspect-ai", "version": "0.3.247", "vulns": []}
                ]
            }
        ),
        encoding="utf-8",
    )
    bundle = tmp_path / "bundle"
    assemble_release_bundle(
        repository,
        distribution,
        bundle,
        sbom_path=sbom,
        dependency_report=dependency_report,
        allow_prerelease=True,
    )

    (bundle / "metadata/sbom.cdx.json").write_text(
        json.dumps({"bomFormat": "CycloneDX", "components": []}), encoding="utf-8"
    )
    (bundle / "metadata/pip-audit.json").write_text(
        json.dumps({"dependencies": []}), encoding="utf-8"
    )
    (bundle / "data/task-instances-v0.2.json").write_text("[]\n", encoding="utf-8")
    _resign_outer_bundle(bundle)

    report = verify_release_bundle(bundle)

    assert report["verified"] is False
    assert "release benchmark summary does not match bundled data" in report["issues"]
    assert any(issue.startswith("SBOM inventory: missing") for issue in report["issues"])
    assert any(
        issue.startswith("dependency inventory: missing") for issue in report["issues"]
    )


def test_release_rejects_unreviewed_vulnerability_even_with_complete_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    distribution = _write_fake_repository(repository)
    monkeypatch.setattr(
        "decision_agent_bench.release._git_release_state", lambda _repository: _clean_state()
    )
    report = tmp_path / "pip-audit.json"
    report.write_text(
        json.dumps(
            {
                "dependencies": [
                    {
                        "name": "inspect-ai",
                        "version": "0.3.247",
                        "vulns": [{"id": "CVE-2099-0001", "aliases": []}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="without current OpenVEX coverage"):
        assemble_release_bundle(
            repository,
            distribution,
            tmp_path / "bundle",
            dependency_report=report,
            allow_prerelease=True,
        )
