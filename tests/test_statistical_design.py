from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from decision_agent_bench.cli import main
from decision_agent_bench.evals.scorer import SCORE_KEYS
from decision_agent_bench.experiments.metric_dependence import (
    metric_dependence_report,
    verify_metric_dependence_report,
    write_metric_dependence_report,
)
from decision_agent_bench.experiments.power import (
    PowerDesign,
    load_power_design,
    simulate_power,
    verify_power_report,
)


def _design_path() -> Path:
    return Path(__file__).parents[1] / "configs" / "power" / "v0.5.json"


def _score_row(task_id: str, effectiveness: float, recovery: float) -> dict[str, object]:
    scores = {
        "task_effectiveness": effectiveness,
        "decision_quality": effectiveness,
        "safety": 1.0,
        "robustness": recovery,
        "calibration": 0.8,
        "efficiency": effectiveness * 0.9,
        "recovery": recovery,
        "explainability": effectiveness * 0.8,
        "composite": effectiveness * 0.85,
    }
    assert set(scores) == set(SCORE_KEYS)
    return {"task_id": task_id, "scores": scores}


def test_v05_power_design_counts_the_exact_reduced_grid() -> None:
    design = load_power_design(_design_path())

    assert design.grid.independent_family_count == 25
    assert design.grid.seeded_instance_count == 100
    assert design.grid.paired_sample_count == 200
    assert design.grid.sample_executions == 7_200
    assert design.grid.configured_cost_exposure_usd == 1_800.0
    assert len(design.contrasts) == 3
    assert sum(contrast.status == "confirmatory" for contrast in design.contrasts) == 1
    assert sum(contrast.status == "exploratory" for contrast in design.contrasts) == 2
    assert design.validity_gate.status == "blocked"


def test_power_simulation_is_deterministic_and_keeps_validity_gate_closed() -> None:
    design = load_power_design(_design_path())

    first = simulate_power(design, simulations=150)
    second = simulate_power(design, simulations=150)

    assert first == second
    assert first["grid"]["sample_executions"] == 7_200
    assert first["simulation"]["multiplicity_method"] == "single_step_max_t"
    assert all(item["effective_families_min"] == 25 for item in first["contrasts"])
    assert first["decision"]["grid_frozen"] is False
    assert first["decision"]["publication_scale_run_authorized"] is False
    assert "the upstream measurement-validity gate has not passed" in first["decision"][
        "blocking_reasons"
    ]


def test_power_report_binds_its_design_and_detects_tampering(tmp_path: Path) -> None:
    report_path = tmp_path / "power.json"
    committed_report = Path(__file__).parents[1] / "results" / "design" / "v0.5-power.json"
    shutil.copy2(committed_report, report_path)

    assert verify_power_report(report_path, _design_path())["verified"] is True
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["grid"]["task_families"] = 100
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    result = verify_power_report(report_path, _design_path())
    assert result["verified"] is False
    assert "power report digest mismatch" in result["issues"]


def test_committed_initial_design_preserves_the_underpowered_decision() -> None:
    repository = Path(__file__).parents[1]
    design = repository / "configs" / "power" / "v0.5-initial.json"
    report_path = repository / "results" / "design" / "v0.5-initial-power.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert verify_power_report(report_path, design)["verified"] is True
    assert payload["decision"]["all_confirmatory_power_gates_passed"] is False
    assert [item["power_at_smallest_effect"] for item in payload["contrasts"]] == [
        0.61725,
        0.62675,
        0.79825,
    ]


def test_power_design_rejects_an_unbudgeted_or_unknown_architecture() -> None:
    payload = json.loads(_design_path().read_text(encoding="utf-8"))
    payload["grid"]["study_cost_ceiling_usd"] = 100.0
    with pytest.raises(ValueError, match="exceeds the study cost ceiling"):
        PowerDesign.from_dict(payload)

    payload = json.loads(_design_path().read_text(encoding="utf-8"))
    payload["contrasts"][0]["treatment"] = "imaginary_architecture"
    with pytest.raises(ValueError, match="outside the grid"):
        PowerDesign.from_dict(payload)


def test_metric_dependence_reports_structural_and_empirical_overlap() -> None:
    rows = [
        _score_row("DAB-A", 0.2, 0.0),
        _score_row("DAB-A", 0.4, 0.0),
        _score_row("DAB-B", 0.6, 1.0),
        _score_row("DAB-B", 0.8, 1.0),
        _score_row("DAB-C", 0.9, 1.0),
        _score_row("DAB-C", 1.0, 1.0),
    ]

    report = metric_dependence_report(rows, draws=120)
    pair = next(
        item
        for item in report["pairs"]
        if item["left"] == "task_effectiveness" and item["right"] == "decision_quality"
    )

    assert pair["pearson"] == 1.0
    assert pair["spearman"] == 1.0
    assert pair["identical_value_rate"] == 1.0
    assert pair["high_correlation_review"] is True
    assert report["independent_task_families"] == 3
    assert len(report["structural_relationships"]) == 4


def test_metric_dependence_cli_writes_a_content_addressed_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    samples = tmp_path / "samples.sanitized.jsonl"
    samples.write_text(
        "\n".join(
            json.dumps(_score_row(task_id, effectiveness, recovery))
            for task_id, effectiveness, recovery in (
                ("DAB-A", 0.2, 0.0),
                ("DAB-B", 0.6, 1.0),
                ("DAB-C", 0.9, 1.0),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "dependence.json"

    assert (
        main(
            [
                "metric-dependence",
                str(samples),
                str(output),
                "--draws",
                "100",
            ]
        )
        == 0
    )
    capsys.readouterr()
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["source_samples"]["path"] == samples.name
    assert len(payload["report_sha256"]) == 64
    assert verify_metric_dependence_report(output, samples)["verified"] is True

    payload["sample_count"] = 999
    output.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_metric_dependence_report(output, samples)["verified"] is False


def test_metric_dependence_rejects_incomplete_score_rows(tmp_path: Path) -> None:
    samples = tmp_path / "bad.jsonl"
    samples.write_text('{"task_id":"DAB-A","scores":{"composite":1}}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid score"):
        write_metric_dependence_report(samples, tmp_path / "report.json", draws=100)


def test_statistical_inputs_reject_duplicate_json_keys(tmp_path: Path) -> None:
    design = tmp_path / "duplicate-design.json"
    design.write_text('{"schema_version":"1.0.0","schema_version":"1.0.0"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        load_power_design(design)

    samples = tmp_path / "duplicate-samples.jsonl"
    samples.write_text('{"task_id":"DAB-A","task_id":"DAB-B","scores":{}}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        write_metric_dependence_report(samples, tmp_path / "report.json", draws=100)
