from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from decision_agent_bench.experiments.analysis import (
    SampleRecord,
    _coverage_report,
    summarize_records,
)
from decision_agent_bench.experiments.manifest import load_manifest, plan_experiment
from decision_agent_bench.experiments.runner import _eval_statuses, execute_manifest
from decision_agent_bench.experiments.schema import ExperimentConfig, load_experiment_config
from decision_agent_bench.specs import load_task_specs


def _config_path(name: str) -> Path:
    return Path(__file__).parents[1] / "configs" / "experiments" / name


def _record(
    variant: str,
    composite: float,
    *,
    epoch: int = 1,
    instance_id: str = "DAB-SAL-001-i1",
    task_id: str = "DAB-SAL-001",
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
        benchmark_version="0.2.0",
        task_version="0.1.0",
        model="provider/model",
        model_family="provider",
        display_name="Provider model",
        publishable=True,
        baseline="single_agent",
        sample_id=f"{instance_id}-{variant}",
        instance_id=instance_id,
        task_id=task_id,
        scenario_seed=20260717,
        category="sales_diagnosis",
        difficulty="medium",
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

    assert complete["publication_eligible"] is True
    assert complete["cells"][0]["observed"] == 25
    assert incomplete["publication_eligible"] is False
    assert incomplete["cells"][0]["observed"] == 24


def test_coverage_without_manifest_is_never_publishable() -> None:
    coverage = _coverage_report([_record("clean", 0.9)], None)

    assert coverage["verified"] is False
    assert coverage["publication_eligible"] is False
