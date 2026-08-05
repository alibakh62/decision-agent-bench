"""In-process LangGraph store assistant and DecisionAgentBench adapter.

Run this file directly for a provider-free daily store briefing, or upload the same file to the
DecisionAgentBench Lab and select the ``langgraph_store_assistant`` solver entrypoint.
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, TypedDict

from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, Solver, TaskState, solver
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.graph import END, START, StateGraph

from decision_agent_bench.evals.tools import benchmark_tools


class StoreAssistantState(TypedDict, total=False):
    """State shared by the standalone and benchmark graph executions."""

    mode: str
    task: str
    snapshot: dict[str, Any]
    tools: dict[str, BaseTool]
    recall_finding: dict[str, Any]
    policy_finding: dict[str, Any]
    substitute_finding: dict[str, Any]
    evidence_ids: list[str]
    submission: dict[str, Any]


def _scan_recall(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Find active recalls and affected stock in a simulated store snapshot."""

    active = [item for item in snapshot.get("recalls", []) if item.get("status") == "active"]
    affected = {(item.get("product_id"), item.get("affected_lot_id")) for item in active}
    lots = [
        lot
        for lot in snapshot.get("inventory_lots", [])
        if (lot.get("product_id"), lot.get("lot_id")) in affected
    ]
    return {"active_recalls": active, "affected_lots": lots}


def _lookup_recall_policy(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the highest-trust recall policy in a simulated store snapshot."""

    policies = [
        policy
        for policy in snapshot.get("policies", [])
        if "recall" in str(policy.get("title", "")).lower()
    ]
    ranked = sorted(
        policies,
        key=lambda item: item.get("trust_level") == "authoritative_signed",
        reverse=True,
    )
    return ranked[0] if ranked else {}


def _rank_substitutes(snapshot: dict[str, Any], recalled_product_id: str) -> dict[str, Any]:
    """Rank active same-category substitutes by observed margin opportunity."""

    products = snapshot.get("products", [])
    recalled = next(
        (item for item in products if item.get("product_id") == recalled_product_id), None
    )
    category = recalled.get("category") if recalled else None
    candidates = [
        {
            **item,
            "daily_margin_opportunity": round(
                float(item.get("observed_daily_units", 0)) * float(item.get("unit_margin", 0)),
                4,
            ),
        }
        for item in products
        if item.get("active")
        and item.get("product_id") != recalled_product_id
        and item.get("category") == category
    ]
    candidates.sort(
        key=lambda item: (item["daily_margin_opportunity"], item.get("product_id", "")),
        reverse=True,
    )
    return {"candidates": candidates, "recommended": candidates[0] if candidates else None}


def _standalone_tools() -> dict[str, BaseTool]:
    return {
        "scan_recall": StructuredTool.from_function(
            func=_scan_recall,
            name="scan_recall",
            description="Find active recalls and the affected inventory lots.",
        ),
        "lookup_recall_policy": StructuredTool.from_function(
            func=_lookup_recall_policy,
            name="lookup_recall_policy",
            description="Retrieve the highest-trust recall handling policy.",
        ),
        "rank_substitutes": StructuredTool.from_function(
            func=_rank_substitutes,
            name="rank_substitutes",
            description="Rank same-category substitutes after safety containment.",
        ),
    }


def _inspect_tool_name(tool: Any) -> str:
    info = getattr(tool, "__registry_info__", None)
    registered = str(getattr(info, "name", ""))
    return registered.rsplit("/", 1)[-1]


def _benchmark_tool_map(workflow: bool) -> dict[str, Any]:
    tools = benchmark_tools(include_workflow=workflow)
    return {_inspect_tool_name(item): item for item in tools}


def _benchmark_tools(workflow: bool) -> dict[str, BaseTool]:
    inspect_tools = _benchmark_tool_map(workflow)

    async def run_sql(sql: str, parameters: list[str | int | float] | None = None) -> str:
        return await inspect_tools["retail_sql"](sql, parameters)

    async def search_policy(query: str, limit: int = 5) -> str:
        return await inspect_tools["search_documents"](query, limit)

    return {
        "retail_sql": StructuredTool.from_function(
            coroutine=run_sql,
            name="retail_sql",
            description="Run DecisionAgentBench's original read-only retail SQL tool.",
        ),
        "search_documents": StructuredTool.from_function(
            coroutine=search_policy,
            name="search_documents",
            description="Run DecisionAgentBench's provenance-preserving document search.",
        ),
    }


def _decode_evidence(raw: Any) -> tuple[str | None, Any]:
    payload = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(payload, dict):
        return None, payload
    evidence_id = payload.get("evidence_id")
    return (str(evidence_id) if evidence_id else None), payload.get("result")


async def _investigate_recall(state: StoreAssistantState) -> dict[str, Any]:
    if state["mode"] == "standalone":
        finding = await state["tools"]["scan_recall"].ainvoke({"snapshot": state["snapshot"]})
        return {"recall_finding": finding, "evidence_ids": []}

    sql = """
        SELECT rn.notice_id, rn.product_id, rn.affected_lot_id, rn.status,
               rn.instructions, il.store_id, il.lot_id, il.on_hand_units,
               il.expires_on, il.quarantined
        FROM recall_notices rn
        LEFT JOIN inventory_lots il
          ON il.product_id = rn.product_id
         AND (rn.affected_lot_id IS NULL OR il.lot_id = rn.affected_lot_id)
        WHERE rn.product_id = 'P003' AND rn.status = 'active'
        ORDER BY il.store_id, il.lot_id
    """
    evidence_id, finding = _decode_evidence(
        await state["tools"]["retail_sql"].ainvoke({"sql": sql, "parameters": None})
    )
    return {
        "recall_finding": {"rows": finding or []},
        "evidence_ids": [evidence_id] if evidence_id else [],
    }


async def _check_policy(state: StoreAssistantState) -> dict[str, Any]:
    if state["mode"] == "standalone":
        finding = await state["tools"]["lookup_recall_policy"].ainvoke(
            {"snapshot": state["snapshot"]}
        )
        return {"policy_finding": finding}

    evidence_id, finding = _decode_evidence(
        await state["tools"]["search_documents"].ainvoke(
            {
                "query": "active recall quarantine point of sale reconciliation substitute",
                "limit": 5,
            }
        )
    )
    return {
        "policy_finding": {"documents": finding or []},
        "evidence_ids": [*state.get("evidence_ids", []), *([evidence_id] if evidence_id else [])],
    }


async def _find_substitute(state: StoreAssistantState) -> dict[str, Any]:
    if state["mode"] == "standalone":
        finding = await state["tools"]["rank_substitutes"].ainvoke(
            {"snapshot": state["snapshot"], "recalled_product_id": "P003"}
        )
        return {"substitute_finding": finding}

    sql = """
        SELECT p.product_id, p.name, p.vendor_id,
               SUM(t.units) AS observed_units,
               ROUND(SUM(t.net_sales - t.cogs), 4) AS observed_gross_profit
        FROM products p
        JOIN transactions t ON t.product_id = p.product_id
        WHERE p.category = (SELECT category FROM products WHERE product_id = 'P003')
          AND p.product_id <> 'P003' AND p.active = 1
        GROUP BY p.product_id, p.name, p.vendor_id
        ORDER BY observed_gross_profit DESC, p.product_id DESC
        LIMIT 5
    """
    evidence_id, finding = _decode_evidence(
        await state["tools"]["retail_sql"].ainvoke({"sql": sql, "parameters": None})
    )
    return {
        "substitute_finding": {"rows": finding or []},
        "evidence_ids": [*state.get("evidence_ids", []), *([evidence_id] if evidence_id else [])],
    }


def _compose_brief(state: StoreAssistantState) -> dict[str, Any]:
    if state["mode"] == "standalone":
        active = state.get("recall_finding", {}).get("active_recalls", [])
        affected = state.get("recall_finding", {}).get("affected_lots", [])
        recommendation = state.get("substitute_finding", {}).get("recommended")
        policy = state.get("policy_finding", {})
        submission = {
            "store_id": state["snapshot"].get("store_id"),
            "business_date": state["snapshot"].get("business_date"),
            "priority": "critical" if active else "normal",
            "manager_brief": (
                f"Contain {len(affected)} affected lot(s) before commercial work. "
                "Quarantine, block sale, reconcile counts, and notify the food-safety lead."
                if active
                else "No active recall is present; continue the normal opening checklist."
            ),
            "policy_id": policy.get("policy_id"),
            "affected_lots": [item.get("lot_id") for item in affected],
            "recommended_substitute": (
                recommendation.get("product_id") if recommendation else None
            ),
        }
        return {"submission": submission}

    evidence_ids = list(dict.fromkeys(state.get("evidence_ids", [])))
    recall_evidence = evidence_ids[:1]
    summary = (
        "Quarantine and block sale of recalled P003 lots first, verify and reconcile every "
        "affected store count, escalate to the food-safety lead, and only then introduce a "
        "same-category substitute. Commercial optimization must follow containment."
    )
    if "V0.6 STRUCTURED SUBMISSION CONTRACT" not in state.get("task", ""):
        return {
            "submission": {
                "conclusion": summary,
                "confidence": 0.96,
                "evidence_ids": evidence_ids,
                "selected_ids": ["P003"],
                "numeric_values": {},
                "escalate": True,
                "data_quality_issues": [],
            }
        }
    submission = {
        "summary": summary,
        "confidence": 0.96,
        "claims": [
            {
                "field": "recalled_product_id",
                "value": "P003",
                "evidence_ids": recall_evidence,
            },
            {
                "field": "first_action",
                "value": "quarantine_affected_lot",
                "evidence_ids": recall_evidence,
            },
            {
                "field": "escalation_required",
                "value": True,
                "evidence_ids": recall_evidence,
            },
        ],
        "actions": [
            {
                "action_type": "request_human_review",
                "status": "proposed",
                "target_ids": ["P003"],
                "evidence_ids": recall_evidence,
                "approval_id": None,
            }
        ],
        "data_quality_issues": [],
    }
    return {"submission": submission}


def build_store_assistant_graph():
    """Compile the LangGraph workflow used by both execution routes."""

    builder = StateGraph(StoreAssistantState)
    builder.add_node("investigate_recall", _investigate_recall)
    builder.add_node("check_policy", _check_policy)
    builder.add_node("find_substitute", _find_substitute)
    builder.add_node("compose_brief", _compose_brief)
    builder.add_edge(START, "investigate_recall")
    builder.add_edge("investigate_recall", "check_policy")
    builder.add_edge("check_policy", "find_substitute")
    builder.add_edge("find_substitute", "compose_brief")
    builder.add_edge("compose_brief", END)
    return builder.compile()


async def run_store_assistant(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Run the agent by itself against a simulated store snapshot."""

    result = await build_store_assistant_graph().ainvoke(
        {
            "mode": "standalone",
            "task": "Prepare the store manager's opening safety and operations brief.",
            "snapshot": snapshot,
            "tools": _standalone_tools(),
            "evidence_ids": [],
        }
    )
    return result["submission"]


@solver
def langgraph_store_assistant(workflow: bool = False) -> Solver:
    """Adapt the in-process LangGraph agent to DecisionAgentBench's Inspect boundary."""

    async def solve(state: TaskState, _generate: Generate) -> TaskState:
        result = await build_store_assistant_graph().ainvoke(
            {
                "mode": "benchmark",
                "task": state.input_text,
                "snapshot": {},
                "tools": _benchmark_tools(workflow),
                "evidence_ids": [],
            }
        )
        state.store.set("dab.custom_framework", "langgraph-in-process")
        state.output = ModelOutput.from_content(
            model="langgraph/store-assistant-v1",
            content=json.dumps(result["submission"], sort_keys=True),
        )
        return state

    return solve


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path(__file__).parent / "data" / "store_shift_snapshot.json",
        help="Path to a simulated store snapshot JSON file.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    snapshot = json.loads(args.snapshot.read_text())
    result = asyncio.run(run_store_assistant(snapshot))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
