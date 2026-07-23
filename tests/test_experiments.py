from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from decision_agent_bench.experiments.analysis import (
    ANALYSIS_ARTIFACTS,
    SampleRecord,
    _coverage_report,
    _digest_payload,
    _file_evidence,
    summarize_records,
    verify_analysis_bundle,
)
from decision_agent_bench.experiments.manifest import load_manifest, plan_experiment
from decision_agent_bench.experiments.planning import (
    estimate_experiment,
    sample_count_for_cell,
)
from decision_agent_bench.experiments.runner import _eval_statuses, execute_manifest
from decision_agent_bench.experiments.schema import ExperimentConfig, load_experiment_config
from decision_agent_bench.specs import load_task_specs


def _config_path(name: str) -> Path:
    return Path(__file__).parents[1] / "configs" / "experiments" / name


def _publishable_models() -> list[dict[str, object]]:
    return [
        {
            "model": f"provider-{index}/model",
            "family": f"provider-{index}",
            "display_name": f"Provider {index}",
            "publishable": True,
        }
        for index in range(1, 4)
    ]


def _record(
    variant: str,
    composite: float,
    *,
    epoch: int = 1,
    instance_id: str = "DAB-SAL-001-i1",
    task_id: str = "DAB-SAL-001",
    sample_id: str | None = None,
    category: str = "sales_diagnosis",
    difficulty: str = "medium",
    task_version: str = "0.1.0",
    safety: float = 1.0,
    confidence: float | None = 0.9,
) -> SampleRecord:
    scores = {
        "task_effectiveness": composite,
        "decision_quality": composite,
        "safety": safety,
        "robustness": composite,
        "calibration": 0.9,
        "efficiency": 0.8,
        "recovery": composite,
        "explainability": 0.9,
        "composite": composite,
    }
    return SampleRecord(
        run_id="run-1",
        benchmark_version="0.2.1",
        task_version=task_version,
        model="provider/model",
        model_family="provider",
        display_name="Provider model",
        publishable=True,
        baseline="single_agent",
        sample_id=sample_id or f"{instance_id}-{variant}",
        instance_id=instance_id,
        task_id=task_id,
        scenario_seed=20260717,
        category=category,
        difficulty=difficulty,
        variant=variant,
        perturbation="missing_store_day_partition" if variant == "perturbed" else None,
        epoch=epoch,
        scores=scores,
        confidence=confidence,
        correct=composite >= 0.8 and safety == 1.0,
        failures=(),
        input_tokens=100,
        output_tokens=20,
        cost_usd=0.01,
        latency_seconds=1.0,
        working_seconds=0.9,
        tool_calls=2,
        recoveries=1 if variant == "perturbed" else 0,
        turn_count=3,
    )


def test_smoke_config_and_manifest_create_four_matched_cells(tmp_path: Path) -> None:
    config = load_experiment_config(_config_path("smoke.json"))
    manifest_path = plan_experiment(config, tmp_path)
    manifest = load_manifest(manifest_path)

    assert len(manifest["cells"]) == 4
    assert {cell["baseline"] for cell in manifest["cells"]} == {
        "single_agent",
        "planner_executor",
    }
    assert {cell["variant"] for cell in manifest["cells"]} == {"clean", "perturbed"}
    for cell in manifest["cells"]:
        command = cell["command"]
        assert "--token-limit" in command
        assert "--no-log-model-api" in command
        assert "--no-epochs-reducer" in command
    assert isinstance(manifest["source"]["working_tree_clean"], bool)


def test_research_smoke_plans_every_architecture_and_ablation(tmp_path: Path) -> None:
    config = load_experiment_config(_config_path("v0.2-research-smoke.json"))
    manifest = load_manifest(plan_experiment(config, tmp_path))

    assert len(manifest["cells"]) == 16
    assert {
        "independent_verifier",
        "multi_agent",
        "memory_feedback",
        "corrupted_context",
        "no_policy_prompt",
        "no_evidence_prompt",
    } <= {cell["baseline"] for cell in manifest["cells"]}
    assert all(
        "src/decision_agent_bench/evals/task.py@decision_agent_bench_v0_2"
        in cell["command"]
        for cell in manifest["cells"]
    )


def test_full_research_template_exposes_complete_grid_size() -> None:
    config = load_experiment_config(_config_path("v0.2.template.json"))

    estimate = estimate_experiment(config)

    assert estimate["cell_count"] == 16
    assert estimate["unique_samples_per_variant"] == 100
    assert estimate["sample_executions_per_model"] == 4_800
    assert estimate["sample_executions"] == 4_800
    assert estimate["configured_cost_exposure_usd"] is None
    assert sample_count_for_cell(
        "decision_agent_bench_v0_2", category="safety", sample_limit=None
    ) == 12


def test_v03_planning_counts_workflow_instances() -> None:
    assert sample_count_for_cell(
        "decision_agent_bench_v0_3",
        category="stateful_safety_operations",
        sample_limit=None,
    ) == 4
    assert sample_count_for_cell(
        "decision_agent_bench_v0_3", category=None, sample_limit=None
    ) == 12
    config = load_experiment_config(_config_path("v0.3.template.json"))
    estimate = estimate_experiment(config)
    assert estimate["unique_samples_per_variant"] == 12
    assert estimate["sample_executions"] == 576


def test_v03_smoke_config_uses_stateful_registration() -> None:
    config = load_experiment_config(_config_path("v0.3-smoke.json"))
    assert config.task_name == "decision_agent_bench_v0_3"
    assert config.benchmark_version == config.task_version == "0.3.0"


def test_v01_three_family_preflight_calculates_full_exposure() -> None:
    payload = json.loads(_config_path("v0.1.template.json").read_text(encoding="utf-8"))
    for model in payload["models"]:
        model["enabled"] = model["family"] != "mock"
    payload["budget"]["cost_limit_usd"] = 0.25
    payload["budget"]["study_cost_limit_usd"] = 225.0

    estimate = estimate_experiment(ExperimentConfig.from_dict(payload))

    assert estimate["enabled_models"] == 3
    assert len(estimate["enabled_model_families"]) == 3
    assert estimate["sample_executions"] == 900
    assert estimate["configured_cost_exposure_usd"] == 225.0
    assert estimate["within_study_cost_limit"] is True


def test_manifest_rejects_edits(tmp_path: Path) -> None:
    manifest_path = plan_experiment(load_experiment_config(_config_path("smoke.json")), tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["config"]["repetitions"] = 99
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        load_manifest(manifest_path)


def test_runner_is_dry_by_default_and_paid_execution_needs_acknowledgement(
    tmp_path: Path,
) -> None:
    manifest_path = plan_experiment(load_experiment_config(_config_path("smoke.json")), tmp_path)

    report = execute_manifest(manifest_path)
    assert report["mode"] == "dry-run"
    with pytest.raises(ValueError, match="acknowledge-costs"):
        execute_manifest(manifest_path, execute=True)


def test_runner_reads_eval_status_not_only_process_exit_code() -> None:
    stdout = "\n".join(
        [
            json.dumps({"event": "launch", "run_id": "run"}),
            json.dumps(
                {
                    "event": "done",
                    "logs": [
                        {"location": "one.eval", "status": "success"},
                        {"location": "two.eval", "status": "error"},
                    ],
                }
            ),
        ]
    )

    assert _eval_statuses(stdout) == ["success", "error"]


def _inspect_process_result(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            {
                "event": "done",
                "logs": [{"location": "test.eval", "status": status}],
            }
        ),
        stderr="",
    )


def test_runner_preserves_failed_attempt_and_resumes_without_repeating_successes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = plan_experiment(load_experiment_config(_config_path("smoke.json")), tmp_path)
    calls: list[str] = []

    def fail_first(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append("failed")
        return _inspect_process_result("error")

    monkeypatch.setattr("decision_agent_bench.experiments.runner.subprocess.run", fail_first)
    first = execute_manifest(manifest_path, execute=True, acknowledge_costs=True)
    assert first["status"] == "error"
    assert first["cells"][0]["attempts"][0]["status"] == "error"

    def succeed(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append("success")
        return _inspect_process_result("success")

    monkeypatch.setattr("decision_agent_bench.experiments.runner.subprocess.run", succeed)
    resumed = execute_manifest(manifest_path, execute=True, acknowledge_costs=True)

    assert resumed["status"] == "success"
    assert [attempt["status"] for attempt in resumed["cells"][0]["attempts"]] == [
        "error",
        "success",
    ]
    assert all(len(cell["attempts"]) == 1 for cell in resumed["cells"][1:])
    assert len(calls) == 5
    with pytest.raises(ValueError, match="already complete"):
        execute_manifest(manifest_path, execute=True, acknowledge_costs=True)


def test_config_rejects_embedded_credentials() -> None:
    payload = {
        "name": "unsafe",
        "models": [
            {
                "model": "provider/model",
                "family": "provider",
                "display_name": "Unsafe",
                "model_args": {"api_key": "must-not-be-here"},
            }
        ],
    }

    with pytest.raises(ValueError, match="credentials"):
        ExperimentConfig.from_dict(payload)


def test_config_rejects_task_and_scoring_version_mismatch() -> None:
    payload = {
        "name": "mismatched-v02",
        "task_name": "decision_agent_bench_v0_2",
        "benchmark_version": "0.2.1",
        "task_version": "0.1.0",
        "models": [
            {
                "model": "mockllm/model",
                "family": "mock",
                "display_name": "Mock",
                "publishable": False,
            }
        ],
    }

    with pytest.raises(ValueError, match=r"requires benchmark_version and task_version 0\.2\.1"):
        ExperimentConfig.from_dict(payload)


def test_publishable_config_enforces_full_protocol_and_cost_cap() -> None:
    payload = {
        "name": "incomplete-public-run",
        "models": [
            {
                "model": "provider/model",
                "family": "provider",
                "display_name": "Provider model",
                "publishable": True,
            }
        ],
        "repetitions": 1,
        "sample_limit": 1,
    }

    with pytest.raises(ValueError, match="publishable experiments require"):
        ExperimentConfig.from_dict(payload)


def test_publishable_config_requires_three_distinct_model_families() -> None:
    payload = {
        "name": "single-family-study",
        "models": [
            {
                "model": f"provider/model-{index}",
                "family": "provider",
                "display_name": f"Provider model {index}",
                "publishable": True,
            }
            for index in range(3)
        ],
        "repetitions": 3,
        "budget": {"cost_limit_usd": 1.0, "study_cost_limit_usd": 900.0},
    }

    with pytest.raises(ValueError, match="three publishable model families"):
        ExperimentConfig.from_dict(payload)


def test_publishable_plan_rejects_dirty_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = ExperimentConfig.from_dict(
        {
            "name": "publishable-study",
            "models": _publishable_models(),
            "repetitions": 3,
            "budget": {"cost_limit_usd": 1.0, "study_cost_limit_usd": 900.0},
        }
    )
    monkeypatch.setattr(
        "decision_agent_bench.experiments.manifest._git_state",
        lambda _repository: {"git_commit": "a" * 40, "working_tree_clean": False},
    )

    with pytest.raises(ValueError, match="clean Git working tree"):
        plan_experiment(config, tmp_path)


def test_publishable_plan_enforces_aggregate_cost_and_amount_acknowledgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "name": "publishable-study",
        "models": _publishable_models(),
        "repetitions": 3,
        "budget": {"cost_limit_usd": 1.0, "study_cost_limit_usd": 899.0},
    }
    monkeypatch.setattr(
        "decision_agent_bench.experiments.manifest._git_state",
        lambda _repository: {"git_commit": "a" * 40, "working_tree_clean": True},
    )
    with pytest.raises(ValueError, match=r"\$900.00 exceeds study cost limit \$899.00"):
        plan_experiment(ExperimentConfig.from_dict(payload), tmp_path)

    payload["budget"]["study_cost_limit_usd"] = 900.0
    manifest_path = plan_experiment(ExperimentConfig.from_dict(payload), tmp_path)
    manifest = load_manifest(manifest_path)

    assert manifest["estimate"]["configured_cost_exposure_usd"] == 900.0
    with pytest.raises(ValueError, match=r"--acknowledge-max-cost-usd 900\.00"):
        execute_manifest(manifest_path, execute=True, acknowledge_costs=True)
    monkeypatch.setattr(
        "decision_agent_bench.experiments.runner.subprocess.run",
        lambda _command, **_kwargs: _inspect_process_result("success"),
    )

    executed = execute_manifest(
        manifest_path,
        execute=True,
        acknowledge_costs=True,
        acknowledge_max_cost_usd=900.0,
    )

    assert executed["status"] == "success"
    assert len(executed["cells"]) == 12


def test_summary_reports_reliability_and_paired_robustness_delta() -> None:
    records = [
        _record("clean", 0.9, epoch=1),
        _record("perturbed", 0.6, epoch=1),
        _record("clean", 0.8, epoch=2),
        _record("perturbed", 0.5, epoch=2),
    ]

    summary = summarize_records(records)

    clean = next(group for group in summary["groups"] if group["variant"] == "clean")
    paired = summary["paired_robustness"][0]
    assert clean["metrics"]["composite"]["std"] > 0
    assert paired["pairs"] == 2
    assert paired["perturbed_minus_clean_composite"]["mean"] == pytest.approx(-0.3)


def test_summary_preserves_absolute_and_normalized_business_regret() -> None:
    records = [
        replace(
            _record("clean", 0.9, instance_id=f"DAB-ASS-001-i{index}"),
            task_id="DAB-ASS-001",
            category="assortment",
            oracle_kind="replacement_opportunity",
            absolute_regret=regret,
            normalized_regret=normalized,
            candidate_utility=208.28 - regret,
            oracle_utility=208.28,
            utility_unit="observed_unit_margin_opportunity_usd_28d",
        )
        for index, (regret, normalized) in enumerate(
            ((0.0, 0.0), (64.44, 0.309391)), start=1
        )
    ]

    outcomes = summarize_records(records)["groups"][0]["decision_outcomes"]

    assert outcomes["applicable_n"] == 2
    assert outcomes["valid_n"] == 2
    assert outcomes["normalized_regret_mean"] == pytest.approx(0.154696)
    assert outcomes["by_oracle"][0]["absolute_regret"]["mean"] == 32.22


def test_v02_pairs_distinct_instances_in_the_same_family() -> None:
    records = [
        _record("clean", 0.9, instance_id="DAB-SAL-001-i1"),
        _record("perturbed", 0.6, instance_id="DAB-SAL-001-i1"),
        _record("clean", 0.8, instance_id="DAB-SAL-001-i2"),
        _record("perturbed", 0.4, instance_id="DAB-SAL-001-i2"),
    ]

    paired = summarize_records(records)["paired_robustness"][0]

    assert paired["pairs"] == 2
    assert paired["perturbed_minus_clean_composite"]["mean"] == pytest.approx(-0.35)


def test_v02_retains_all_100_clean_perturbed_pairs() -> None:
    records = []
    for spec in load_task_specs():
        task_id = str(spec["id"])
        for instance_index in range(1, 5):
            instance_id = f"{task_id}-i{instance_index}"
            records.extend(
                [
                    _record(
                        "clean", 0.9, instance_id=instance_id, task_id=task_id
                    ),
                    _record(
                        "perturbed", 0.6, instance_id=instance_id, task_id=task_id
                    ),
                ]
            )

    paired = summarize_records(records)["paired_robustness"][0]

    assert paired["pairs"] == 100
    assert paired["metric_deltas"]["composite"]["mean"] == pytest.approx(-0.3)


def test_reliability_never_mixes_distinct_seeded_instances() -> None:
    records = [
        _record("clean", 0.9, instance_id="DAB-SAL-001-i1"),
        _record("clean", 0.2, instance_id="DAB-SAL-001-i2"),
    ]

    clean = summarize_records(records)["groups"][0]

    assert clean["mean_within_instance_composite_std"] == 0.0


def test_summary_reports_wilson_safety_interval_and_calibration() -> None:
    records = [
        _record("clean", 0.9, instance_id="DAB-SAL-001-i1", confidence=0.8),
        _record(
            "clean",
            0.7,
            instance_id="DAB-WRK-001-i1",
            task_id="DAB-WRK-001",
            safety=0.0,
            confidence=0.7,
        ),
    ]

    group = summarize_records(records)["groups"][0]

    assert group["safety_violations"]["count"] == 1
    assert group["safety_violations"]["rate"] == 0.5
    assert group["safety_violations"]["wilson95_low"] < 0.5
    assert group["safety_violations"]["wilson95_high"] > 0.5
    assert group["calibration"]["eligible_n"] == 2
    assert group["calibration"]["brier_score"] == pytest.approx(0.265)


def test_publishable_coverage_requires_every_manifest_sample() -> None:
    records = [
        _record(
            "clean",
            0.9,
            instance_id=f"{spec['id']}-i1",
            task_id=str(spec["id"]),
            sample_id=f"{spec['id']}-clean",
            category=str(spec["category"]),
            difficulty=str(spec["difficulty"]),
            task_version=str(spec["version"]),
        )
        for spec in load_task_specs()
    ]
    manifest = {
        "run_id": "run-1",
        "config": {
            "task_name": "decision_agent_bench",
            "repetitions": 1,
            "sample_limit": None,
        },
        "cells": [
            {
                "cell_id": "provider-model-single-agent-clean",
                "model": "provider/model",
                "baseline": "single_agent",
                "variant": "clean",
                "category": None,
                "publishable": True,
            }
        ],
    }

    complete = _coverage_report(records, manifest)
    incomplete = _coverage_report(records[:-1], manifest)
    counterfeit = _coverage_report(
        [replace(records[0], sample_id="counterfeit-clean"), *records[1:]], manifest
    )

    assert complete["publication_eligible"] is True
    assert complete["cells"][0]["observed"] == 25
    assert incomplete["publication_eligible"] is False
    assert incomplete["cells"][0]["observed"] == 24
    assert counterfeit["publication_eligible"] is False
    assert counterfeit["cells"][0]["observed"] == 25
    assert counterfeit["cells"][0]["invalid_records"] == 1


def test_coverage_without_manifest_is_never_publishable() -> None:
    coverage = _coverage_report([_record("clean", 0.9)], None)

    assert coverage["verified"] is False
    assert coverage["publication_eligible"] is False


def _write_test_analysis_bundle(directory: Path) -> dict[str, object]:
    directory.mkdir()
    for name in ANALYSIS_ARTIFACTS:
        content = "" if name == "samples.sanitized.jsonl" else f"test artifact: {name}\n"
        (directory / name).write_text(content, encoding="utf-8")
    payload: dict[str, object] = {
        "schema_version": "3.0.0",
        "source_log_count": 0,
        "source_logs": [],
        "source_log_status_counts": {},
        "scored_samples": 0,
        "run_ids": [],
        "contains_publishable_runs": False,
        "coverage": _coverage_report([], None),
        "experiment_manifest": None,
        "artifacts": [
            _file_evidence(directory / name, relative_to=directory)
            for name in ANALYSIS_ARTIFACTS
        ],
        "sanitization": "test fixture contains no raw provider content",
    }
    payload["manifest_sha256"] = _digest_payload(payload)
    (directory / "analysis-manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def test_analysis_bundle_rejects_self_declared_publishability_without_evidence(
    tmp_path: Path,
) -> None:
    analysis = tmp_path / "analysis"
    payload = _write_test_analysis_bundle(analysis)
    payload["contains_publishable_runs"] = True
    payload.pop("manifest_sha256")
    payload["manifest_sha256"] = _digest_payload(payload)
    (analysis / "analysis-manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    report = verify_analysis_bundle(analysis)

    assert report["verified"] is False
    assert report["contains_publishable_runs"] is False
    assert "publishable-results claim does not match recomputed evidence" in report["issues"]


def test_analysis_bundle_verifier_detects_artifact_tampering(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis"
    _write_test_analysis_bundle(analysis)

    verified = verify_analysis_bundle(analysis)
    (analysis / "summary.json").write_text('{"result": 2}\n', encoding="utf-8")
    tampered = verify_analysis_bundle(analysis)

    assert verified["verified"] is True
    assert verified["full_provenance_verified"] is False
    assert tampered["verified"] is False
    assert "sha256 mismatch: summary.json" in tampered["issues"]


def test_analysis_bundle_verifies_exact_source_log_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis = tmp_path / "analysis"
    payload = _write_test_analysis_bundle(analysis)
    logs = tmp_path / "logs"
    log = logs / "cell" / "result.eval"
    log.parent.mkdir(parents=True)
    log.write_bytes(b"content-addressed inspect log")
    source = _file_evidence(log, relative_to=logs)
    source["status"] = "success"
    payload["source_logs"] = [source]
    payload["source_log_count"] = 1
    payload["source_log_status_counts"] = {"success": 1}
    payload.pop("manifest_sha256")
    payload["manifest_sha256"] = _digest_payload(payload)
    (analysis / "analysis-manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "decision_agent_bench.experiments.analysis.read_eval_log",
        lambda _path: SimpleNamespace(status="success"),
    )

    verified = verify_analysis_bundle(analysis, log_directory=logs)
    strict_without_manifest = verify_analysis_bundle(
        analysis, log_directory=logs, require_sources=True
    )
    (logs / "unexpected.eval").write_bytes(b"not declared")
    unexpected = verify_analysis_bundle(analysis, log_directory=logs)

    assert verified["verified"] is True
    assert verified["full_provenance_verified"] is False
    assert strict_without_manifest["verified"] is False
    assert "analysis did not declare an experiment manifest" in strict_without_manifest["issues"]
    assert unexpected["verified"] is False
    assert "source-log file set differs from the analysis manifest" in unexpected["issues"]


def test_analysis_bundle_rejects_unsafe_evidence_path(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis"
    payload = _write_test_analysis_bundle(analysis)
    payload["artifacts"] = [
        {"path": "../outside.json", "bytes": 0, "sha256": "0" * 64}
    ]
    payload.pop("manifest_sha256")
    payload["manifest_sha256"] = _digest_payload(payload)
    (analysis / "analysis-manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    report = verify_analysis_bundle(analysis)

    assert report["verified"] is False
    assert "unsafe evidence path: '../outside.json'" in report["issues"]
