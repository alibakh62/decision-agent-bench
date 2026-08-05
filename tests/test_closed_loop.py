from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from decision_agent_bench.cli import main
from decision_agent_bench.simulator import (
    BASELINES,
    CAUSAL_SCENARIOS,
    REGIMES,
    ClosedLoopConfig,
    ClosedLoopEnvironment,
    baseline_catalog,
    closed_loop_digest,
    generate_closed_loop_world,
    replay_actions,
    run_baseline,
    run_causal_scenario,
    validate_closed_loop_world,
    verify_calibration_report,
    verify_closed_loop_reference,
)
from decision_agent_bench.simulator.environment import PolicyViolation, ToolError


@pytest.fixture
def episode(tmp_path: Path) -> Path:
    return generate_closed_loop_world(
        tmp_path / "episode", ClosedLoopConfig(seed=71, horizon_days=14)
    )


def test_closed_loop_generation_is_reproducible_and_manifested(tmp_path: Path) -> None:
    config = ClosedLoopConfig(seed=20260805, horizon_days=28)
    first = generate_closed_loop_world(tmp_path / "first", config)
    second = generate_closed_loop_world(tmp_path / "second", config)
    different = generate_closed_loop_world(
        tmp_path / "different", ClosedLoopConfig(seed=20260806, horizon_days=28)
    )

    assert closed_loop_digest(first) == closed_loop_digest(second)
    assert closed_loop_digest(first) != closed_loop_digest(different)
    manifest = json.loads((first.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "0.7.0"
    assert manifest["world_contract"] == "closed_loop_retail"
    assert manifest["initial_logical_sha256"] == closed_loop_digest(first)
    assert "cl_demand_parameters" in manifest["oracle_only"]
    assert "cl_inventory" in manifest["agent_visibility"]


def test_published_closed_loop_manifest_reproduces_exactly() -> None:
    manifest = verify_closed_loop_reference()

    assert manifest["config"] == asdict(ClosedLoopConfig())
    assert manifest["world_contract"] == "closed_loop_retail"


def test_published_calibration_report_is_content_addressed() -> None:
    report = verify_calibration_report(Path("results/design/v0.7-calibration.json"))

    assert report["verified"] is True


def test_agent_sql_is_bounded_and_cannot_read_oracle_state(episode: Path) -> None:
    with ClosedLoopEnvironment(episode, row_limit=4) as environment:
        rows = environment.query_sql(
            "SELECT store_id, SUM(on_hand_units) AS units "
            "FROM cl_inventory GROUP BY store_id"
        )
        assert len(rows) == 4
        with pytest.raises(ToolError, match="access to cl_demand_parameters"):
            environment.query_sql("SELECT * FROM cl_demand_parameters")
        with pytest.raises(ToolError, match="only SELECT"):
            environment.query_sql("DELETE FROM cl_inventory")
        with pytest.raises(ToolError, match="row limit"):
            environment.query_sql("SELECT * FROM cl_inventory")


def test_same_seed_and_action_sequence_replays_exactly(tmp_path: Path) -> None:
    config = ClosedLoopConfig(seed=19, horizon_days=21, regime="heldout_demand_shift")
    actions = [
        {
            "day": 1,
            "action_type": "place_order",
            "store_id": "S001",
            "product_id": "P001",
            "cases": 6,
        },
        {
            "day": 3,
            "action_type": "change_price",
            "store_id": "S001",
            "product_id": "P001",
            "new_price": 2.56,
        },
    ]

    first = replay_actions(tmp_path / "first", config, actions)
    second = replay_actions(tmp_path / "second", config, actions)

    assert first == second
    assert first.final_digest == second.final_digest


@pytest.mark.parametrize("scenario", CAUSAL_SCENARIOS)
def test_every_published_scenario_has_a_later_causal_effect(
    tmp_path: Path, scenario: str
) -> None:
    result = run_causal_scenario(
        tmp_path / scenario,
        scenario,
        ClosedLoopConfig(seed=29, horizon_days=14),
    )

    assert result.later_state_changed is True
    assert result.outcome_a.final_digest != result.outcome_b.final_digest
    assert (
        result.gross_profit_delta_b_minus_a != 0
        or result.service_level_delta_b_minus_a != 0
    )


def test_daily_transition_couples_orders_inventory_sales_returns_and_cash(
    episode: Path,
) -> None:
    with ClosedLoopEnvironment(episode) as environment:
        environment.place_order("S001", "P001", 6, actor="test-agent")
        outcome = environment.run_to_horizon()
        counts = environment.query_sql(
            """
            SELECT
              (SELECT COUNT(*) FROM cl_purchase_orders) AS orders,
              (SELECT COUNT(*) FROM cl_inventory_lots) AS lots,
              (SELECT COUNT(*) FROM cl_sales) AS sales,
              (SELECT COUNT(*) FROM cl_substitutions) AS substitutions,
              (SELECT COUNT(*) FROM cl_spoilage) AS spoilage,
              (SELECT COUNT(*) FROM cl_returns_feedback WHERE return_units>0) AS returns,
              (SELECT COUNT(*) FROM cl_cash_ledger) AS cash_events
            """
        )[0]

    assert counts["orders"] == 1
    assert counts["lots"] > 32
    assert counts["sales"] == 14 * 4 * 8
    assert counts["substitutions"] > 0
    assert counts["spoilage"] > 0
    assert counts["returns"] > 0
    assert counts["cash_events"] > counts["sales"] / 4
    assert outcome.processed_days == 14
    validate_closed_loop_world(episode)


def test_price_action_is_store_specific_and_changes_future_demand(episode: Path) -> None:
    with ClosedLoopEnvironment(episode) as environment:
        environment.change_price("S001", "P001", 2.56, actor="test-agent")
        prices = environment.query_sql(
            "SELECT store_id, unit_price FROM cl_prices WHERE product_id='P001' "
            "ORDER BY store_id"
        )
        environment.advance_day()
        demand = environment.query_sql(
            "SELECT latent_demand_units FROM cl_sales "
            "WHERE business_date='2026-07-01' AND store_id='S001' AND product_id='P001'"
        )[0]["latent_demand_units"]

    assert prices[0]["unit_price"] == 2.56
    assert {row["unit_price"] for row in prices[1:]} == {2.49}
    assert demand >= 0


def test_high_stakes_approval_lifecycle_is_structured(episode: Path) -> None:
    payload = {
        "store_id": "S001",
        "product_id": "P001",
        "start_date": "2026-07-01",
        "end_date": "2026-07-07",
        "discount_pct": 0.15,
    }
    with ClosedLoopEnvironment(episode) as environment:
        with pytest.raises(PolicyViolation, match="approved promotion"):
            environment.schedule_promotion(
                "S001",
                "P001",
                start_date="2026-07-01",
                end_date="2026-07-07",
                discount_pct=0.15,
                actor="test-agent",
            )
        approval = environment.request_approval(
            "promotion", actor="test-agent", payload=payload
        )
        environment.resolve_approval(approval, approved=True)
        environment.schedule_promotion(
            "S001",
            "P001",
            start_date="2026-07-01",
            end_date="2026-07-07",
            discount_pct=0.15,
            actor="test-agent",
            approval_id=approval,
        )
        states = environment.query_sql(
            "SELECT state FROM cl_approval_events WHERE approval_id=? ORDER BY event_id",
            (approval,),
        )

    assert [row["state"] for row in states] == [
        "approval_required",
        "approval_requested",
        "approved",
        "resumed",
    ]
    validate_closed_loop_world(episode)


def test_rejected_approval_must_be_aborted(episode: Path) -> None:
    payload = {"reason": "high exposure"}
    with ClosedLoopEnvironment(episode) as environment:
        approval = environment.request_approval(
            "promotion", actor="test-agent", payload=payload
        )
        environment.resolve_approval(approval, approved=False)
        environment.abort_approval(approval, actor="test-agent")
        states = environment.query_sql(
            "SELECT state FROM cl_approval_events WHERE approval_id=? ORDER BY event_id",
            (approval,),
        )

    assert [row["state"] for row in states] == [
        "approval_required",
        "approval_requested",
        "rejected",
        "aborted",
    ]


@pytest.mark.parametrize("regime", REGIMES)
def test_all_regimes_hold_invariants_under_multiweek_stress(
    tmp_path: Path, regime: str
) -> None:
    database = generate_closed_loop_world(
        tmp_path / regime,
        ClosedLoopConfig(seed=101, horizon_days=35, regime=regime),
    )
    with ClosedLoopEnvironment(database) as environment:
        environment.run_to_horizon()

    report = validate_closed_loop_world(database)
    assert report.processed_days == 35
    assert report.table_counts["cl_daily_metrics"] == 35 * 4


def test_multimonth_episode_runs_reproducibly(tmp_path: Path) -> None:
    config = ClosedLoopConfig(seed=303, horizon_days=60, regime="stress_mixed")
    first = run_baseline(tmp_path / "first", "information_matched", config)
    second = run_baseline(tmp_path / "second", "information_matched", config)

    assert first.outcome == second.outcome
    assert first.outcome.processed_days == 60
    assert first.outcome.service_level > 0.75


def test_baselines_disclose_information_advantage_and_are_executable(tmp_path: Path) -> None:
    catalog = {item["name"]: item for item in baseline_catalog()}
    assert set(catalog) == set(BASELINES)
    assert catalog["privileged_oracle"]["uses_privileged_state"] is True
    assert catalog["privileged_oracle"]["leaderboard_eligible"] is False
    outcomes = {}
    for policy in BASELINES:
        report = run_baseline(
            tmp_path / policy,
            policy,
            ClosedLoopConfig(seed=13, horizon_days=14),
        )
        outcomes[policy] = report.outcome
        assert report.uses_privileged_state == (policy == "privileged_oracle")
        assert report.validation_digest == report.outcome.final_digest
    assert outcomes["reorder_point"].service_level > outcomes["fixed_policy"].service_level
    assert outcomes["privileged_oracle"].gross_profit > 0


def test_cli_generates_validates_and_compares_closed_loop_world(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "world"
    assert main(["generate-closed-loop", str(output), "--days", "14"]) == 0
    capsys.readouterr()
    assert main(["validate-closed-loop", str(output / "episode.sqlite")]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["processed_days"] == 0
    comparison = tmp_path / "comparison"
    assert (
        main(
            [
                "compare-closed-loop",
                str(comparison),
                "--scenario",
                "replenishment",
                "--days",
                "14",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["later_state_changed"] is True
    assert asdict(ClosedLoopConfig())["regime"] == "train_normal"
