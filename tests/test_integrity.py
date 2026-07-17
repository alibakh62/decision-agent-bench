from __future__ import annotations

from pathlib import Path

from decision_agent_bench.integrity import (
    locked_requirements,
    verify_pip_audit_inventory,
    verify_sbom_inventory,
)


def _universal_lock(tmp_path: Path) -> Path:
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "core-package==1.0.0\n"
        "colorama==0.4.6 ; sys_platform == 'win32'\n"
        "numpy==2.4.6 ; python_full_version < '3.12'\n"
        "numpy==2.5.1 ; python_full_version >= '3.12'\n",
        encoding="utf-8",
    )
    return lock


def test_pip_audit_inventory_accepts_one_python_variant_and_platform_omission(
    tmp_path: Path,
) -> None:
    lock = _universal_lock(tmp_path)
    payload = {
        "dependencies": [
            {"name": "core_package", "version": "1.0.0"},
            {"name": "numpy", "version": "2.5.1"},
        ]
    }

    report = verify_pip_audit_inventory(lock, payload)

    assert report["verified"] is True
    assert report["locked_requirement_entries"] == 4
    assert report["required_packages"] == 2
    assert report["audited_packages"] == 2


def test_pip_audit_inventory_rejects_duplicate_and_unlocked_versions(tmp_path: Path) -> None:
    lock = _universal_lock(tmp_path)
    payload = {
        "dependencies": [
            {"name": "core-package", "version": "1.0.0"},
            {"name": "numpy", "version": "9.9.9"},
            {"name": "numpy", "version": "2.5.1"},
        ]
    }

    report = verify_pip_audit_inventory(lock, payload)

    assert report["verified"] is False
    assert report["duplicates"] == ["numpy"]
    assert report["version_mismatches"] == ["numpy==9.9.9"]


def test_sbom_inventory_requires_every_universal_lock_entry(tmp_path: Path) -> None:
    lock = _universal_lock(tmp_path)
    complete = {
        "components": [
            {"name": requirement["name"], "version": requirement["version"]}
            for requirement in locked_requirements(lock)
        ]
    }
    incomplete = {
        "components": [
            component
            for component in complete["components"]
            if component["version"] != "2.4.6"
        ]
    }

    assert verify_sbom_inventory(lock, complete)["verified"] is True
    report = verify_sbom_inventory(lock, incomplete)
    assert report["verified"] is False
    assert report["missing"] == ["numpy==2.4.6"]
