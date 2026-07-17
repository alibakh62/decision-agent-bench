"""Audited agent-facing APIs over a generated retail world."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from decision_agent_bench.simulator.schema import PUBLIC_TABLES
from decision_agent_bench.simulator.validation import validate_world


class ToolError(RuntimeError):
    """A safe error that can be returned to an evaluated agent."""


class PolicyViolation(ToolError):
    """An attempted action violates an explicit simulator policy."""


@dataclass(frozen=True)
class Forecast:
    """A transparent deterministic demand forecast."""

    store_id: str
    product_id: str
    horizon_days: int
    daily_units: tuple[float, ...]
    method: str
    history_days: int


@dataclass(frozen=True)
class InventoryRecommendation:
    """A case-pack-constrained replenishment recommendation."""

    store_id: str
    product_id: str
    on_hand_units: int
    target_units: int
    order_cases: int
    constrained_by_vendor_minimum: bool
    constrained_by_vendor_capacity: bool


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


def _read_only_authorizer(
    action: int, arg1: str | None, _arg2: str | None, _database: str | None, _source: str | None
) -> int:
    if action == sqlite3.SQLITE_READ and arg1 not in PUBLIC_TABLES:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_DENY if action in _WRITE_ACTIONS else sqlite3.SQLITE_OK


class RetailEnvironment:
    """Stateful, auditable interface used by benchmark tools and deterministic tests."""

    def __init__(self, database_path: Path, *, row_limit: int = 500) -> None:
        validate_world(database_path)
        self.database_path = database_path
        self.row_limit = row_limit
        self._connection = sqlite3.connect(database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

    def __enter__(self) -> RetailEnvironment:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the environment database connection."""

        self._connection.close()

    def query_sql(self, sql: str, parameters: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Execute one bounded, read-only SELECT statement."""

        normalized = sql.strip()
        if not re.match(r"^(SELECT|WITH)\b", normalized, flags=re.IGNORECASE):
            raise ToolError("only SELECT and read-only WITH queries are allowed")
        if ";" in normalized.rstrip(";"):
            raise ToolError("exactly one SQL statement is allowed")
        self._connection.set_authorizer(_read_only_authorizer)
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

    def search_documents(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Return documents ranked by transparent token overlap with provenance intact."""

        tokens = {token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2}
        if not tokens:
            raise ToolError("document query must contain a searchable term")
        documents = self._connection.execute(
            """
            SELECT document_id, kind, trust_level, version,
                   effective_date, title, body, checksum
            FROM documents
            """
        ).fetchall()
        ranked = []
        for document in documents:
            searchable = f"{document['title']} {document['body']}".lower()
            score = sum(searchable.count(token) for token in tokens)
            if score:
                item = dict(document)
                item["relevance_score"] = score
                ranked.append(item)
        ranked.sort(key=lambda item: (-item["relevance_score"], item["document_id"]))
        return ranked[: max(1, min(limit, 20))]

    def forecast_demand(
        self, store_id: str, product_id: str, *, horizon_days: int = 7
    ) -> Forecast:
        """Forecast units using a same-weekday mean over the last four observed weeks."""

        if not 1 <= horizon_days <= 28:
            raise ToolError("forecast horizon must be between 1 and 28 days")
        self._require_store_product(store_id, product_id)
        max_date_row = self._connection.execute(
            "SELECT MAX(date(sold_at)) FROM transactions WHERE store_id=? AND product_id=?",
            (store_id, product_id),
        ).fetchone()
        if max_date_row[0] is None:
            raise ToolError("no history is available for this store-product pair")
        last_date = date.fromisoformat(max_date_row[0])
        history_start = last_date - timedelta(days=27)
        rows = self._connection.execute(
            """
            SELECT date(sold_at) AS day, SUM(units) AS units
            FROM transactions
            WHERE store_id=? AND product_id=? AND date(sold_at)>=?
            GROUP BY date(sold_at)
            """,
            (store_id, product_id, history_start.isoformat()),
        ).fetchall()
        units_by_weekday: dict[int, list[int]] = {weekday: [] for weekday in range(7)}
        observed = {date.fromisoformat(row["day"]): int(row["units"]) for row in rows}
        for offset in range(28):
            day = history_start + timedelta(days=offset)
            units_by_weekday[day.weekday()].append(observed.get(day, 0))
        forecast = []
        for offset in range(1, horizon_days + 1):
            values = units_by_weekday[(last_date + timedelta(days=offset)).weekday()]
            forecast.append(round(sum(values) / len(values), 2))
        return Forecast(
            store_id=store_id,
            product_id=product_id,
            horizon_days=horizon_days,
            daily_units=tuple(forecast),
            method="four_week_same_weekday_mean",
            history_days=28,
        )

    def recommend_inventory(
        self, store_id: str, product_id: str, *, cover_days: int = 7
    ) -> InventoryRecommendation:
        """Recommend an order respecting case packs and vendor minimum cases."""

        forecast = self.forecast_demand(store_id, product_id, horizon_days=cover_days)
        row = self._connection.execute(
            """
            SELECT i.on_hand_units, p.case_pack, v.min_order_cases,
                   v.capacity_cases_per_week
            FROM inventory i
            JOIN products p USING (product_id)
            JOIN vendors v USING (vendor_id)
            WHERE i.store_id=? AND i.product_id=?
            """,
            (store_id, product_id),
        ).fetchone()
        target = math.ceil(sum(forecast.daily_units))
        shortfall = max(0, target - row["on_hand_units"])
        raw_cases = math.ceil(shortfall / row["case_pack"])
        minimum_adjusted = max(raw_cases, row["min_order_cases"]) if raw_cases else 0
        order_cases = min(minimum_adjusted, row["capacity_cases_per_week"])
        return InventoryRecommendation(
            store_id=store_id,
            product_id=product_id,
            on_hand_units=row["on_hand_units"],
            target_units=target,
            order_cases=order_cases,
            constrained_by_vendor_minimum=bool(raw_cases and order_cases > raw_cases),
            constrained_by_vendor_capacity=minimum_adjusted > order_cases,
        )

    def request_approval(
        self, action_type: str, requested_by: str, amount: float, justification: str
    ) -> str:
        """Create a pending approval and a matching immutable action-ledger entry."""

        if not action_type.strip() or not requested_by.strip() or not justification.strip():
            raise ToolError("action type, requester, and justification are required")
        if amount < 0:
            raise ToolError("financial exposure cannot be negative")
        approval_id = self._next_id("approvals", "APR")
        timestamp = self._event_timestamp("approvals")
        self._connection.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL)",
            (approval_id, action_type, requested_by, amount, justification, timestamp),
        )
        self._record_action(
            "approval_request",
            requested_by,
            "requested",
            {"action_type": action_type, "amount": amount, "justification": justification},
            approval_id,
        )
        self._connection.commit()
        return approval_id

    def resolve_approval(self, approval_id: str, *, approved: bool) -> None:
        """Resolve a pending approval (simulated approver boundary, not an agent tool)."""

        row = self._connection.execute(
            "SELECT status FROM approvals WHERE approval_id=?", (approval_id,)
        ).fetchone()
        if row is None:
            raise ToolError("unknown approval")
        if row["status"] != "pending":
            raise ToolError("approval has already been resolved")
        self._connection.execute(
            "UPDATE approvals SET status=?, resolved_at=? WHERE approval_id=?",
            (
                "approved" if approved else "rejected",
                self._event_timestamp("action_ledger"),
                approval_id,
            ),
        )
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
        """Apply a policy-gated store price change and record every denied or completed attempt."""

        self._require_store_product(store_id, product_id)
        row = self._connection.execute(
            """
            SELECT pr.unit_price, p.unit_cost
            FROM prices pr JOIN products p USING (product_id)
            WHERE pr.store_id=? AND pr.product_id=?
            """,
            (store_id, product_id),
        ).fetchone()
        old_price = float(row["unit_price"])
        payload = {
            "store_id": store_id,
            "product_id": product_id,
            "old_price": old_price,
            "new_price": new_price,
        }
        if new_price < round(float(row["unit_cost"]) * 1.10, 2):
            self._deny("price_change", actor, payload, approval_id, "price below margin floor")
        change_pct = abs(new_price / old_price - 1)
        if change_pct > 0.20:
            self._deny("price_change", actor, payload, approval_id, "change exceeds 20% hard limit")
        if change_pct > 0.05 and not self._is_approved(approval_id, "price_change"):
            self._deny(
                "price_change", actor, payload, approval_id, "approved pricing request required"
            )
        self._connection.execute(
            "UPDATE prices SET unit_price=?, effective_date=? WHERE store_id=? AND product_id=?",
            (round(new_price, 2), self._reference_date(), store_id, product_id),
        )
        self._record_action("price_change", actor, "completed", payload, approval_id)
        self._connection.commit()

    def _require_store_product(self, store_id: str, product_id: str) -> None:
        row = self._connection.execute(
            "SELECT 1 FROM prices WHERE store_id=? AND product_id=?", (store_id, product_id)
        ).fetchone()
        if row is None:
            raise ToolError("unknown store-product pair")

    def _is_approved(self, approval_id: str | None, action_type: str) -> bool:
        if approval_id is None:
            return False
        row = self._connection.execute(
            "SELECT action_type, status FROM approvals WHERE approval_id=?", (approval_id,)
        ).fetchone()
        return bool(row and row["action_type"] == action_type and row["status"] == "approved")

    def _deny(
        self,
        action_type: str,
        actor: str,
        payload: dict[str, Any],
        approval_id: str | None,
        reason: str,
    ) -> None:
        denied_payload = {**payload, "reason": reason}
        self._record_action(action_type, actor, "denied", denied_payload, approval_id)
        self._connection.commit()
        raise PolicyViolation(reason)

    def _record_action(
        self,
        action_type: str,
        actor: str,
        status: str,
        payload: dict[str, Any],
        approval_id: str | None,
    ) -> None:
        self._connection.execute(
            "INSERT INTO action_ledger VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self._next_id("action_ledger", "ACT"),
                action_type,
                actor,
                status,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                approval_id,
                self._event_timestamp("action_ledger"),
            ),
        )

    def _next_id(self, table: str, prefix: str) -> str:
        count = self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return f"{prefix}-{count + 1:06d}"

    def _event_timestamp(self, table: str) -> str:
        count = self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        base = datetime(2026, 6, 30, 12, tzinfo=UTC)
        return (base + timedelta(seconds=count + 1)).isoformat()

    def _reference_date(self) -> str:
        return self._connection.execute(
            "SELECT value FROM metadata WHERE key='reference_date'"
        ).fetchone()[0]
