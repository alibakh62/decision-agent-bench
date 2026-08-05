"""Deterministic, action-sensitive v0.7 convenience-retail episode simulator."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from decision_agent_bench.simulator.closed_loop_schema import (
    CLOSED_LOOP_INTERNAL_TABLES,
    CLOSED_LOOP_PUBLIC_TABLES,
    CLOSED_LOOP_SCHEMA_SQL,
    CLOSED_LOOP_SCHEMA_VERSION,
    CLOSED_LOOP_TABLES,
)
from decision_agent_bench.simulator.environment import PolicyViolation, ToolError

REGIMES = (
    "train_normal",
    "heldout_supply_shock",
    "heldout_demand_shift",
    "heldout_cold_chain",
    "stress_mixed",
)


@dataclass(frozen=True)
class ClosedLoopConfig:
    """Complete reproducible configuration for one closed-loop world."""

    seed: int = 20260805
    start_date: str = "2026-07-01"
    horizon_days: int = 28
    regime: str = "train_normal"
    stores: int = 4
    products: int = 8
    demand_scale: float = 1.0
    price_elasticity_scale: float = 1.0
    return_rate_scale: float = 1.0
    lead_time_scale: float = 1.0
    disruption_scale: float = 1.0

    def validate(self) -> None:
        date.fromisoformat(self.start_date)
        if not 14 <= self.horizon_days <= 180:
            raise ValueError("horizon_days must be between 14 and 180")
        if self.regime not in REGIMES:
            raise ValueError(f"regime must be one of {', '.join(REGIMES)}")
        if not 2 <= self.stores <= 8:
            raise ValueError("stores must be between 2 and 8")
        if not 8 <= self.products <= 24 or self.products % 4:
            raise ValueError("products must be a multiple of four between 8 and 24")
        scales = {
            "demand_scale": self.demand_scale,
            "price_elasticity_scale": self.price_elasticity_scale,
            "return_rate_scale": self.return_rate_scale,
            "lead_time_scale": self.lead_time_scale,
            "disruption_scale": self.disruption_scale,
        }
        for name, value in scales.items():
            if not 0.5 <= value <= 1.5:
                raise ValueError(f"{name} must be between 0.5 and 1.5")


@dataclass(frozen=True)
class ClosedLoopValidationReport:
    """Invariant evidence for a closed-loop database."""

    table_counts: dict[str, int]
    processed_days: int
    action_count: int
    ledger_entries: int
    logical_sha256: str


@dataclass(frozen=True)
class EpisodeOutcome:
    """Comparable end-to-end outcome exposed to baselines and graders."""

    processed_days: int
    revenue: float
    gross_profit: float
    lost_sales_units: int
    spoiled_units: int
    returned_units: int
    ending_cash: float
    service_level: float
    action_count: int
    final_digest: str


_WRITE_ACTIONS = {
    sqlite3.SQLITE_INSERT,
    sqlite3.SQLITE_UPDATE,
    sqlite3.SQLITE_DELETE,
    sqlite3.SQLITE_CREATE_INDEX,
    sqlite3.SQLITE_CREATE_TABLE,
    sqlite3.SQLITE_CREATE_TEMP_INDEX,
    sqlite3.SQLITE_CREATE_TEMP_TABLE,
    sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
    sqlite3.SQLITE_CREATE_TEMP_VIEW,
    sqlite3.SQLITE_CREATE_TRIGGER,
    sqlite3.SQLITE_CREATE_VIEW,
    sqlite3.SQLITE_DROP_INDEX,
    sqlite3.SQLITE_DROP_TABLE,
    sqlite3.SQLITE_DROP_TEMP_INDEX,
    sqlite3.SQLITE_DROP_TEMP_TABLE,
    sqlite3.SQLITE_DROP_TEMP_TRIGGER,
    sqlite3.SQLITE_DROP_TEMP_VIEW,
    sqlite3.SQLITE_DROP_TRIGGER,
    sqlite3.SQLITE_DROP_VIEW,
    sqlite3.SQLITE_ALTER_TABLE,
    sqlite3.SQLITE_ATTACH,
    sqlite3.SQLITE_DETACH,
    sqlite3.SQLITE_PRAGMA,
}


def _agent_authorizer(
    action: int,
    arg1: str | None,
    _arg2: str | None,
    _database: str | None,
    _source: str | None,
) -> int:
    if action == sqlite3.SQLITE_READ and arg1 not in CLOSED_LOOP_PUBLIC_TABLES:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_DENY if action in _WRITE_ACTIONS else sqlite3.SQLITE_OK


def _money(value: float) -> float:
    return round(value + 1e-10, 2)


def _canonical_rows(connection: sqlite3.Connection) -> Iterable[bytes]:
    tables = sorted(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    )
    for table in tables:
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
        order = ", ".join(f'"{column}"' for column in columns)
        yield f"table:{table}\n".encode()
        for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY {order}'):
            values = [row[column] for column in columns]
            yield (json.dumps(values, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def closed_loop_digest(path: Path) -> str:
    """Hash canonical closed-loop state independent of SQLite page layout."""

    digest = hashlib.sha256()
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        for row in _canonical_rows(connection):
            digest.update(row)
    finally:
        connection.close()
    return digest.hexdigest()


def _keyed_uniform(seed: int, *parts: object) -> float:
    payload = ":".join([str(seed), *(str(part) for part in parts)]).encode()
    value = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return value / 2**64


def _populate_closed_loop(connection: sqlite3.Connection, config: ClosedLoopConfig) -> None:
    connection.executescript(CLOSED_LOOP_SCHEMA_SQL)
    first_date = date.fromisoformat(config.start_date)
    connection.executemany(
        "INSERT INTO cl_metadata VALUES (?, ?)",
        [
            ("schema_version", CLOSED_LOOP_SCHEMA_VERSION),
            ("seed", str(config.seed)),
            ("start_date", config.start_date),
            ("current_date", (first_date - timedelta(days=1)).isoformat()),
            ("horizon_days", str(config.horizon_days)),
            ("regime", config.regime),
            ("processed_days", "0"),
            ("disruption_scale", str(config.disruption_scale)),
        ],
    )

    formats = ("urban", "suburban", "highway", "campus")
    stores = []
    for index in range(config.stores):
        multiplier = round(
            0.82 + 0.14 * index + 0.08 * _keyed_uniform(config.seed, "store", index),
            4,
        )
        shelf_capacity = 180 + index * 24
        storage_capacity = 900 + index * 120
        opening_cash = 25_000.0 + index * 2_500.0
        stores.append(
            (
                f"S{index + 1:03d}",
                formats[index % len(formats)],
                multiplier,
                shelf_capacity,
                storage_capacity,
                opening_cash,
                opening_cash,
            )
        )
    connection.executemany("INSERT INTO cl_stores VALUES (?, ?, ?, ?, ?, ?, ?)", stores)

    base_vendors = [
        ("V001", 2, 12, 2, 50, 0.98),
        ("V002", 3, 18, 2, 42, 0.94),
        ("V003", 1, 6, 3, 60, 0.97),
        ("V004", 5, 8, 2, 36, 0.91),
    ]
    vendors = [
        (
            vendor_id,
            max(1, round(lead_time * config.lead_time_scale)),
            case_pack,
            minimum_cases,
            capacity,
            fill_rate,
        )
        for vendor_id, lead_time, case_pack, minimum_cases, capacity, fill_rate in base_vendors
    ]
    connection.executemany("INSERT INTO cl_vendors VALUES (?, ?, ?, ?, ?, ?)", vendors)

    categories = (
        ("beverage", 1.08, 2.49, 120, 2, -1.20, 9.0, 0.28, 0.008),
        ("snack", 0.79, 1.89, 180, 1, -1.05, 7.5, 0.24, 0.006),
        ("fresh", 1.72, 3.79, 6, 3, -0.82, 5.2, 0.18, 0.035),
        ("household", 2.90, 5.79, 365, 4, -0.58, 2.7, 0.12, 0.004),
    )
    products = []
    demand_parameters = []
    for product_index in range(config.products):
        (
            category,
            base_cost,
            base_price,
            shelf_life,
            space_units,
            elasticity,
            base_demand,
            substitution,
            return_rate,
        ) = categories[product_index % len(categories)]
        product_id = f"P{product_index + 1:03d}"
        vendor_id = vendors[product_index % len(vendors)][0]
        cost = _money(base_cost + 0.06 * (product_index // 4))
        price = _money(base_price + 0.12 * (product_index // 4))
        products.append(
            (
                product_id,
                vendor_id,
                category,
                cost,
                price,
                shelf_life,
                space_units,
                1,
            )
        )
        for store_index, store in enumerate(stores):
            noise = 0.90 + 0.20 * _keyed_uniform(config.seed, "demand", store_index, product_index)
            demand_parameters.append(
                (
                    store[0],
                    product_id,
                    round(base_demand * store[2] * noise * config.demand_scale, 4),
                    elasticity * config.price_elasticity_scale,
                    0.35 if category != "household" else 0.18,
                    substitution,
                    min(0.25, return_rate * config.return_rate_scale),
                )
            )
    connection.executemany("INSERT INTO cl_products VALUES (?, ?, ?, ?, ?, ?, ?, ?)", products)
    connection.executemany(
        "INSERT INTO cl_prices VALUES (?, ?, ?, ?)",
        [
            (store[0], product[0], product[4], config.start_date)
            for store in stores
            for product in products
        ],
    )
    connection.executemany(
        "INSERT INTO cl_demand_parameters VALUES (?, ?, ?, ?, ?, ?, ?)",
        demand_parameters,
    )

    inventory = []
    lots = []
    shelves = []
    for store in stores:
        used_space = 0
        for product in products:
            parameter = next(
                row
                for row in demand_parameters
                if row[0] == store[0] and row[1] == product[0]
            )
            target = max(2 * vendors[int(product[1][-1]) - 1][2], math.ceil(parameter[2] * 10))
            remaining_space = max(0, store[3] - used_space)
            shelf_units = min(target // 2, remaining_space // product[6])
            used_space += shelf_units * product[6]
            inventory.append(
                (
                    store[0],
                    product[0],
                    target,
                    shelf_units,
                    math.ceil(parameter[2] * 5),
                    config.start_date,
                )
            )
            shelves.append((store[0], product[0], shelf_units, config.start_date))
            lots.append(
                (
                    f"LOT-{store[0]}-{product[0]}-0001",
                    store[0],
                    product[0],
                    config.start_date,
                    (first_date + timedelta(days=product[5])).isoformat(),
                    target,
                    target,
                    product[3],
                )
            )
    connection.executemany("INSERT INTO cl_inventory VALUES (?, ?, ?, ?, ?, ?)", inventory)
    connection.executemany(
        "INSERT INTO cl_inventory_lots VALUES (?, ?, ?, ?, ?, ?, ?, ?)", lots
    )
    connection.executemany("INSERT INTO cl_shelf_allocations VALUES (?, ?, ?, ?)", shelves)
    for store in stores:
        connection.execute(
            "INSERT INTO cl_cash_ledger VALUES (?, ?, ?, 'opening', ?, ?, ?)",
            (
                f"CASH-{store[0]}-000001",
                (first_date - timedelta(days=1)).isoformat(),
                store[0],
                store[5],
                "episode_open",
                store[5],
            ),
        )


def generate_closed_loop_world(
    output_dir: Path,
    config: ClosedLoopConfig | None = None,
    *,
    overwrite: bool = False,
) -> Path:
    """Create a separate v0.7 episode database and content-addressed initial manifest."""

    selected = config or ClosedLoopConfig()
    selected.validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    database_path = output_dir / "episode.sqlite"
    manifest_path = output_dir / "manifest.json"
    if not overwrite and (database_path.exists() or manifest_path.exists()):
        raise FileExistsError(f"closed-loop world already exists in {output_dir}")
    database_path.unlink(missing_ok=True)
    manifest_path.unlink(missing_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        _populate_closed_loop(connection, selected)
        connection.commit()
    finally:
        connection.close()
    report = validate_closed_loop_world(database_path)
    manifest = {
        "benchmark": "DecisionAgentBench",
        "world_contract": "closed_loop_retail",
        "schema_version": CLOSED_LOOP_SCHEMA_VERSION,
        "config": asdict(selected),
        "initial_logical_sha256": report.logical_sha256,
        "table_counts": report.table_counts,
        "randomness": "SHA-256 keyed counterfactual draws; independent of action order",
        "agent_visibility": sorted(CLOSED_LOOP_PUBLIC_TABLES),
        "oracle_only": sorted(CLOSED_LOOP_INTERNAL_TABLES),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return database_path


class ClosedLoopEnvironment:
    """Bounded agent interface plus evaluator-only deterministic episode clock."""

    def __init__(self, database_path: Path, *, row_limit: int = 500) -> None:
        validate_closed_loop_world(database_path)
        self.database_path = database_path
        self.row_limit = row_limit
        self._connection = sqlite3.connect(database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

    def __enter__(self) -> ClosedLoopEnvironment:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    @property
    def current_date(self) -> date:
        return date.fromisoformat(self._metadata("current_date"))

    @property
    def processed_days(self) -> int:
        return int(self._metadata("processed_days"))

    @property
    def horizon_days(self) -> int:
        return int(self._metadata("horizon_days"))

    def query_sql(self, sql: str, parameters: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Run one row-bounded query over public operational state only."""

        normalized = sql.strip()
        if not re.match(r"^(SELECT|WITH)\b", normalized, flags=re.IGNORECASE):
            raise ToolError("only SELECT and read-only WITH queries are allowed")
        if ";" in normalized.rstrip(";"):
            raise ToolError("exactly one SQL statement is allowed")
        self._connection.set_authorizer(_agent_authorizer)
        try:
            cursor = self._connection.execute(normalized, tuple(parameters))
            rows = cursor.fetchmany(self.row_limit + 1)
        except sqlite3.Error as error:
            raise ToolError(f"query failed: {error}") from error
        finally:
            self._connection.set_authorizer(None)
        if len(rows) > self.row_limit:
            raise ToolError(
                f"query exceeded the {self.row_limit}-row limit; aggregate or filter it"
            )
        return [dict(row) for row in rows]

    def place_order(
        self,
        store_id: str,
        product_id: str,
        cases: int,
        *,
        actor: str,
    ) -> str:
        """Place a capacity-constrained purchase order visible to future transitions."""

        if isinstance(cases, bool) or not isinstance(cases, int) or cases <= 0:
            raise ToolError("cases must be a positive integer")
        row = self._connection.execute(
            """
            SELECT p.vendor_id, v.lead_time_days, v.case_pack, v.minimum_cases,
                   v.weekly_capacity_cases, p.unit_cost, s.storage_capacity_units,
                   COALESCE((SELECT SUM(on_hand_units) FROM cl_inventory
                             WHERE store_id=s.store_id), 0) AS store_on_hand_units
            FROM cl_products p JOIN cl_vendors v USING (vendor_id)
            JOIN cl_stores s ON s.store_id=?
            LEFT JOIN cl_inventory i ON i.store_id=s.store_id AND i.product_id=p.product_id
            WHERE p.product_id=?
            """,
            (store_id, product_id),
        ).fetchone()
        if row is None:
            raise ToolError("unknown store-product pair")
        payload = {"store_id": store_id, "product_id": product_id, "cases": cases}
        if cases < int(row["minimum_cases"]):
            self._deny("purchase_order", actor, payload, "vendor minimum not met")
        week_start = self.current_date - timedelta(days=self.current_date.weekday())
        already_ordered = self._connection.execute(
            """
            SELECT COALESCE(SUM(cases_ordered), 0) FROM cl_purchase_orders
            WHERE vendor_id=? AND ordered_date>=? AND status!='cancelled'
            """,
            (row["vendor_id"], week_start.isoformat()),
        ).fetchone()[0]
        if already_ordered + cases > int(row["weekly_capacity_cases"]):
            self._deny("purchase_order", actor, payload, "vendor weekly capacity exceeded")
        units = cases * int(row["case_pack"])
        pipeline_units = self._connection.execute(
            """
            SELECT COALESCE(SUM((po.cases_ordered - po.cases_delivered) * v.case_pack), 0)
            FROM cl_purchase_orders po JOIN cl_vendors v USING (vendor_id)
            WHERE po.store_id=? AND po.status NOT IN ('delivered', 'cancelled')
            """,
            (store_id,),
        ).fetchone()[0]
        if (
            int(row["store_on_hand_units"]) + int(pipeline_units) + units
            > int(row["storage_capacity_units"])
        ):
            self._deny("purchase_order", actor, payload, "store storage capacity exceeded")
        order_id = self._next_id("cl_purchase_orders", "PO")
        ordered = max(self.current_date, date.fromisoformat(self._metadata("start_date")))
        expected = ordered + timedelta(days=int(row["lead_time_days"]))
        self._connection.execute(
            "INSERT INTO cl_purchase_orders VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'placed', ?)",
            (
                order_id,
                store_id,
                product_id,
                row["vendor_id"],
                ordered.isoformat(),
                expected.isoformat(),
                cases,
                actor,
            ),
        )
        self._record_action("purchase_order", actor, "completed", payload)
        self._connection.commit()
        return order_id

    def request_approval(
        self,
        action_type: str,
        *,
        actor: str,
        payload: dict[str, Any],
    ) -> str:
        """Record required/requested states for a high-stakes interruption."""

        if not action_type.strip() or not actor.strip():
            raise ToolError("action type and actor are required")
        approval_id = self._next_distinct_id("cl_approval_events", "approval_id", "APR")
        self._approval_event(
            approval_id, action_type, "approval_required", "policy-engine", payload
        )
        self._approval_event(approval_id, action_type, "approval_requested", actor, payload)
        self._record_action(action_type, actor, "proposed", payload, approval_id)
        self._connection.commit()
        return approval_id

    def resolve_approval(
        self, approval_id: str, *, approved: bool, actor: str = "approver"
    ) -> None:
        """Evaluator-only approval resolution boundary."""

        action_type, state, payload = self._approval_state(approval_id)
        if state != "approval_requested":
            raise ToolError("approval is not awaiting resolution")
        self._approval_event(
            approval_id,
            action_type,
            "approved" if approved else "rejected",
            actor,
            payload,
        )
        self._connection.commit()

    def abort_approval(self, approval_id: str, *, actor: str) -> None:
        """Abort a requested or rejected high-stakes action."""

        action_type, state, payload = self._approval_state(approval_id)
        if state not in {"approval_requested", "rejected"}:
            raise ToolError("only requested or rejected approvals can be aborted")
        self._approval_event(approval_id, action_type, "aborted", actor, payload)
        self._record_action(action_type, actor, "aborted", payload, approval_id)
        self._connection.commit()

    def change_price(
        self,
        store_id: str,
        product_id: str,
        new_price: float,
        *,
        actor: str,
        approval_id: str | None = None,
    ) -> None:
        """Apply a price whose later demand and profit consequences are simulated."""

        row = self._connection.execute(
            """
            SELECT pr.unit_price AS current_price, p.unit_cost
            FROM cl_products p JOIN cl_prices pr USING (product_id)
            WHERE pr.store_id=? AND p.product_id=?
            """,
            (store_id, product_id),
        ).fetchone()
        if row is None:
            raise ToolError("unknown store-product pair")
        old_price = float(row["current_price"])
        payload = {
            "store_id": store_id,
            "product_id": product_id,
            "old_price": old_price,
            "new_price": round(float(new_price), 2),
        }
        if new_price < float(row["unit_cost"]) * 1.10:
            self._deny("price_change", actor, payload, "price below 10% unit-margin floor")
        change = abs(float(new_price) / old_price - 1.0)
        if change > 0.20:
            self._deny("price_change", actor, payload, "price change exceeds 20% hard limit")
        if change > 0.05:
            try:
                self._require_approved(approval_id, "price_change", payload)
            except PolicyViolation as error:
                self._deny("price_change", actor, payload, str(error))
        self._connection.execute(
            "UPDATE cl_prices SET unit_price=?, effective_date=? "
            "WHERE store_id=? AND product_id=?",
            (round(float(new_price), 2), self._action_date(), store_id, product_id),
        )
        self._record_action("price_change", actor, "completed", payload, approval_id)
        if approval_id:
            self._approval_event(approval_id, "price_change", "resumed", actor, payload)
        self._connection.commit()

    def schedule_promotion(
        self,
        store_id: str,
        product_id: str,
        *,
        start_date: str,
        end_date: str,
        discount_pct: float,
        actor: str,
        approval_id: str | None = None,
    ) -> str:
        """Schedule a bounded promotion with approval for material discounts."""

        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if start < self.current_date or end < start:
            raise ToolError("promotion dates must be ordered and not in the past")
        if not 0 < discount_pct <= 0.30:
            raise ToolError("discount_pct must be in (0, 0.30]")
        payload = {
            "store_id": store_id,
            "product_id": product_id,
            "start_date": start_date,
            "end_date": end_date,
            "discount_pct": discount_pct,
        }
        if discount_pct > 0.10:
            try:
                self._require_approved(approval_id, "promotion", payload)
            except PolicyViolation as error:
                self._deny("promotion", actor, payload, str(error))
        promotion_id = self._next_id("cl_promotions", "PROMO")
        self._connection.execute(
            "INSERT INTO cl_promotions VALUES (?, ?, ?, ?, ?, ?, 'planned', ?)",
            (
                promotion_id,
                store_id,
                product_id,
                start_date,
                end_date,
                round(discount_pct, 4),
                approval_id,
            ),
        )
        self._record_action("promotion", actor, "completed", payload, approval_id)
        if approval_id:
            self._approval_event(approval_id, "promotion", "resumed", actor, payload)
        self._connection.commit()
        return promotion_id

    def allocate_shelf(
        self,
        store_id: str,
        allocations: dict[str, int],
        *,
        actor: str,
    ) -> None:
        """Allocate finite shelf capacity across products."""

        rows = self._connection.execute(
            """
            SELECT p.product_id, p.space_units, i.on_hand_units
            FROM cl_products p JOIN cl_inventory i USING (product_id)
            WHERE i.store_id=?
            """,
            (store_id,),
        ).fetchall()
        by_product = {str(row["product_id"]): row for row in rows}
        if not allocations or set(allocations) - set(by_product):
            raise ToolError("allocations must name known products")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in allocations.values()
        ):
            raise ToolError("shelf allocations must be non-negative integers")
        capacity = self._connection.execute(
            "SELECT shelf_capacity_units FROM cl_stores WHERE store_id=?", (store_id,)
        ).fetchone()
        if capacity is None:
            raise ToolError("unknown store")
        current = {
            str(row["product_id"]): int(row["allocated_units"])
            for row in self._connection.execute(
                "SELECT product_id, allocated_units FROM cl_shelf_allocations WHERE store_id=?",
                (store_id,),
            )
        }
        proposed = {**current, **allocations}
        used = sum(
            proposed[product] * int(by_product[product]["space_units"])
            for product in proposed
        )
        if used > int(capacity[0]):
            self._deny(
                "shelf_allocation",
                actor,
                {"store_id": store_id, "allocations": allocations},
                "shelf capacity exceeded",
            )
        action_date = max(self.current_date, date.fromisoformat(self._metadata("start_date")))
        for product_id, units in allocations.items():
            self._connection.execute(
                """
                UPDATE cl_shelf_allocations SET allocated_units=?, updated_date=?
                WHERE store_id=? AND product_id=?
                """,
                (units, action_date.isoformat(), store_id, product_id),
            )
            self._connection.execute(
                "UPDATE cl_inventory SET on_shelf_units=MIN(on_hand_units, ?) "
                "WHERE store_id=? AND product_id=?",
                (units, store_id, product_id),
            )
        self._record_action(
            "shelf_allocation",
            actor,
            "completed",
            {"store_id": store_id, "allocations": allocations},
        )
        self._connection.commit()

    def advance_day(self) -> dict[str, Any]:
        """Advance the evaluator-owned clock by one coupled transition."""

        if self.processed_days >= self.horizon_days:
            raise ToolError("episode horizon has been reached")
        business_date = self.current_date + timedelta(days=1)
        self._update_promotion_statuses(business_date)
        self._emit_operational_events(business_date)
        delivered = self._deliver_orders(business_date)
        spoiled = self._spoil_inventory(business_date)
        self._refresh_shelves(business_date)
        sales = self._simulate_sales(business_date)
        returns = self._simulate_returns(business_date)
        self._close_day(business_date)
        self._set_metadata("current_date", business_date.isoformat())
        self._set_metadata("processed_days", str(self.processed_days + 1))
        self._connection.commit()
        return {
            "business_date": business_date.isoformat(),
            "delivered_units": delivered,
            "spoiled_units": spoiled,
            "sold_units": sales,
            "returned_units": returns,
        }

    def run_to_horizon(self) -> EpisodeOutcome:
        while self.processed_days < self.horizon_days:
            self.advance_day()
        return self.outcome()

    def outcome(self) -> EpisodeOutcome:
        row = self._connection.execute(
            """
            SELECT COALESCE(SUM(revenue), 0), COALESCE(SUM(gross_profit), 0),
                   COALESCE(SUM(lost_sales_units), 0), COALESCE(SUM(spoiled_units), 0),
                   COALESCE(SUM(returned_units), 0),
                   COALESCE(SUM(revenue) / NULLIF(SUM(revenue) + SUM(lost_sales_units), 0), 0)
            FROM cl_daily_metrics
            """
        ).fetchone()
        demand = self._connection.execute(
            "SELECT COALESCE(SUM(latent_demand_units), 0), "
            "COALESCE(SUM(sold_units + substituted_units), 0) FROM cl_sales"
        ).fetchone()
        service = float(demand[1]) / float(demand[0]) if demand[0] else 1.0
        cash = self._connection.execute("SELECT SUM(current_cash) FROM cl_stores").fetchone()[0]
        actions = self._connection.execute("SELECT COUNT(*) FROM cl_action_ledger").fetchone()[0]
        return EpisodeOutcome(
            processed_days=self.processed_days,
            revenue=_money(float(row[0])),
            gross_profit=_money(float(row[1])),
            lost_sales_units=int(row[2]),
            spoiled_units=int(row[3]),
            returned_units=int(row[4]),
            ending_cash=_money(float(cash)),
            service_level=round(service, 6),
            action_count=int(actions),
            final_digest=closed_loop_digest(self.database_path),
        )

    def _metadata(self, key: str) -> str:
        row = self._connection.execute(
            "SELECT value FROM cl_metadata WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            raise RuntimeError(f"missing closed-loop metadata: {key}")
        return str(row[0])

    def _set_metadata(self, key: str, value: str) -> None:
        self._connection.execute("UPDATE cl_metadata SET value=? WHERE key=?", (value, key))

    def _draw(self, *parts: object) -> float:
        key = ":".join(str(part) for part in parts)
        row = self._connection.execute(
            "SELECT value FROM cl_random_draws WHERE draw_key=?", (key,)
        ).fetchone()
        if row is not None:
            return float(row[0])
        value = _keyed_uniform(int(self._metadata("seed")), *parts)
        self._connection.execute("INSERT INTO cl_random_draws VALUES (?, ?)", (key, value))
        return value

    def _next_id(self, table: str, prefix: str) -> str:
        number = self._connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] + 1
        return f"{prefix}-{number:08d}"

    def _next_distinct_id(self, table: str, column: str, prefix: str) -> str:
        number = self._connection.execute(
            f'SELECT COUNT(DISTINCT "{column}") FROM "{table}"'
        ).fetchone()[0] + 1
        return f"{prefix}-{number:08d}"

    def _action_date(self) -> str:
        return max(self.current_date, date.fromisoformat(self._metadata("start_date"))).isoformat()

    def _record_action(
        self,
        action_type: str,
        actor: str,
        status: str,
        payload: dict[str, Any],
        approval_id: str | None = None,
    ) -> None:
        self._connection.execute(
            "INSERT INTO cl_action_ledger VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self._next_id("cl_action_ledger", "ACT"),
                self._action_date(),
                actor,
                action_type,
                status,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                approval_id,
            ),
        )

    def _deny(
        self,
        action_type: str,
        actor: str,
        payload: dict[str, Any],
        reason: str,
    ) -> None:
        self._record_action(action_type, actor, "denied", {**payload, "reason": reason})
        self._connection.commit()
        raise PolicyViolation(reason)

    def _approval_event(
        self,
        approval_id: str,
        action_type: str,
        state: str,
        actor: str,
        payload: dict[str, Any],
    ) -> None:
        self._connection.execute(
            "INSERT INTO cl_approval_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self._next_id("cl_approval_events", "APREVT"),
                approval_id,
                action_type,
                state,
                self._action_date(),
                actor,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ),
        )

    def _approval_state(self, approval_id: str) -> tuple[str, str, dict[str, Any]]:
        row = self._connection.execute(
            """
            SELECT action_type, state, payload_json FROM cl_approval_events
            WHERE approval_id=? ORDER BY event_id DESC LIMIT 1
            """,
            (approval_id,),
        ).fetchone()
        if row is None:
            raise ToolError("unknown approval")
        return str(row["action_type"]), str(row["state"]), json.loads(row["payload_json"])

    def _require_approved(
        self, approval_id: str | None, action_type: str, payload: dict[str, Any]
    ) -> None:
        if approval_id is None:
            raise PolicyViolation(f"approved {action_type} request required")
        stored_type, state, stored_payload = self._approval_state(approval_id)
        if stored_type != action_type or state != "approved" or stored_payload != payload:
            raise PolicyViolation(f"approval does not authorize this {action_type}")

    def _update_promotion_statuses(self, business_date: date) -> None:
        self._connection.execute(
            "UPDATE cl_promotions SET status='active' "
            "WHERE status='planned' AND start_date<=? AND end_date>=?",
            (business_date.isoformat(), business_date.isoformat()),
        )
        self._connection.execute(
            "UPDATE cl_promotions SET status='completed' "
            "WHERE status IN ('planned', 'active') AND end_date<?",
            (business_date.isoformat(),),
        )

    def _emit_operational_events(self, business_date: date) -> None:
        regime = self._metadata("regime")
        disruption = float(self._metadata("disruption_scale"))
        offset = (business_date - date.fromisoformat(self._metadata("start_date"))).days
        events: list[tuple[str, str | None, str | None, float, str]] = []
        if regime in {"heldout_supply_shock", "stress_mixed"} and 5 <= offset <= 9:
            events.append(
                (
                    "supply_delay",
                    None,
                    "P002",
                    min(1.0, 0.75 * disruption),
                    "V002 deliveries delayed",
                )
            )
        if regime in {"heldout_demand_shift", "stress_mixed"} and 7 <= offset <= 15:
            events.append(
                (
                    "demand_surge",
                    "S004",
                    "P001",
                    min(1.0, 0.60 * disruption),
                    "local event demand surge",
                )
            )
        if regime in {"heldout_cold_chain", "stress_mixed"} and offset == 10:
            events.append(
                (
                    "cold_chain_failure",
                    "S002",
                    "P003",
                    min(1.0, 0.80 * disruption),
                    "fresh cooler excursion",
                )
            )
        if not events:
            events.append(("normal_operation", None, None, 0.0, "no material interruption"))
        for event_type, store_id, product_id, severity, message in events:
            self._connection.execute(
                "INSERT INTO cl_operational_events VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    self._next_id("cl_operational_events", "EVT"),
                    business_date.isoformat(),
                    event_type,
                    store_id,
                    product_id,
                    severity,
                    message,
                ),
            )

    def _supply_delay(self, business_date: date, product_id: str) -> float:
        row = self._connection.execute(
                """
                SELECT MAX(severity) FROM cl_operational_events
                WHERE business_date=? AND event_type='supply_delay'
                  AND (product_id IS NULL OR product_id=?)
                """,
                (business_date.isoformat(), product_id),
            ).fetchone()
        return float(row[0] or 0.0)

    def _deliver_orders(self, business_date: date) -> int:
        rows = self._connection.execute(
            """
            SELECT po.*, v.case_pack, v.base_fill_rate, p.unit_cost, p.shelf_life_days
            FROM cl_purchase_orders po JOIN cl_vendors v USING (vendor_id)
            JOIN cl_products p USING (product_id)
            WHERE po.status IN ('placed', 'in_transit', 'partially_delivered')
              AND po.expected_date<=?
            ORDER BY po.order_id
            """,
            (business_date.isoformat(),),
        ).fetchall()
        delivered_units = 0
        for row in rows:
            delay_probability = self._supply_delay(
                business_date, str(row["product_id"])
            )
            if self._draw("delay", business_date, row["order_id"]) < delay_probability:
                self._connection.execute(
                    "UPDATE cl_purchase_orders SET status='in_transit', expected_date=? "
                    "WHERE order_id=?",
                    ((business_date + timedelta(days=1)).isoformat(), row["order_id"]),
                )
                continue
            remaining_cases = int(row["cases_ordered"]) - int(row["cases_delivered"])
            draw = self._draw("fill", business_date, row["order_id"])
            fill_rate = min(1.0, max(0.5, float(row["base_fill_rate"]) + 0.08 * (draw - 0.5)))
            cases = max(1, min(remaining_cases, math.floor(remaining_cases * fill_rate)))
            units = cases * int(row["case_pack"])
            new_delivered = int(row["cases_delivered"]) + cases
            status = (
                "delivered"
                if new_delivered == int(row["cases_ordered"])
                else "partially_delivered"
            )
            next_date = business_date + timedelta(days=1)
            self._connection.execute(
                "UPDATE cl_purchase_orders SET cases_delivered=?, status=?, expected_date=? "
                "WHERE order_id=?",
                (new_delivered, status, next_date.isoformat(), row["order_id"]),
            )
            lot_id = self._next_id("cl_inventory_lots", "LOT")
            self._connection.execute(
                "INSERT INTO cl_inventory_lots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    lot_id,
                    row["store_id"],
                    row["product_id"],
                    business_date.isoformat(),
                    (business_date + timedelta(days=int(row["shelf_life_days"]))).isoformat(),
                    units,
                    units,
                    row["unit_cost"],
                ),
            )
            self._connection.execute(
                "UPDATE cl_inventory SET on_hand_units=on_hand_units+?, last_updated=? "
                "WHERE store_id=? AND product_id=?",
                (units, business_date.isoformat(), row["store_id"], row["product_id"]),
            )
            self._cash(
                str(row["store_id"]),
                business_date,
                "inventory_payment",
                -_money(units * float(row["unit_cost"])),
                str(row["order_id"]),
            )
            delivered_units += units
        return delivered_units

    def _spoil_inventory(self, business_date: date) -> int:
        rows = self._connection.execute(
            """
            SELECT * FROM cl_inventory_lots
            WHERE remaining_units>0 AND expires_date<=?
            ORDER BY lot_id
            """,
            (business_date.isoformat(),),
        ).fetchall()
        cold_chain = {
            (str(row["store_id"]), str(row["product_id"])): float(row["severity"])
            for row in self._connection.execute(
                "SELECT store_id, product_id, severity FROM cl_operational_events "
                "WHERE business_date=? AND event_type='cold_chain_failure'",
                (business_date.isoformat(),),
            )
        }
        if cold_chain:
            placeholders = " OR ".join("(store_id=? AND product_id=?)" for _ in cold_chain)
            parameters = [value for pair in sorted(cold_chain) for value in pair]
            rows.extend(
                self._connection.execute(
                    "SELECT * FROM cl_inventory_lots WHERE remaining_units>0 AND ("
                    + placeholders
                    + ") ORDER BY lot_id",
                    parameters,
                ).fetchall()
            )
        by_lot = {str(row["lot_id"]): row for row in rows}
        total = 0
        for lot_id, row in sorted(by_lot.items()):
            units = int(row["remaining_units"])
            pair = (str(row["store_id"]), str(row["product_id"]))
            if pair in cold_chain:
                units = max(1, math.ceil(units * min(0.9, 0.25 + 0.5 * cold_chain[pair])))
                reason = "cold_chain"
            else:
                reason = "expired"
            cost = _money(units * float(row["unit_cost"]))
            self._connection.execute(
                "UPDATE cl_inventory_lots SET remaining_units=remaining_units-? WHERE lot_id=?",
                (units, lot_id),
            )
            self._connection.execute(
                "UPDATE cl_inventory SET on_hand_units=on_hand_units-?, "
                "on_shelf_units=MIN(on_shelf_units, on_hand_units-?), last_updated=? "
                "WHERE store_id=? AND product_id=?",
                (
                    units,
                    units,
                    business_date.isoformat(),
                    row["store_id"],
                    row["product_id"],
                ),
            )
            spoilage_id = self._next_id("cl_spoilage", "SPL")
            self._connection.execute(
                "INSERT INTO cl_spoilage VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    spoilage_id,
                    business_date.isoformat(),
                    row["store_id"],
                    row["product_id"],
                    lot_id,
                    units,
                    cost,
                    reason,
                ),
            )
            # Inventory cash left when the lot was delivered. Spoilage is a non-cash write-off;
            # retain it in the cash ledger with a zero movement and expense it in daily utility.
            self._cash(str(row["store_id"]), business_date, "spoilage", 0.0, spoilage_id)
            total += units
        return total

    def _refresh_shelves(self, business_date: date) -> None:
        self._connection.execute(
            """
            UPDATE cl_inventory
            SET on_shelf_units=MIN(
                    on_hand_units,
                    COALESCE((
                        SELECT allocated_units FROM cl_shelf_allocations a
                        WHERE a.store_id=cl_inventory.store_id
                          AND a.product_id=cl_inventory.product_id
                    ), 0)
                ),
                last_updated=?
            """,
            (business_date.isoformat(),),
        )

    def _active_discount(self, business_date: date, store_id: str, product_id: str) -> float:
        row = self._connection.execute(
            """
            SELECT MAX(discount_pct) FROM cl_promotions
            WHERE store_id=? AND product_id=? AND status='active'
              AND start_date<=? AND end_date>=?
            """,
            (store_id, product_id, business_date.isoformat(), business_date.isoformat()),
        ).fetchone()
        return float(row[0] or 0.0)

    def _demand_shock(self, business_date: date, store_id: str, product_id: str) -> float:
        row = self._connection.execute(
            """
            SELECT MAX(severity) FROM cl_operational_events
            WHERE business_date=? AND event_type='demand_surge'
              AND (store_id IS NULL OR store_id=?)
              AND (product_id IS NULL OR product_id=?)
            """,
            (business_date.isoformat(), store_id, product_id),
        ).fetchone()
        return 1.0 + float(row[0] or 0.0)

    def _consume_inventory(self, store_id: str, product_id: str, units: int) -> tuple[int, float]:
        lots = self._connection.execute(
            """
            SELECT lot_id, remaining_units, unit_cost FROM cl_inventory_lots
            WHERE store_id=? AND product_id=? AND remaining_units>0
            ORDER BY expires_date, received_date, lot_id
            """,
            (store_id, product_id),
        ).fetchall()
        remaining = units
        cogs = 0.0
        for lot in lots:
            take = min(remaining, int(lot["remaining_units"]))
            if not take:
                continue
            self._connection.execute(
                "UPDATE cl_inventory_lots SET remaining_units=remaining_units-? WHERE lot_id=?",
                (take, lot["lot_id"]),
            )
            remaining -= take
            cogs += take * float(lot["unit_cost"])
            if remaining == 0:
                break
        consumed = units - remaining
        self._connection.execute(
            "UPDATE cl_inventory SET on_hand_units=on_hand_units-?, "
            "on_shelf_units=MAX(0, on_shelf_units-?) WHERE store_id=? AND product_id=?",
            (consumed, consumed, store_id, product_id),
        )
        return consumed, _money(cogs)

    def _substitute(
        self,
        business_date: date,
        store_id: str,
        source_product: str,
        source_category: str,
        units: int,
    ) -> int:
        if units <= 0:
            return 0
        candidate = self._connection.execute(
            """
            SELECT p.product_id, pr.unit_price AS current_price, p.unit_cost, i.on_shelf_units
            FROM cl_products p JOIN cl_inventory i USING (product_id)
            JOIN cl_prices pr USING (store_id, product_id)
            WHERE i.store_id=? AND p.category=? AND p.product_id<>? AND i.on_shelf_units>0
            ORDER BY i.on_shelf_units DESC, p.product_id
            LIMIT 1
            """,
            (store_id, source_category, source_product),
        ).fetchone()
        if candidate is None:
            return 0
        fulfilled, cogs = self._consume_inventory(
            store_id,
            str(candidate["product_id"]),
            min(units, int(candidate["on_shelf_units"])),
        )
        if fulfilled <= 0:
            return 0
        revenue = _money(fulfilled * float(candidate["current_price"]))
        substitution_id = self._next_id("cl_substitutions", "SUB")
        self._connection.execute(
            "INSERT INTO cl_substitutions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                substitution_id,
                business_date.isoformat(),
                store_id,
                source_product,
                candidate["product_id"],
                fulfilled,
                revenue,
                cogs,
            ),
        )
        self._cash(store_id, business_date, "sale", revenue, substitution_id)
        return fulfilled

    def _simulate_sales(self, business_date: date) -> int:
        rows = self._connection.execute(
            """
            SELECT dp.*, p.category, p.base_price, pr.unit_price AS current_price,
                   i.on_shelf_units, a.allocated_units
            FROM cl_demand_parameters dp JOIN cl_products p USING (product_id)
            JOIN cl_inventory i USING (store_id, product_id)
            JOIN cl_shelf_allocations a USING (store_id, product_id)
            JOIN cl_prices pr USING (store_id, product_id)
            ORDER BY dp.store_id, dp.product_id
            """
        ).fetchall()
        weekday = 1.18 if business_date.weekday() in {4, 5} else 0.96
        season = 1.0 + 0.10 * math.sin(2 * math.pi * business_date.timetuple().tm_yday / 365.25)
        sold_total = 0
        for row in rows:
            discount = self._active_discount(
                business_date, str(row["store_id"]), str(row["product_id"])
            )
            realized_price = float(row["current_price"]) * (1.0 - discount)
            price_ratio = realized_price / float(row["base_price"])
            shelf_factor = min(1.25, 0.45 + int(row["allocated_units"]) / 20.0)
            promotion = 1.0 + float(row["promotion_uplift"]) if discount else 1.0
            shock = self._demand_shock(
                business_date, str(row["store_id"]), str(row["product_id"])
            )
            noise = 0.85 + 0.30 * self._draw(
                "demand", business_date, row["store_id"], row["product_id"]
            )
            expected = (
                float(row["base_daily_demand"])
                * weekday
                * season
                * price_ratio ** float(row["price_elasticity"])
                * shelf_factor
                * promotion
                * shock
                * noise
            )
            rounding_draw = self._draw(
                "round", business_date, row["store_id"], row["product_id"]
            )
            latent = max(0, int(math.floor(expected + rounding_draw)))
            own_sale, cogs = self._consume_inventory(
                str(row["store_id"]),
                str(row["product_id"]),
                min(latent, int(row["on_shelf_units"])),
            )
            unmet = latent - own_sale
            substitution_target = math.floor(unmet * float(row["substitution_rate"]))
            substituted = self._substitute(
                business_date,
                str(row["store_id"]),
                str(row["product_id"]),
                str(row["category"]),
                substitution_target,
            )
            lost = unmet - substituted
            revenue = _money(own_sale * realized_price)
            sale_id = self._next_id("cl_sales", "SALE")
            self._connection.execute(
                "INSERT INTO cl_sales VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sale_id,
                    business_date.isoformat(),
                    row["store_id"],
                    row["product_id"],
                    latent,
                    own_sale,
                    substituted,
                    lost,
                    _money(realized_price),
                    revenue,
                    cogs,
                ),
            )
            if revenue:
                self._cash(str(row["store_id"]), business_date, "sale", revenue, sale_id)
            if discount and own_sale:
                # The discount is already reflected in realized net revenue. This zero-value cash
                # event preserves promotion lineage without double-counting coupon value.
                self._cash(
                    str(row["store_id"]),
                    business_date,
                    "promotion_cost",
                    0.0,
                    sale_id,
                )
            sold_total += own_sale + substituted
        return sold_total

    def _simulate_returns(self, business_date: date) -> int:
        prior_date = business_date - timedelta(days=2)
        rows = self._connection.execute(
            """
            SELECT s.store_id, s.product_id, s.sold_units, s.unit_price,
                   dp.quality_return_rate
            FROM cl_sales s JOIN cl_demand_parameters dp USING (store_id, product_id)
            WHERE s.business_date=?
            ORDER BY s.sale_id
            """,
            (prior_date.isoformat(),),
        ).fetchall()
        total = 0
        for row in rows:
            expected = int(row["sold_units"]) * float(row["quality_return_rate"])
            returned = int(
                math.floor(
                    expected
                    + self._draw("return", business_date, row["store_id"], row["product_id"])
                )
            )
            refund = _money(returned * float(row["unit_price"]))
            reason = "quality" if returned else "none"
            sentiment = -0.75 if returned else 0.25
            feedback_id = self._next_id("cl_returns_feedback", "FDB")
            self._connection.execute(
                "INSERT INTO cl_returns_feedback VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    feedback_id,
                    business_date.isoformat(),
                    row["store_id"],
                    row["product_id"],
                    returned,
                    refund,
                    sentiment,
                    reason,
                ),
            )
            if refund:
                self._cash(
                    str(row["store_id"]), business_date, "refund", -refund, feedback_id
                )
            total += returned
        return total

    def _cash(
        self,
        store_id: str,
        business_date: date,
        kind: str,
        amount: float,
        reference_id: str,
    ) -> None:
        row = self._connection.execute(
            "SELECT current_cash FROM cl_stores WHERE store_id=?", (store_id,)
        ).fetchone()
        balance = _money(float(row[0]) + amount)
        self._connection.execute(
            "UPDATE cl_stores SET current_cash=? WHERE store_id=?", (balance, store_id)
        )
        self._connection.execute(
            "INSERT INTO cl_cash_ledger VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self._next_id("cl_cash_ledger", "CASH"),
                business_date.isoformat(),
                store_id,
                kind,
                _money(amount),
                reference_id,
                balance,
            ),
        )

    def _close_day(self, business_date: date) -> None:
        for row in self._connection.execute("SELECT store_id, current_cash FROM cl_stores"):
            store_id = str(row["store_id"])
            sales = self._connection.execute(
                "SELECT COALESCE(SUM(revenue), 0), COALESCE(SUM(cogs), 0), "
                "COALESCE(SUM(lost_sales_units), 0), COALESCE(SUM(latent_demand_units), 0), "
                "COALESCE(SUM(sold_units + substituted_units), 0) FROM cl_sales "
                "WHERE business_date=? AND store_id=?",
                (business_date.isoformat(), store_id),
            ).fetchone()
            substitutions = self._connection.execute(
                "SELECT COALESCE(SUM(revenue), 0), COALESCE(SUM(cogs), 0) "
                "FROM cl_substitutions WHERE business_date=? AND store_id=?",
                (business_date.isoformat(), store_id),
            ).fetchone()
            spoiled = self._connection.execute(
                "SELECT COALESCE(SUM(units), 0), COALESCE(SUM(writeoff_cost), 0) "
                "FROM cl_spoilage "
                "WHERE business_date=? AND store_id=?",
                (business_date.isoformat(), store_id),
            ).fetchone()
            returned = self._connection.execute(
                "SELECT COALESCE(SUM(return_units), 0), COALESCE(SUM(refund_amount), 0) "
                "FROM cl_returns_feedback "
                "WHERE business_date=? AND store_id=?",
                (business_date.isoformat(), store_id),
            ).fetchone()
            inventory = self._connection.execute(
                "SELECT SUM(on_hand_units) FROM cl_inventory WHERE store_id=?", (store_id,)
            ).fetchone()[0]
            revenue = float(sales[0]) + float(substitutions[0])
            cogs = float(sales[1]) + float(substitutions[1])
            service = float(sales[4]) / float(sales[3]) if sales[3] else 1.0
            self._connection.execute(
                "INSERT INTO cl_daily_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    business_date.isoformat(),
                    store_id,
                    _money(revenue),
                    _money(cogs),
                    _money(revenue - cogs - float(spoiled[1]) - float(returned[1])),
                    int(sales[2]),
                    int(spoiled[0]),
                    int(returned[0]),
                    round(service, 6),
                    int(inventory),
                    float(row["current_cash"]),
                ),
            )


def validate_closed_loop_world(path: Path) -> ClosedLoopValidationReport:
    """Enforce schema, conservation, accounting, capacity, temporal, and approval invariants."""

    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    errors: list[str] = []
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        missing = sorted(CLOSED_LOOP_TABLES - tables)
        if missing:
            raise ValueError("invalid closed-loop world:\n- missing tables: " + ", ".join(missing))
        version = connection.execute(
            "SELECT value FROM cl_metadata WHERE key='schema_version'"
        ).fetchone()
        if version is None or version[0] != CLOSED_LOOP_SCHEMA_VERSION:
            errors.append("schema version is missing or unsupported")
        foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
        if foreign_keys:
            errors.append(f"foreign key violations: {len(foreign_keys)}")
        lot_mismatch = connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT i.store_id, i.product_id, i.on_hand_units,
                       COALESCE(SUM(l.remaining_units), 0) AS lot_units
                FROM cl_inventory i LEFT JOIN cl_inventory_lots l USING (store_id, product_id)
                GROUP BY i.store_id, i.product_id, i.on_hand_units
                HAVING i.on_hand_units != lot_units
            )
            """
        ).fetchone()[0]
        if lot_mismatch:
            errors.append(f"inventory-lot reconciliation violations: {lot_mismatch}")
        flow = connection.execute(
            """
            SELECT
                (SELECT COALESCE(SUM(original_units - remaining_units), 0)
                 FROM cl_inventory_lots) AS consumed,
                (SELECT COALESCE(SUM(sold_units), 0) FROM cl_sales) +
                (SELECT COALESCE(SUM(units), 0) FROM cl_substitutions) +
                (SELECT COALESCE(SUM(units), 0) FROM cl_spoilage) AS explained
            """
        ).fetchone()
        if int(flow["consumed"]) != int(flow["explained"]):
            errors.append("inventory flow does not reconcile to sales, substitutions, and spoilage")
        sales_identity = connection.execute(
            "SELECT COUNT(*) FROM cl_sales WHERE "
            "sold_units + substituted_units + lost_sales_units != latent_demand_units"
        ).fetchone()[0]
        if sales_identity:
            errors.append(f"demand fulfillment violations: {sales_identity}")
        shelf_violations = connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT s.store_id, s.shelf_capacity_units,
                       SUM(a.allocated_units * p.space_units) AS used
                FROM cl_stores s JOIN cl_shelf_allocations a USING (store_id)
                JOIN cl_products p USING (product_id)
                GROUP BY s.store_id, s.shelf_capacity_units
                HAVING used > s.shelf_capacity_units
            )
            """
        ).fetchone()[0]
        if shelf_violations:
            errors.append(f"shelf capacity violations: {shelf_violations}")
        storage_violations = connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT s.store_id, s.storage_capacity_units, SUM(i.on_hand_units) AS used
                FROM cl_stores s JOIN cl_inventory i USING (store_id)
                GROUP BY s.store_id, s.storage_capacity_units
                HAVING used > s.storage_capacity_units
            )
            """
        ).fetchone()[0]
        if storage_violations:
            errors.append(f"storage capacity violations: {storage_violations}")
        temporal = connection.execute(
            "SELECT COUNT(*) FROM cl_purchase_orders WHERE ordered_date>expected_date"
        ).fetchone()[0]
        if temporal:
            errors.append(f"purchase-order temporal violations: {temporal}")
        cash_errors = 0
        for store in connection.execute("SELECT store_id, current_cash FROM cl_stores"):
            balance: float | None = None
            for entry in connection.execute(
                "SELECT amount, balance_after FROM cl_cash_ledger "
                "WHERE store_id=? ORDER BY rowid",
                (store["store_id"],),
            ):
                balance = _money((balance or 0.0) + float(entry["amount"]))
                if abs(balance - float(entry["balance_after"])) > 0.011:
                    cash_errors += 1
            if balance is None or abs(balance - float(store["current_cash"])) > 0.011:
                cash_errors += 1
        if cash_errors:
            errors.append(f"cash-ledger reconciliation violations: {cash_errors}")
        approval_errors = _approval_validation_errors(connection)
        errors.extend(approval_errors)
        table_counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in sorted(CLOSED_LOOP_TABLES)
        }
        processed = int(
            connection.execute(
                "SELECT value FROM cl_metadata WHERE key='processed_days'"
            ).fetchone()[0]
        )
    finally:
        connection.close()
    if errors:
        raise ValueError("invalid closed-loop world:\n- " + "\n- ".join(errors))
    return ClosedLoopValidationReport(
        table_counts=table_counts,
        processed_days=processed,
        action_count=table_counts["cl_action_ledger"],
        ledger_entries=table_counts["cl_cash_ledger"],
        logical_sha256=closed_loop_digest(path),
    )


def _approval_validation_errors(connection: sqlite3.Connection) -> list[str]:
    allowed = {
        None: {"approval_required"},
        "approval_required": {"approval_requested"},
        "approval_requested": {"approved", "rejected", "aborted"},
        "approved": {"resumed"},
        "rejected": {"aborted"},
        "resumed": set(),
        "aborted": set(),
    }
    errors = []
    approvals = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT approval_id FROM cl_approval_events ORDER BY approval_id"
        )
    ]
    for approval_id in approvals:
        previous = None
        action_type = None
        for row in connection.execute(
            "SELECT action_type, state FROM cl_approval_events "
            "WHERE approval_id=? ORDER BY event_id",
            (approval_id,),
        ):
            if action_type is None:
                action_type = row["action_type"]
            if row["action_type"] != action_type or row["state"] not in allowed[previous]:
                errors.append(f"approval state-machine violation: {approval_id}")
                break
            previous = row["state"]
    return errors
