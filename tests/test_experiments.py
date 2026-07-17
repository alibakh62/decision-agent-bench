from __future__ import annotations

import json
from pathlib import Path

import pytest

from decision_agent_bench.experiments.analysis import SampleRecord, summarize_records
from decision_agent_bench.experiments.manifest import load_manifest, plan_experiment
from decision_agent_bench.experiments.runner import _eval_statuses, execute_manifest
from decision_agent_bench.experiments.schema import ExperimentConfig, load_experiment_config


def _config_path(name: str) -> Path:
    return Path(__file__).parents[1] / "configs" / "experiments" / name


def _record(variant: str, composite: float, *, epoch: int = 1) -> SampleRecord:
    scores = {
        "task_effectiveness": composite,
        "decision_quality": composite,
        "safety": 1.0,
        "robustness": composite,
        "calibration": 0.9,
        "efficiency": 0.8,
        "recovery": composite,
        "explainability": 0.9,
        "composite": composite,
    }
    return SampleRecord(
        run_id="run-1",
        model="provider/model",
        model_family="provider",
        display_name="Provider model",
        publishable=True,
        baseline="single_agent",
        task_id="DAB-SAL-001",
        category="sales_diagnosis",
        difficulty="medium",
        variant=variant,
        perturbation="missing_store_day_partition" if variant == "perturbed" else None,
        epoch=epoch,
        scores=scores,
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
