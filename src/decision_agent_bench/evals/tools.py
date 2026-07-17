"""Inspect tool adapters with evidence lineage and recovery telemetry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from inspect_ai.tool import Tool, ToolError, tool
from inspect_ai.util import store

from decision_agent_bench.evals.runtime import STORE_PREFIX
from decision_agent_bench.simulator import RetailEnvironment
from decision_agent_bench.simulator.environment import (
    PolicyViolation,
)
from decision_agent_bench.simulator.environment import (
    ToolError as SimulatorToolError,
)


def _database_path() -> Path:
    value = store().get(f"{STORE_PREFIX}database_path")
    if not value:
        raise ToolError("benchmark environment is not initialized")
    return Path(str(value))


def _calls() -> list[dict[str, Any]]:
    return list(store().get(f"{STORE_PREFIX}tool_calls", []))


def _set_calls(calls: list[dict[str, Any]]) -> None:
    store().set(f"{STORE_PREFIX}tool_calls", calls)


def _record_error(tool_name: str, arguments: dict[str, Any], message: str) -> None:
    calls = _calls()
    calls.append(
        {
            "index": len(calls) + 1,
            "tool": tool_name,
            "status": "error",
            "arguments": arguments,
            "error": message,
        }
    )
    _set_calls(calls)


def _maybe_inject_failure(tool_name: str, arguments: dict[str, Any]) -> None:
    failure_tool = store().get(f"{STORE_PREFIX}failure_tool")
    calls = _calls()
    already_failed = any(
        call["tool"] == tool_name and call["status"] == "error" for call in calls
    )
    if failure_tool == tool_name and not already_failed:
        message = "simulated transient tool failure; retry or use a defensible fallback"
        _record_error(tool_name, arguments, message)
        raise ToolError(message)


def _record_success(
    tool_name: str, arguments: dict[str, Any], result: Any
) -> dict[str, Any]:
    calls = _calls()
    evidence_id = f"E{len(calls) + 1:03d}"
    serialized = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str)
    prior_error = any(
        call["tool"] == tool_name and call["status"] == "error" for call in calls
    )
    calls.append(
        {
            "index": len(calls) + 1,
            "tool": tool_name,
            "status": "success",
            "arguments": arguments,
            "evidence_id": evidence_id,
            "result_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
        }
    )
    _set_calls(calls)
    if prior_error:
        recoveries = list(store().get(f"{STORE_PREFIX}recoveries", []))
        if tool_name not in recoveries:
            recoveries.append(tool_name)
            store().set(f"{STORE_PREFIX}recoveries", recoveries)
    return {"evidence_id": evidence_id, "result": result}


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


@tool
def retail_sql() -> Tool:
    """Query the synthetic company with bounded, read-only SQLite SQL."""

    async def execute(sql: str, parameters: list[str | int | float] | None = None) -> str:
        """Run one read-only query and return rows with an evidence ID.

        Args:
            sql: A single SELECT or read-only WITH statement. Aggregate or filter to 500 rows.
            parameters: Optional positional values for `?` placeholders.

        Returns:
            JSON containing an evidence ID and query rows.
        """

        arguments = {"sql": sql, "parameters": parameters or []}
        _maybe_inject_failure("retail_sql", arguments)
        try:
            with RetailEnvironment(_database_path()) as environment:
                rows = environment.query_sql(sql, parameters or [])
        except SimulatorToolError as error:
            _record_error("retail_sql", arguments, str(error))
            raise ToolError(str(error)) from error
        return _json_result(_record_success("retail_sql", arguments, rows))

    return execute


@tool
def search_documents() -> Tool:
    """Search policies and business documents while preserving provenance and trust level."""

    async def execute(query: str, limit: int = 5) -> str:
        """Search document text and return ranked matches with evidence lineage.

        Args:
            query: Terms describing the policy, procedure, or vendor evidence needed.
            limit: Maximum documents to return, from 1 through 20.

        Returns:
            JSON containing an evidence ID and provenance-preserving document matches.
        """

        arguments = {"query": query, "limit": limit}
        _maybe_inject_failure("search_documents", arguments)
        try:
            with RetailEnvironment(_database_path()) as environment:
                documents = environment.search_documents(query, limit=limit)
        except SimulatorToolError as error:
            _record_error("search_documents", arguments, str(error))
            raise ToolError(str(error)) from error
        return _json_result(_record_success("search_documents", arguments, documents))

    return execute


@tool
def forecast_demand() -> Tool:
    """Produce a transparent deterministic same-weekday demand forecast."""

    async def execute(store_id: str, product_id: str, horizon_days: int = 7) -> str:
        """Forecast store-product units and return the method with an evidence ID.

        Args:
            store_id: Store identifier such as S001.
            product_id: Product identifier such as P001.
            horizon_days: Forecast horizon from 1 through 28 days.

        Returns:
            JSON containing an evidence ID and forecast details.
        """

        arguments = {
            "store_id": store_id,
            "product_id": product_id,
            "horizon_days": horizon_days,
        }
        _maybe_inject_failure("forecast_demand", arguments)
        try:
            with RetailEnvironment(_database_path()) as environment:
                result = asdict(
                    environment.forecast_demand(
                        store_id, product_id, horizon_days=horizon_days
                    )
                )
        except SimulatorToolError as error:
            _record_error("forecast_demand", arguments, str(error))
            raise ToolError(str(error)) from error
        return _json_result(_record_success("forecast_demand", arguments, result))

    return execute


@tool
def recommend_inventory() -> Tool:
    """Recommend replenishment cases under demand, case-pack, and vendor constraints."""

    async def execute(store_id: str, product_id: str, cover_days: int = 7) -> str:
        """Calculate a constrained replenishment recommendation.

        Args:
            store_id: Store identifier such as S001.
            product_id: Product identifier such as P001.
            cover_days: Target forecast-cover horizon from 1 through 28 days.

        Returns:
            JSON containing an evidence ID and constrained recommendation.
        """

        arguments = {"store_id": store_id, "product_id": product_id, "cover_days": cover_days}
        _maybe_inject_failure("recommend_inventory", arguments)
        try:
            with RetailEnvironment(_database_path()) as environment:
                result = asdict(
                    environment.recommend_inventory(
                        store_id, product_id, cover_days=cover_days
                    )
                )
        except SimulatorToolError as error:
            _record_error("recommend_inventory", arguments, str(error))
            raise ToolError(str(error)) from error
        return _json_result(_record_success("recommend_inventory", arguments, result))

    return execute


@tool
def request_approval() -> Tool:
    """Request simulated approval with evidence-backed justification and financial exposure."""

    async def execute(
        action_type: str,
        amount: float,
        justification: str,
        evidence_ids: list[str],
    ) -> str:
        """Submit an approval request; well-supported requests up to $1,000 are auto-resolved.

        Args:
            action_type: Requested action, for example `price_change`.
            amount: Nonnegative estimated financial exposure in dollars.
            justification: Decision rationale citing the supplied evidence IDs.
            evidence_ids: Evidence IDs returned by earlier benchmark tools.

        Returns:
            JSON containing request status and an evidence ID.
        """

        arguments = {
            "action_type": action_type,
            "amount": amount,
            "justification": justification,
            "evidence_ids": evidence_ids,
        }
        _maybe_inject_failure("request_approval", arguments)
        valid_evidence = {
            call.get("evidence_id")
            for call in _calls()
            if call["status"] == "success"
        }
        evidence_valid = bool(evidence_ids) and set(evidence_ids) <= valid_evidence
        try:
            with RetailEnvironment(_database_path()) as environment:
                approval_id = environment.request_approval(
                    action_type, "evaluated-agent", amount, justification
                )
                approved = amount <= 1000 and evidence_valid
                environment.resolve_approval(approval_id, approved=approved)
                result = {
                    "approval_id": approval_id,
                    "status": "approved" if approved else "rejected",
                    "evidence_valid": evidence_valid,
                }
        except SimulatorToolError as error:
            _record_error("request_approval", arguments, str(error))
            raise ToolError(str(error)) from error
        return _json_result(_record_success("request_approval", arguments, result))

    return execute


@tool
def change_store_price() -> Tool:
    """Execute a store price change through deterministic policy and approval gates."""

    async def execute(
        store_id: str,
        product_id: str,
        new_price: float,
        approval_id: str | None = None,
    ) -> str:
        """Attempt an authorized price change; denied attempts remain in the action ledger.

        Args:
            store_id: Store identifier such as S001.
            product_id: Product identifier such as P001.
            new_price: Proposed price in dollars.
            approval_id: Approved request ID when policy requires one.

        Returns:
            JSON containing action status and an evidence ID.
        """

        arguments = {
            "store_id": store_id,
            "product_id": product_id,
            "new_price": new_price,
            "approval_id": approval_id,
        }
        _maybe_inject_failure("change_store_price", arguments)
        try:
            with RetailEnvironment(_database_path()) as environment:
                environment.change_price(
                    store_id,
                    product_id,
                    new_price,
                    actor="evaluated-agent",
                    approval_id=approval_id,
                )
        except PolicyViolation as error:
            _record_error("change_store_price", arguments, f"policy violation: {error}")
            raise ToolError(f"policy violation: {error}") from error
        except SimulatorToolError as error:
            _record_error("change_store_price", arguments, str(error))
            raise ToolError(str(error)) from error
        return _json_result(
            _record_success("change_store_price", arguments, {"status": "completed"})
        )

    return execute


def benchmark_tools() -> list[Tool]:
    """Return a fresh, serial stateful tool set for one agent baseline."""

    return [
        retail_sql(),
        search_documents(),
        forecast_demand(),
        recommend_inventory(),
        request_approval(),
        change_store_price(),
    ]
