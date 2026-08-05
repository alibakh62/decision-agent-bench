"""Classical and diagnostic policies for the v0.7 closed-loop retail world."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from decision_agent_bench.simulator.closed_loop import (
    ClosedLoopConfig,
    ClosedLoopEnvironment,
    EpisodeOutcome,
    generate_closed_loop_world,
    validate_closed_loop_world,
)
from decision_agent_bench.simulator.environment import PolicyViolation, ToolError

PUBLIC_BASELINES = (
    "random",
    "fixed_policy",
    "reorder_point",
    "newsvendor",
    "pricing",
    "information_matched",
)
PRIVILEGED_BASELINE = "privileged_oracle"
BASELINES = (*PUBLIC_BASELINES, PRIVILEGED_BASELINE)


@dataclass(frozen=True)
class BaselineRun:
    """Portable outcome and disclosure for one baseline episode."""

    policy: str
    uses_privileged_state: bool
    leaderboard_eligible: bool
    config: dict[str, Any]
    outcome: EpisodeOutcome
    validation_digest: str


def baseline_catalog() -> list[dict[str, Any]]:
    """Return explicit information boundaries for every reference policy."""

    descriptions = {
        "random": "Seeded random feasible order/price actions using public state.",
        "fixed_policy": "Fixed weekly case orders independent of realized demand.",
        "reorder_point": "Orders vendor-minimum cases when public inventory crosses its threshold.",
        "newsvendor": "Lead-time demand plus safety-stock policy estimated from public sales.",
        "pricing": "Small public-history price adjustments without hidden elasticity.",
        "information_matched": "Public newsvendor, pricing, and demand-weighted shelf allocation.",
        "privileged_oracle": "Diagnostic policy with hidden structural demand parameters.",
    }
    return [
        {
            "name": name,
            "description": descriptions[name],
            "uses_privileged_state": name == PRIVILEGED_BASELINE,
            "leaderboard_eligible": name != PRIVILEGED_BASELINE,
        }
        for name in BASELINES
    ]


def run_baseline(
    output_dir: Path,
    policy: str,
    config: ClosedLoopConfig | None = None,
    *,
    overwrite: bool = False,
) -> BaselineRun:
    """Generate an episode, apply one policy daily, and write a portable run report."""

    if policy not in BASELINES:
        raise ValueError(f"unknown baseline {policy!r}; choose from {', '.join(BASELINES)}")
    selected = config or ClosedLoopConfig()
    database = generate_closed_loop_world(output_dir, selected, overwrite=overwrite)
    with ClosedLoopEnvironment(database) as environment:
        while environment.processed_days < environment.horizon_days:
            apply_policy(environment, policy)
            environment.advance_day()
        outcome = environment.outcome()
    validation = validate_closed_loop_world(database)
    report = BaselineRun(
        policy=policy,
        uses_privileged_state=policy == PRIVILEGED_BASELINE,
        leaderboard_eligible=policy != PRIVILEGED_BASELINE,
        config=asdict(selected),
        outcome=outcome,
        validation_digest=validation.logical_sha256,
    )
    (output_dir / "policy-run.json").write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def apply_policy(environment: ClosedLoopEnvironment, policy: str) -> None:
    """Apply one day of a declared policy before the evaluator advances time."""

    if policy == "random":
        _random_policy(environment)
    elif policy == "fixed_policy":
        _fixed_policy(environment)
    elif policy == "reorder_point":
        _reorder_policy(environment, safety_multiplier=1.0)
    elif policy == "newsvendor":
        _newsvendor_policy(environment)
    elif policy == "pricing":
        _pricing_policy(environment)
    elif policy == "information_matched":
        _newsvendor_policy(environment)
        _pricing_policy(environment)
        _shelf_policy(environment)
    elif policy == PRIVILEGED_BASELINE:
        _privileged_policy(environment)
    else:
        raise ValueError(f"unknown baseline: {policy}")


def _policy_day(environment: ClosedLoopEnvironment) -> int:
    return environment.processed_days + 1


def _stable_fraction(*parts: object) -> float:
    payload = ":".join(str(part) for part in parts).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / 2**64


def _safe_order(
    environment: ClosedLoopEnvironment,
    store_id: str,
    product_id: str,
    cases: int,
    actor: str,
) -> None:
    try:
        environment.place_order(store_id, product_id, cases, actor=actor)
    except (PolicyViolation, ToolError):
        # Denied attempts remain visible in the action ledger and policy comparisons.
        pass


def _open_order_pairs(environment: ClosedLoopEnvironment) -> set[tuple[str, str]]:
    rows = environment.query_sql(
        "SELECT store_id, product_id FROM cl_purchase_orders "
        "WHERE status NOT IN ('delivered', 'cancelled')"
    )
    return {(str(row["store_id"]), str(row["product_id"])) for row in rows}


def _random_policy(environment: ClosedLoopEnvironment) -> None:
    rows = environment.query_sql(
        """
        SELECT i.store_id, i.product_id, v.minimum_cases, pr.unit_price
        FROM cl_inventory i JOIN cl_products p USING (product_id)
        JOIN cl_vendors v USING (vendor_id)
        JOIN cl_prices pr USING (store_id, product_id)
        ORDER BY i.store_id, i.product_id
        """
    )
    day = _policy_day(environment)
    for row in rows:
        draw = _stable_fraction("random-policy", day, row["store_id"], row["product_id"])
        if draw < 0.025:
            _safe_order(
                environment,
                str(row["store_id"]),
                str(row["product_id"]),
                int(row["minimum_cases"]),
                "random-policy",
            )
        elif draw > 0.985:
            direction = -1 if draw > 0.9925 else 1
            try:
                environment.change_price(
                    str(row["store_id"]),
                    str(row["product_id"]),
                    round(float(row["unit_price"]) * (1 + direction * 0.02), 2),
                    actor="random-policy",
                )
            except (PolicyViolation, ToolError):
                pass


def _fixed_policy(environment: ClosedLoopEnvironment) -> None:
    if (_policy_day(environment) - 1) % 7:
        return
    rows = environment.query_sql(
        """
        SELECT i.store_id, i.product_id, v.minimum_cases
        FROM cl_inventory i JOIN cl_products p USING (product_id)
        JOIN cl_vendors v USING (vendor_id)
        WHERE CAST(SUBSTR(i.product_id, 2) AS INTEGER) <= 4
        ORDER BY i.store_id, i.product_id
        """
    )
    open_pairs = _open_order_pairs(environment)
    for row in rows:
        pair = (str(row["store_id"]), str(row["product_id"]))
        if pair not in open_pairs:
            _safe_order(
                environment,
                *pair,
                int(row["minimum_cases"]),
                "fixed-policy",
            )


def _reorder_policy(
    environment: ClosedLoopEnvironment, *, safety_multiplier: float
) -> None:
    rows = environment.query_sql(
        """
        SELECT i.store_id, i.product_id, i.on_hand_units, i.reorder_point,
               v.case_pack, v.minimum_cases
        FROM cl_inventory i JOIN cl_products p USING (product_id)
        JOIN cl_vendors v USING (vendor_id)
        WHERE i.on_hand_units <= i.reorder_point * ?
        ORDER BY i.on_hand_units * 1.0 / MAX(i.reorder_point, 1), i.store_id, i.product_id
        """,
        (safety_multiplier,),
    )
    open_pairs = _open_order_pairs(environment)
    for row in rows:
        pair = (str(row["store_id"]), str(row["product_id"]))
        if pair in open_pairs:
            continue
        target = math.ceil(float(row["reorder_point"]) * 2.0)
        shortfall = max(0, target - int(row["on_hand_units"]))
        cases = max(
            int(row["minimum_cases"]), math.ceil(shortfall / int(row["case_pack"]))
        )
        _safe_order(environment, *pair, cases, "reorder-point")


def _newsvendor_policy(environment: ClosedLoopEnvironment) -> None:
    rows = environment.query_sql(
        """
        SELECT i.store_id, i.product_id, i.on_hand_units, v.lead_time_days,
               v.case_pack, v.minimum_cases,
               COALESCE(AVG(s.latent_demand_units), i.reorder_point / 5.0) AS mean_demand
        FROM cl_inventory i JOIN cl_products p USING (product_id)
        JOIN cl_vendors v USING (vendor_id)
        LEFT JOIN cl_sales s ON s.store_id=i.store_id AND s.product_id=i.product_id
        GROUP BY i.store_id, i.product_id
        ORDER BY i.store_id, i.product_id
        """
    )
    open_pairs = _open_order_pairs(environment)
    for row in rows:
        pair = (str(row["store_id"]), str(row["product_id"]))
        if pair in open_pairs:
            continue
        mean = float(row["mean_demand"])
        protection_days = int(row["lead_time_days"]) + 5
        target = math.ceil(mean * protection_days + 1.28 * math.sqrt(mean * protection_days))
        shortfall = target - int(row["on_hand_units"])
        if shortfall <= 0:
            continue
        cases = max(
            int(row["minimum_cases"]), math.ceil(shortfall / int(row["case_pack"]))
        )
        _safe_order(environment, *pair, cases, "newsvendor")


def _pricing_policy(environment: ClosedLoopEnvironment) -> None:
    if _policy_day(environment) < 8 or _policy_day(environment) % 7:
        return
    rows = environment.query_sql(
        """
        SELECT pr.store_id, pr.product_id, pr.unit_price, p.unit_cost,
               COALESCE(SUM(s.sold_units + s.substituted_units), 0) AS fulfilled,
               COALESCE(SUM(s.latent_demand_units), 0) AS demand
        FROM cl_prices pr JOIN cl_products p USING (product_id)
        LEFT JOIN cl_sales s USING (store_id, product_id)
        GROUP BY pr.store_id, pr.product_id
        ORDER BY pr.store_id, pr.product_id
        """
    )
    for row in rows:
        service = float(row["fulfilled"]) / float(row["demand"]) if row["demand"] else 1.0
        factor = 1.03 if service < 0.75 else 0.98 if service > 0.96 else 1.0
        if factor == 1.0:
            continue
        new_price = max(float(row["unit_cost"]) * 1.10, float(row["unit_price"]) * factor)
        try:
            environment.change_price(
                str(row["store_id"]),
                str(row["product_id"]),
                round(new_price, 2),
                actor="public-pricing",
            )
        except (PolicyViolation, ToolError):
            pass


def _shelf_policy(environment: ClosedLoopEnvironment) -> None:
    if _policy_day(environment) % 7:
        return
    stores = environment.query_sql(
        "SELECT store_id, shelf_capacity_units FROM cl_stores ORDER BY store_id"
    )
    for store in stores:
        rows = environment.query_sql(
            """
            SELECT p.product_id, p.space_units,
                   COALESCE(AVG(s.latent_demand_units), i.reorder_point / 5.0) AS demand
            FROM cl_products p JOIN cl_inventory i USING (product_id)
            LEFT JOIN cl_sales s USING (store_id, product_id)
            WHERE i.store_id=?
            GROUP BY p.product_id, p.space_units, i.reorder_point
            ORDER BY demand DESC, p.product_id
            """,
            (store["store_id"],),
        )
        weights = [max(float(row["demand"]), 0.1) for row in rows]
        total = sum(
            weight * int(row["space_units"])
            for weight, row in zip(weights, rows, strict=True)
        )
        allocations = {
            str(row["product_id"]): max(
                1,
                math.floor(
                    int(store["shelf_capacity_units"]) * weight / max(total, 1.0)
                ),
            )
            for weight, row in zip(weights, rows, strict=True)
        }
        try:
            environment.allocate_shelf(
                str(store["store_id"]), allocations, actor="information-matched"
            )
        except (PolicyViolation, ToolError):
            pass


def _privileged_policy(environment: ClosedLoopEnvironment) -> None:
    # The diagnostic oracle also receives the same shelf-action surface; unlike the public
    # information-matched policy, its order targets below use hidden structural demand.
    _shelf_policy(environment)
    connection = sqlite3.connect(environment.database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT dp.store_id, dp.product_id, dp.base_daily_demand, dp.price_elasticity,
                   i.on_hand_units, v.lead_time_days, v.case_pack, v.minimum_cases,
                   p.base_price, p.unit_cost
            FROM cl_demand_parameters dp JOIN cl_inventory i USING (store_id, product_id)
            JOIN cl_products p USING (product_id) JOIN cl_vendors v USING (vendor_id)
            ORDER BY dp.store_id, dp.product_id
            """
        ).fetchall()
    finally:
        connection.close()
    open_pairs = _open_order_pairs(environment)
    for row in rows:
        pair = (str(row["store_id"]), str(row["product_id"]))
        protection = int(row["lead_time_days"]) + 7
        target = math.ceil(float(row["base_daily_demand"]) * protection * 1.15)
        shortfall = target - int(row["on_hand_units"])
        if shortfall > 0 and pair not in open_pairs:
            cases = max(
                int(row["minimum_cases"]), math.ceil(shortfall / int(row["case_pack"]))
            )
            _safe_order(environment, *pair, cases, "privileged-oracle")
        if _policy_day(environment) == 1:
            elasticity = float(row["price_elasticity"])
            cost = float(row["unit_cost"])
            # Constant-elasticity monopoly price, clipped to the simulator policy envelope.
            unconstrained = (
                cost * elasticity / (elasticity + 1)
                if elasticity < -1
                else float(row["base_price"])
            )
            lower = max(cost * 1.10, float(row["base_price"]) * 0.95)
            upper = float(row["base_price"]) * 1.05
            candidate = min(upper, max(lower, unconstrained))
            try:
                environment.change_price(
                    *pair,
                    round(candidate, 2),
                    actor="privileged-oracle",
                )
            except (PolicyViolation, ToolError):
                pass
