"""Oracle-only deterministic economic outcome calculations.

This module is used by graders. Its inputs are deliberately inaccessible through
the agent-facing SQL authorizer and tool API.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from decision_agent_bench.simulator.validation import validate_world


@dataclass(frozen=True)
class PriceOutcome:
    """Expected economics of a candidate store-product price."""

    store_id: str
    product_id: str
    candidate_price: float
    horizon_days: int
    expected_units: float
    expected_revenue: float
    expected_cogs: float
    expected_gross_profit: float


@dataclass(frozen=True)
class PriceDecisionScore:
    """Candidate outcome compared with the best feasible grid price."""

    candidate: PriceOutcome
    oracle: PriceOutcome
    absolute_regret: float
    normalized_regret: float


class EconomicOracle:
    """Read-only counterfactual simulator for deterministic graders."""

    def __init__(self, database_path: Path) -> None:
        validate_world(database_path)
        self._connection = sqlite3.connect(f"file:{database_path.resolve()}?mode=ro", uri=True)
        self._connection.row_factory = sqlite3.Row

    def __enter__(self) -> EconomicOracle:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def price_outcome(
        self, store_id: str, product_id: str, candidate_price: float, *, horizon_days: int = 7
    ) -> PriceOutcome:
        """Simulate price response using a hidden elasticity and recent demand baseline."""

        if not 1 <= horizon_days <= 28:
            raise ValueError("horizon_days must be between 1 and 28")
        row = self._connection.execute(
            """
            SELECT pr.unit_price, p.unit_cost, op.price_elasticity, op.demand_multiplier
            FROM prices pr
            JOIN products p USING (product_id)
            JOIN oracle_parameters op USING (product_id)
            WHERE pr.store_id=? AND pr.product_id=?
            """,
            (store_id, product_id),
        ).fetchone()
        if row is None:
            raise ValueError("unknown store-product pair")
        current_price = float(row["unit_price"])
        unit_cost = float(row["unit_cost"])
        if candidate_price < round(unit_cost * 1.10, 2):
            raise ValueError("candidate violates the margin floor")
        if abs(candidate_price / current_price - 1) > 0.200001:
            raise ValueError("candidate violates the 20% price-change limit")

        max_date = date.fromisoformat(
            self._connection.execute(
                "SELECT MAX(date(sold_at)) FROM transactions"
            ).fetchone()[0]
        )
        start = (max_date - timedelta(days=27)).isoformat()
        observed_units = self._connection.execute(
            """
            SELECT COALESCE(SUM(units), 0) FROM transactions
            WHERE store_id=? AND product_id=? AND date(sold_at)>=?
            """,
            (store_id, product_id, start),
        ).fetchone()[0]
        baseline_daily_units = float(observed_units) / 28
        price_ratio = candidate_price / current_price
        daily_units = (
            baseline_daily_units
            * price_ratio ** float(row["price_elasticity"])
            * float(row["demand_multiplier"])
        )
        expected_units = round(daily_units * horizon_days, 4)
        revenue = round(expected_units * candidate_price, 4)
        cogs = round(expected_units * unit_cost, 4)
        return PriceOutcome(
            store_id=store_id,
            product_id=product_id,
            candidate_price=round(candidate_price, 2),
            horizon_days=horizon_days,
            expected_units=expected_units,
            expected_revenue=revenue,
            expected_cogs=cogs,
            expected_gross_profit=round(revenue - cogs, 4),
        )

    def score_price_decision(
        self, store_id: str, product_id: str, candidate_price: float, *, horizon_days: int = 7
    ) -> PriceDecisionScore:
        """Compare a candidate price with an exhaustive feasible one-cent grid oracle."""

        current = self._connection.execute(
            """
            SELECT pr.unit_price, p.unit_cost
            FROM prices pr JOIN products p USING (product_id)
            WHERE pr.store_id=? AND pr.product_id=?
            """,
            (store_id, product_id),
        ).fetchone()
        if current is None:
            raise ValueError("unknown store-product pair")
        floor_price = math.ceil(float(current["unit_cost"]) * 1.10 * 100) / 100
        change_floor = math.ceil(float(current["unit_price"]) * 0.8 * 100) / 100
        lower = max(floor_price, change_floor)
        upper = math.floor(float(current["unit_price"]) * 1.2 * 100) / 100
        number_of_prices = int(round((upper - lower) * 100)) + 1
        prices = [round(lower + index * 0.01, 2) for index in range(number_of_prices)]
        outcomes = [
            self.price_outcome(store_id, product_id, price, horizon_days=horizon_days)
            for price in prices
        ]
        oracle = max(
            outcomes,
            key=lambda outcome: (outcome.expected_gross_profit, -outcome.candidate_price),
        )
        candidate = self.price_outcome(
            store_id, product_id, candidate_price, horizon_days=horizon_days
        )
        regret = max(0.0, oracle.expected_gross_profit - candidate.expected_gross_profit)
        normalized = regret / max(abs(oracle.expected_gross_profit), 1e-9)
        return PriceDecisionScore(
            candidate=candidate,
            oracle=oracle,
            absolute_regret=round(regret, 4),
            normalized_regret=round(normalized, 6),
        )
