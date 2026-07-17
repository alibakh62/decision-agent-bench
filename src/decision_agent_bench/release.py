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
    verify_vulnerability_dispositions,
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


def _validate_dependency_report(path: Path | None, lock_path: Path, vex_path: Path) -> None:
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
    vex_payload = json.loads(vex_path.read_text(encoding="utf-8"))
    dispositions = verify_vulnerability_dispositions(payload, vex_payload)
    if not dispositions["verified"]:
        identifiers = sorted(
            str(item["vulnerability"]) for item in dispositions["unreviewed"]
        )
        raise ValueError(
            "dependency audit contains vulnerabilities without current OpenVEX coverage: "
            + ", ".join(identifiers)
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
        contains_publishable = contains_publishable or bool(
            report.get("contains_publishable_runs")
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
    _validate_dependency_report(
        dependency_report, lock_path, repository / "security/openvex.json"
    )
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


def _load_bundle_object(path: Path, label: str, issues: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        issues.append(f"{label} is missing")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        issues.append(f"{label} is invalid JSON: {error}")
        return None
    if not isinstance(payload, dict):
        issues.append(f"{label} must be a JSON object")
        return None
    return payload


def _verify_release_semantics(
    directory: Path,
    payload: dict[str, Any],
    artifact_paths: set[str],
) -> list[str]:
    """Recompute release claims from bundled artifacts rather than trusting the manifest."""

    issues: list[str] = []
    version = payload.get("version")
    if payload.get("project") != "decision-agent-bench":
        issues.append("unexpected release project identity")
    if not isinstance(version, str) or not version:
        issues.append("release version is missing or invalid")
        version = "unknown"
    expected_prerelease = bool(re.search(r"(?:\.dev|a|b|rc)\d*", version))
    if payload.get("prerelease") is not expected_prerelease:
        issues.append("prerelease flag does not match the project version")

    source = payload.get("source")
    if not isinstance(source, dict):
        issues.append("release source metadata must be an object")
        source = {}
    commit = source.get("git_commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        issues.append("source commit must be a full lowercase Git SHA")
    if source.get("working_tree_clean") is not True:
        issues.append("release source does not attest to a clean working tree")

    package_stem = f"decision_agent_bench-{version}"
    wheel_paths = {
        path
        for path in artifact_paths
        if path.startswith(f"packages/{package_stem}-") and path.endswith(".whl")
    }
    sdist_path = f"packages/{package_stem}.tar.gz"
    required_paths = {
        "data/reference-world-manifest.json",
        "data/task-instances-v0.2.json",
        "data/task-specs-v0.1.json",
        "media/social-preview.png",
        "metadata/CITATION.cff",
        "metadata/LICENSE",
        "metadata/container-provenance.json",
        "metadata/openvex.json",
        "metadata/requirements.lock",
        "metadata/zenodo.json",
        "research/decision-agent-bench-research-talk.pptx",
        "research/technical-report.md",
        sdist_path,
    }
    missing_required = sorted(required_paths - artifact_paths)
    if missing_required:
        issues.append("required release artifacts are missing: " + ", ".join(missing_required))
    if len(wheel_paths) != 1:
        issues.append("release must contain exactly one version-matched wheel")
    article_paths = sorted(
        path
        for path in artifact_paths
        if path.startswith("research/articles/") and path.endswith(".md")
    )
    if len(article_paths) != 3:
        issues.append(f"release must contain exactly three articles, found {len(article_paths)}")

    try:
        task_families = json.loads(
            (directory / "data/task-specs-v0.1.json").read_text(encoding="utf-8")
        )
        task_instances = json.loads(
            (directory / "data/task-instances-v0.2.json").read_text(encoding="utf-8")
        )
        reference = json.loads(
            (directory / "data/reference-world-manifest.json").read_text(encoding="utf-8")
        )
        if not isinstance(task_families, list) or not isinstance(task_instances, list):
            raise ValueError("task catalogs must be JSON arrays")
        if not isinstance(reference, dict) or not isinstance(
            reference.get("logical_sha256"), str
        ):
            raise ValueError("reference manifest has no logical_sha256")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        issues.append(f"bundled benchmark metadata is invalid: {error}")
    else:
        recomputed_benchmark = {
            "task_families": len(task_families),
            "v0_2_instances": len(task_instances),
            "v0_2_paired_samples": len(task_instances) * 2,
            "reference_world_sha256": reference["logical_sha256"],
        }
        if payload.get("benchmark") != recomputed_benchmark:
            issues.append("release benchmark summary does not match bundled data")

    lock_path = directory / "metadata/requirements.lock"
    sbom_path = directory / "metadata/sbom.cdx.json"
    audit_path = directory / "metadata/pip-audit.json"
    vex_path = directory / "metadata/openvex.json"
    if sbom_path.is_file():
        sbom = _load_bundle_object(sbom_path, "CycloneDX SBOM", issues)
        if sbom is not None:
            if sbom.get("bomFormat") != "CycloneDX":
                issues.append("bundled SBOM is not CycloneDX")
            try:
                inventory = verify_sbom_inventory(lock_path, sbom)
            except (OSError, ValueError) as error:
                issues.append(f"SBOM inventory verification failed: {error}")
            else:
                issues.extend(f"SBOM inventory: {issue}" for issue in inventory["issues"])
    if audit_path.is_file():
        audit = _load_bundle_object(audit_path, "pip-audit report", issues)
        vex = _load_bundle_object(vex_path, "OpenVEX document", issues)
        if audit is not None:
            try:
                inventory = verify_pip_audit_inventory(lock_path, audit)
            except (OSError, ValueError) as error:
                issues.append(f"dependency inventory verification failed: {error}")
            else:
                issues.extend(
                    f"dependency inventory: {issue}" for issue in inventory["issues"]
                )
            if vex is not None:
                try:
                    dispositions = verify_vulnerability_dispositions(audit, vex)
                except ValueError as error:
                    issues.append(f"OpenVEX verification failed: {error}")
                else:
                    for item in dispositions["unreviewed"]:
                        issues.append(
                            "unreviewed bundled vulnerability: "
                            f"{item['package']}=={item['version']}:{item['vulnerability']}"
                        )

    result_names = sorted(
        {
            Path(path).parts[1]
            for path in artifact_paths
            if len(Path(path).parts) >= 3 and Path(path).parts[0] == "results"
        }
    )
    contains_publishable = False
    for result_name in result_names:
        result_directory = directory / "results" / result_name
        try:
            report = verify_analysis_bundle(result_directory)
            analysis_manifest = json.loads(
                (result_directory / "analysis-manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            issues.append(f"analysis bundle {result_name} is invalid: {error}")
            continue
        if not report["verified"]:
            issues.extend(
                f"analysis bundle {result_name}: {issue}" for issue in report["issues"]
            )
        if isinstance(analysis_manifest, dict):
            contains_publishable = contains_publishable or bool(
                report.get("contains_publishable_runs")
            )
        else:
            issues.append(f"analysis bundle {result_name} manifest must be an object")
    if payload.get("contains_publishable_results") is not contains_publishable:
        issues.append("publishable-results claim does not match bundled analyses")

    container = _load_bundle_object(
        directory / "metadata/container-provenance.json", "container provenance", issues
    )
    if container is not None and container.get("status") not in {"pass", "not_supplied"}:
        issues.append("container provenance has a failed or unknown status")

    if payload.get("prerelease") is False:
        for required in (sbom_path, audit_path):
            if not required.is_file():
                issues.append(f"final release is missing {required.name}")
        if container is None or container.get("status") != "pass":
            issues.append("final release lacks passing container provenance")
        if not contains_publishable:
            issues.append("final release has no verified publishable analysis")
        tags = source.get("tags")
        if not isinstance(tags, list) or f"v{version}" not in tags:
            issues.append("final release source does not attest to its matching tag")
    return issues


def verify_release_bundle(directory: Path) -> dict[str, Any]:
    """Verify exact assets, manifest identity, and GNU-style checksums."""

    directory = directory.resolve()
    manifest_path = directory / RELEASE_MANIFEST
    issues: list[str] = []
    if not manifest_path.is_file():
        return {
            "schema_version": "1.0.0",
            "verified": False,
            "version": None,
            "git_commit": None,
            "artifact_count": 0,
            "manifest_sha256": None,
            "issues": ["release manifest is missing"],
        }
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "schema_version": "1.0.0",
            "verified": False,
            "version": None,
            "git_commit": None,
            "artifact_count": 0,
            "manifest_sha256": None,
            "issues": [f"release manifest is invalid JSON: {error}"],
        }
    if not isinstance(payload, dict):
        return {
            "schema_version": "1.0.0",
            "verified": False,
            "version": None,
            "git_commit": None,
            "artifact_count": 0,
            "manifest_sha256": None,
            "issues": ["release manifest must be a JSON object"],
        }
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
    issues.extend(_verify_release_semantics(directory, payload, artifact_paths))

    expected_checksum_paths = artifact_paths | {RELEASE_MANIFEST}
    expected_checksums = {
        relative: sha256_file(directory / relative)
        for relative in expected_checksum_paths
        if (directory / relative).is_file()
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
    source_payload = payload.get("source")
    return {
        "schema_version": "1.0.0",
        "verified": not issues,
        "version": payload.get("version"),
        "git_commit": (
            source_payload.get("git_commit") if isinstance(source_payload, dict) else None
        ),
        "artifact_count": len(artifact_paths),
        "manifest_sha256": expected_manifest_digest,
        "issues": issues,
    }
