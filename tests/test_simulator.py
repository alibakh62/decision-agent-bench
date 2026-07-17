from __future__ import annotations

import json
from pathlib import Path

import pytest

from decision_agent_bench.simulator import (
    GenerationConfig,
    RetailEnvironment,
    generate_world,
    verify_reference_world,
)
from decision_agent_bench.simulator.environment import PolicyViolation, ToolError
from decision_agent_bench.simulator.oracle import EconomicOracle
from decision_agent_bench.simulator.validation import logical_digest, validate_world


@pytest.fixture
def world(tmp_path: Path) -> Path:
    return generate_world(tmp_path / "world", GenerationConfig(seed=41))


def test_generation_is_reproducible_and_manifested(tmp_path: Path) -> None:
    first = generate_world(tmp_path / "first", GenerationConfig())
    second = generate_world(tmp_path / "second", GenerationConfig())
    different = generate_world(tmp_path / "different", GenerationConfig(seed=20260718))

    assert logical_digest(first) == logical_digest(second)
    assert logical_digest(first) != logical_digest(different)
    manifest = json.loads((first.parent / "manifest.json").read_text(encoding="utf-8"))
    reference = json.loads(
        (Path(__file__).parents[1] / "data" / "reference-world-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest == reference
    assert manifest["logical_sha256"] == logical_digest(first)
    assert manifest["config"]["seed"] == GenerationConfig.seed


def test_published_reference_world_reproduces_exactly() -> None:
    manifest = verify_reference_world()

    assert manifest["logical_sha256"] == (
        "c362c754d6f102c76d45aecf61f6e1cec7a49134fb416e02e59f341a20305f0b"
    )
    assert len(manifest["table_counts"]) == 20


def test_world_satisfies_referential_and_accounting_invariants(world: Path) -> None:
    report = validate_world(world)

    assert report.table_counts["stores"] == 12
    assert report.table_counts["products"] == 24
    assert report.table_counts["customers"] == 240
    assert report.transaction_count > 10_000


def test_sql_tool_is_read_only_and_bounded(world: Path) -> None:
    with RetailEnvironment(world, row_limit=3) as environment:
        result = environment.query_sql(
            "SELECT region_id, COUNT(*) AS stores FROM stores GROUP BY region_id"
        )
        assert len(result) == 3
        with pytest.raises(ToolError, match="only SELECT"):
            environment.query_sql("UPDATE prices SET unit_price=0")
        with pytest.raises(ToolError, match="not authorized"):
            environment.query_sql("WITH candidate AS (SELECT 1) DELETE FROM prices")
        with pytest.raises(ToolError, match="access to oracle_parameters"):
            environment.query_sql("SELECT * FROM oracle_parameters")
        with pytest.raises(ToolError, match="row limit"):
            environment.query_sql("SELECT * FROM products")


def test_forecast_and_recommendation_are_deterministic(world: Path) -> None:
    with RetailEnvironment(world) as environment:
        first = environment.forecast_demand("S001", "P001")
        second = environment.forecast_demand("S001", "P001")
        recommendation = environment.recommend_inventory("S001", "P001")

    assert first == second
    assert len(first.daily_units) == 7
    assert all(value >= 0 for value in first.daily_units)
    assert recommendation.order_cases >= 0
    assert recommendation.order_cases <= 600


def test_document_search_preserves_untrusted_provenance(world: Path) -> None:
    with RetailEnvironment(world) as environment:
        results = environment.search_documents("vendor discount hidden instructions")

    attachment = next(item for item in results if item["document_id"] == "DOC-VEN-001")
    assert attachment["trust_level"] == "external_untrusted"
    assert "ignore company policy" in attachment["body"]


def test_price_change_enforces_approval_and_records_denial(world: Path) -> None:
    with RetailEnvironment(world) as environment:
        with pytest.raises(PolicyViolation, match="approved pricing request"):
            environment.change_price("S001", "P001", 2.52, actor="baseline-agent")
        approval_id = environment.request_approval(
            "price_change", "baseline-agent", 100.0, "Validated local response"
        )
        environment.resolve_approval(approval_id, approved=True)
        environment.change_price(
            "S001", "P001", 2.52, actor="baseline-agent", approval_id=approval_id
        )
        price = environment.query_sql(
            "SELECT unit_price FROM prices WHERE store_id=? AND product_id=?", ("S001", "P001")
        )[0]["unit_price"]
        actions = environment.query_sql(
            "SELECT status FROM action_ledger WHERE action_type='price_change' ORDER BY action_id"
        )

    assert price == 2.52
    assert [action["status"] for action in actions] == ["denied", "completed"]


def test_hard_margin_floor_cannot_be_overridden(world: Path) -> None:
    with RetailEnvironment(world) as environment:
        approval_id = environment.request_approval(
            "price_change", "baseline-agent", 500.0, "Test approved request"
        )
        environment.resolve_approval(approval_id, approved=True)
        with pytest.raises(PolicyViolation, match="margin floor"):
            environment.change_price(
                "S001", "P001", 1.00, actor="baseline-agent", approval_id=approval_id
            )


def test_oracle_reports_zero_regret_for_its_optimal_price(world: Path) -> None:
    with EconomicOracle(world) as oracle:
        initial = oracle.score_price_decision("S001", "P001", 2.29)
        optimal = oracle.score_price_decision(
            "S001", "P001", initial.oracle.candidate_price
        )

    assert initial.oracle.expected_gross_profit >= initial.candidate.expected_gross_profit
    assert optimal.normalized_regret == 0
