"""Deterministic archival release assembly and verification."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decision_agent_bench.experiments.analysis import verify_analysis_bundle
from decision_agent_bench.integrity import (
    digest_payload,
    file_evidence,
    sha256_file,
    verify_evidence_files,
    verify_pip_audit_inventory,
    verify_sbom_inventory,
)

RELEASE_MANIFEST = "release-manifest.json"
CHECKSUMS = "SHA256SUMS"


@dataclass(frozen=True)
class ReleaseAsset:
    """One source file and its portable release-bundle destination."""

    source: Path
    destination: str
    role: str
    media_type: str


def _project_version(repository: Path) -> str:
    payload = tomllib.loads((repository / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def _git_release_state(repository: Path) -> dict[str, Any]:
    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    timestamp = run("show", "-s", "--format=%cI", "HEAD")
    tags = run("tag", "--points-at", "HEAD")
    return {
        "git_commit": commit.stdout.strip() if commit.returncode == 0 else "unknown",
        "working_tree_clean": status.returncode == 0 and not status.stdout.strip(),
        "commit_timestamp": timestamp.stdout.strip() if timestamp.returncode == 0 else None,
        "tags": (
            sorted(tag for tag in tags.stdout.splitlines() if tag)
            if tags.returncode == 0
            else []
        ),
    }


def _container_provenance(repository: Path, image: str | None) -> dict[str, Any]:
    if image is None:
        return {"status": "not_supplied", "image": None}

    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", *arguments], check=False, capture_output=True, text=True
        )

    inspection = run("image", "inspect", image)
    verification = run("run", "--rm", image)
    identity = run("run", "--rm", "--entrypoint", "id", image)
    issues = []
    image_payload: list[dict[str, Any]] = []
    if inspection.returncode == 0:
        image_payload = json.loads(inspection.stdout)
    else:
        issues.append("image inspection failed")
    reference_digest = json.loads(
        (repository / "data/reference-world-manifest.json").read_text(encoding="utf-8")
    )["logical_sha256"]
    if verification.returncode or reference_digest not in verification.stdout:
        issues.append("reference-world verification failed")
    if identity.returncode or "uid=10001(benchmark)" not in identity.stdout:
        issues.append("container did not run as the benchmark user")
    inspected = image_payload[0] if image_payload else {}
    return {
        "status": "fail" if issues else "pass",
        "image": image,
        "image_id": inspected.get("Id"),
        "repo_digests": sorted(inspected.get("RepoDigests") or []),
        "runtime_user": identity.stdout.strip(),
        "verification_output": verification.stdout.strip(),
        "dockerfile_sha256": sha256_file(repository / "Dockerfile"),
        "issues": issues,
    }


def _validate_sbom(path: Path | None, lock_path: Path) -> None:
    if path is None:
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("bomFormat") != "CycloneDX" or not isinstance(
        payload.get("components"), list
    ):
        raise ValueError("SBOM must be a CycloneDX JSON document with components")
    inventory = verify_sbom_inventory(lock_path, payload)
    if not inventory["verified"]:
        raise ValueError("SBOM does not cover requirements.lock: " + "; ".join(inventory["issues"]))


def _validate_dependency_report(path: Path | None, lock_path: Path) -> None:
    if path is None:
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("dependencies"), list):
        raise ValueError("dependency report must be pip-audit JSON")
    inventory = verify_pip_audit_inventory(lock_path, payload)
    if not inventory["verified"]:
        raise ValueError(
            "dependency audit does not cover requirements.lock: "
            + "; ".join(inventory["issues"])
        )


def _base_assets(
    repository: Path,
    distribution_directory: Path,
    version: str,
    *,
    sbom_path: Path | None,
    dependency_report: Path | None,
) -> list[ReleaseAsset]:
    wheels = sorted(distribution_directory.glob(f"decision_agent_bench-{version}-*.whl"))
    source = distribution_directory / f"decision_agent_bench-{version}.tar.gz"
    if len(wheels) != 1 or not source.is_file():
        raise ValueError("dist must contain exactly one matching wheel and source distribution")
    assets = [
        ReleaseAsset(wheels[0], f"packages/{wheels[0].name}", "python-wheel", "application/zip"),
        ReleaseAsset(source, f"packages/{source.name}", "source-distribution", "application/gzip"),
        ReleaseAsset(
            repository / "data/task_specs/v0.1.json",
            "data/task-specs-v0.1.json",
            "benchmark-dataset",
            "application/json",
        ),
        ReleaseAsset(
            repository / "data/task_specs/v0.2-instances.json",
            "data/task-instances-v0.2.json",
            "benchmark-dataset",
            "application/json",
        ),
        ReleaseAsset(
            repository / "data/reference-world-manifest.json",
            "data/reference-world-manifest.json",
            "dataset-provenance",
            "application/json",
        ),
        ReleaseAsset(
            repository / "report/technical-report.md",
            "research/technical-report.md",
            "technical-report",
            "text/markdown",
        ),
        ReleaseAsset(
            repository / "talk/decision-agent-bench-research-talk.pptx",
            "research/decision-agent-bench-research-talk.pptx",
            "presentation",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        ReleaseAsset(
            repository / "docs/assets/social-preview.png",
            "media/social-preview.png",
            "social-preview",
            "image/png",
        ),
        ReleaseAsset(repository / "CITATION.cff", "metadata/CITATION.cff", "citation", "text/yaml"),
        ReleaseAsset(
            repository / ".zenodo.json",
            "metadata/zenodo.json",
            "archive",
            "application/json",
        ),
        ReleaseAsset(repository / "LICENSE", "metadata/LICENSE", "license", "text/plain"),
        ReleaseAsset(
            repository / "security/openvex.json",
            "metadata/openvex.json",
            "vulnerability-disposition",
            "application/vnd.openvex+json",
        ),
        ReleaseAsset(
            repository / "requirements.lock",
            "metadata/requirements.lock",
            "dependency-lock",
            "text/plain",
        ),
    ]
    for article in sorted((repository / "articles").glob("*.md")):
        assets.append(
            ReleaseAsset(article, f"research/articles/{article.name}", "article", "text/markdown")
        )
    if sbom_path is not None:
        assets.append(
            ReleaseAsset(
                sbom_path,
                "metadata/sbom.cdx.json",
                "software-bill-of-materials",
                "application/vnd.cyclonedx+json",
            )
        )
    if dependency_report is not None:
        assets.append(
            ReleaseAsset(
                dependency_report,
                "metadata/pip-audit.json",
                "vulnerability-scan",
                "application/json",
            )
        )
    return assets


def _analysis_assets(directories: tuple[Path, ...]) -> tuple[list[ReleaseAsset], bool]:
    assets: list[ReleaseAsset] = []
    contains_publishable = False
    names: set[str] = set()
    for directory in directories:
        report = verify_analysis_bundle(directory)
        if not report["verified"]:
            raise ValueError(f"analysis bundle failed verification: {directory}")
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", directory.name).strip("-")
        if not name or name in names:
            raise ValueError("analysis bundle names must be unique and portable")
        names.add(name)
        manifest = json.loads((directory / "analysis-manifest.json").read_text(encoding="utf-8"))
        contains_publishable = contains_publishable or bool(
            manifest.get("contains_publishable_runs")
        )
        for path in sorted(directory.iterdir()):
            if path.is_file():
                media_type = "application/json" if path.suffix == ".json" else "text/plain"
                assets.append(
                    ReleaseAsset(path, f"results/{name}/{path.name}", "analysis-result", media_type)
                )
    return assets, contains_publishable


def assemble_release_bundle(
    repository: Path,
    distribution_directory: Path,
    output_directory: Path,
    *,
    sbom_path: Path | None = None,
    dependency_report: Path | None = None,
    container_image: str | None = None,
    analysis_directories: tuple[Path, ...] = (),
    allow_prerelease: bool = False,
) -> dict[str, Any]:
    """Assemble an exact content-addressed release directory."""

    repository = repository.resolve()
    distribution_directory = distribution_directory.resolve()
    output_directory = output_directory.resolve()
    version = _project_version(repository)
    prerelease = bool(re.search(r"(?:\.dev|a|b|rc)\d*", version))
    state = _git_release_state(repository)
    if not state["working_tree_clean"]:
        raise ValueError("release assembly requires a clean Git working tree")
    if prerelease and not allow_prerelease:
        raise ValueError("development or prerelease versions require --allow-prerelease")
    if not allow_prerelease and f"v{version}" not in state["tags"]:
        raise ValueError(f"final release requires tag v{version} at HEAD")
    if not allow_prerelease and (
        sbom_path is None or dependency_report is None or container_image is None
    ):
        raise ValueError("final release requires SBOM, dependency audit, and container evidence")
    lock_path = repository / "requirements.lock"
    _validate_sbom(sbom_path, lock_path)
    _validate_dependency_report(dependency_report, lock_path)
    if output_directory.exists() and any(output_directory.iterdir()):
        raise ValueError(f"release output directory is not empty: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)

    analysis_assets, contains_publishable = _analysis_assets(analysis_directories)
    if not allow_prerelease and not contains_publishable:
        raise ValueError("final release requires a verified publishable analysis bundle")
    assets = _base_assets(
        repository,
        distribution_directory,
        version,
        sbom_path=sbom_path,
        dependency_report=dependency_report,
    ) + analysis_assets
    destinations: set[str] = set()
    for asset in assets:
        if not asset.source.is_file():
            raise ValueError(f"release asset is missing: {asset.source}")
        if asset.destination in destinations:
            raise ValueError(f"duplicate release destination: {asset.destination}")
        destinations.add(asset.destination)
        destination = output_directory / asset.destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset.source, destination)

    container = _container_provenance(repository, container_image)
    if container_image is not None and container["status"] != "pass":
        raise ValueError("container provenance verification failed")
    container_path = output_directory / "metadata/container-provenance.json"
    container_path.parent.mkdir(parents=True, exist_ok=True)
    container_path.write_text(
        json.dumps(container, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    assets.append(
        ReleaseAsset(
            container_path,
            "metadata/container-provenance.json",
            "container-provenance",
            "application/json",
        )
    )

    evidence = []
    asset_lookup = {asset.destination: asset for asset in assets}
    for relative in sorted(asset_lookup):
        item = file_evidence(output_directory / relative, relative_to=output_directory)
        item.update(
            {
                "role": asset_lookup[relative].role,
                "media_type": asset_lookup[relative].media_type,
            }
        )
        evidence.append(item)
    reference = json.loads(
        (repository / "data/reference-world-manifest.json").read_text(encoding="utf-8")
    )
    v01 = json.loads((repository / "data/task_specs/v0.1.json").read_text(encoding="utf-8"))
    v02 = json.loads(
        (repository / "data/task_specs/v0.2-instances.json").read_text(encoding="utf-8")
    )
    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "project": "decision-agent-bench",
        "version": version,
        "prerelease": prerelease,
        "source": state,
        "benchmark": {
            "task_families": len(v01),
            "v0_2_instances": len(v02),
            "v0_2_paired_samples": len(v02) * 2,
            "reference_world_sha256": reference["logical_sha256"],
        },
        "contains_publishable_results": contains_publishable,
        "artifacts": evidence,
    }
    manifest["manifest_sha256"] = digest_payload(manifest)
    manifest_path = output_directory / RELEASE_MANIFEST
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksum_paths = [str(item["path"]) for item in evidence] + [RELEASE_MANIFEST]
    (output_directory / CHECKSUMS).write_text(
        "".join(
            f"{sha256_file(output_directory / relative)}  {relative}\n"
            for relative in sorted(checksum_paths)
        ),
        encoding="utf-8",
    )
    return manifest


def verify_release_bundle(directory: Path) -> dict[str, Any]:
    """Verify exact assets, manifest identity, and GNU-style checksums."""

    directory = directory.resolve()
    manifest_path = directory / RELEASE_MANIFEST
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    issues = []
    expected_manifest_digest = payload.get("manifest_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    if payload.get("schema_version") != "1.0.0":
        issues.append("unsupported release manifest schema")
    if expected_manifest_digest != digest_payload(unsigned):
        issues.append("release manifest hash mismatch")
    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        issues.append("release artifacts must be a list")
        artifacts = []
    artifact_issues, artifact_paths = verify_evidence_files(directory, artifacts)
    issues.extend(artifact_issues)
    expected_files = artifact_paths | {RELEASE_MANIFEST, CHECKSUMS}
    actual_files = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        issues.append("release file set differs from the manifest")

    expected_checksum_paths = artifact_paths | {RELEASE_MANIFEST}
    expected_checksums = {
        relative: sha256_file(directory / relative) for relative in expected_checksum_paths
    }
    observed_checksums: dict[str, str] = {}
    checksum_path = directory / CHECKSUMS
    if not checksum_path.is_file():
        issues.append("SHA256SUMS is missing")
    else:
        for line in checksum_path.read_text(encoding="utf-8").splitlines():
            parts = line.split("  ", maxsplit=1)
            if len(parts) != 2 or parts[1] in observed_checksums:
                issues.append("SHA256SUMS contains an invalid or duplicate line")
                continue
            observed_checksums[parts[1]] = parts[0]
        if observed_checksums != expected_checksums:
            issues.append("SHA256SUMS does not match release contents")
    return {
        "schema_version": "1.0.0",
        "verified": not issues,
        "version": payload.get("version"),
        "git_commit": payload.get("source", {}).get("git_commit"),
        "artifact_count": len(artifact_paths),
        "manifest_sha256": expected_manifest_digest,
        "issues": issues,
    }
