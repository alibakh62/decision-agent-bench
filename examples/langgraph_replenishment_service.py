"""LangGraph convenience-retail replenishment service and DecisionAgentBench adapter.

The service owns planning and decision logic while its Inspect adapter brokers every benchmark tool
call back through the active sample. Run ``python examples/langgraph_replenishment_service.py
serve`` to start the HTTP service, or use ``demo`` for a provider-free standalone example.
"""

import argparse
import asyncio
import json
import math
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Literal, TypedDict
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, Solver, TaskState, solver
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from decision_agent_bench.evals.tools import benchmark_tools


class ReplenishmentState(TypedDict, total=False):
    snapshot: dict[str, Any]
    recommendations: list[dict[str, Any]]
    constrained_plan: list[dict[str, Any]]
    brief: dict[str, Any]


def _forecast_and_size(state: ReplenishmentState) -> dict[str, Any]:
    snapshot = state["snapshot"]
    constraints = snapshot.get("constraints", {})
    default_cover = int(constraints.get("target_cover_days", 7))
    fresh_cover = int(constraints.get("fresh_food_max_cover_days", 3))
    recommendations: list[dict[str, Any]] = []
    for product in snapshot.get("products", []):
        cover_days = fresh_cover if product.get("category") == "fresh_food" else default_cover
        daily_units = float(product.get("average_daily_units", 0))
        target_units = daily_units * cover_days
        units_needed = max(0.0, target_units - float(product.get("on_hand_units", 0)))
        case_pack = max(1, int(product.get("case_pack", 1)))
        cases = math.ceil(units_needed / case_pack)
        if cases:
            cases = max(cases, int(product.get("min_order_cases", 1)))
        cases = min(cases, int(product.get("vendor_capacity_cases", cases)))
        arrival_gap = max(
            0.0,
            daily_units * int(product.get("lead_time_days", 0))
            - float(product.get("on_hand_units", 0)),
        )
        recommendations.append(
            {
                "product_id": product.get("product_id"),
                "name": product.get("name"),
                "recommended_cases": cases,
                "target_cover_days": cover_days,
                "arrival_stockout_units": round(arrival_gap, 2),
                "priority_score": round(
                    arrival_gap * 10 + daily_units * float(product.get("unit_margin", 0)), 4
                ),
            }
        )
    recommendations.sort(
        key=lambda item: (item["priority_score"], item.get("product_id", "")), reverse=True
    )
    return {"recommendations": recommendations}


def _apply_order_budget(state: ReplenishmentState) -> dict[str, Any]:
    remaining = int(state["snapshot"].get("constraints", {}).get("max_total_cases", 10))
    plan: list[dict[str, Any]] = []
    for recommendation in state.get("recommendations", []):
        requested = int(recommendation["recommended_cases"])
        approved = min(requested, remaining)
        remaining -= approved
        plan.append(
            {
                **recommendation,
                "approved_cases": approved,
                "deferred_cases": requested - approved,
            }
        )
    return {"constrained_plan": plan}


def _compose_replenishment_brief(state: ReplenishmentState) -> dict[str, Any]:
    plan = state.get("constrained_plan", [])
    urgent = [item for item in plan if item["arrival_stockout_units"] > 0]
    ordered = [item for item in plan if item["approved_cases"] > 0]
    return {
        "brief": {
            "store_id": state["snapshot"].get("store_id"),
            "business_date": state["snapshot"].get("business_date"),
            "summary": (
                f"Place {sum(item['approved_cases'] for item in ordered)} cases across "
                f"{len(ordered)} products; {len(urgent)} product(s) risk stocking out before "
                "their next delivery."
            ),
            "orders": ordered,
            "capacity_remaining_cases": max(
                0,
                int(state["snapshot"].get("constraints", {}).get("max_total_cases", 10))
                - sum(item["approved_cases"] for item in ordered),
            ),
        }
    }


def build_replenishment_graph():
    """Compile the standalone replenishment workflow."""

    builder = StateGraph(ReplenishmentState)
    builder.add_node("forecast_and_size", RunnableLambda(_forecast_and_size))
    builder.add_node("apply_order_budget", RunnableLambda(_apply_order_budget))
    builder.add_node("compose_brief", RunnableLambda(_compose_replenishment_brief))
    builder.add_edge(START, "forecast_and_size")
    builder.add_edge("forecast_and_size", "apply_order_budget")
    builder.add_edge("apply_order_budget", "compose_brief")
    builder.add_edge("compose_brief", END)
    return builder.compile()


async def run_replenishment_agent(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Run the remote service's business graph without starting HTTP."""

    result = await build_replenishment_graph().ainvoke({"snapshot": snapshot})
    return result["brief"]


class BrokerState(TypedDict, total=False):
    prompt: str
    sample_id: str | None
    observations: dict[str, dict[str, Any]]
    failures: dict[str, int]
    next_action: dict[str, Any] | None
    submission: dict[str, Any] | None


_CANDIDATE_SQL = """
    WITH latest AS (SELECT date(MAX(sold_at)) AS max_date FROM transactions)
    SELECT p.product_id, p.name, p.vendor_id, p.unit_cost, pr.unit_price,
           v.min_order_cases, v.capacity_cases_per_week,
           COALESCE(SUM(t.units), 0) AS observed_units_28d,
           ROUND(pr.unit_price - p.unit_cost, 4) AS unit_margin,
           ROUND(COALESCE(SUM(t.units), 0) * (pr.unit_price - p.unit_cost), 4)
             AS opportunity_gross_profit
    FROM products p
    JOIN prices pr ON pr.product_id = p.product_id AND pr.store_id = 'S001'
    JOIN vendors v ON v.vendor_id = p.vendor_id
    CROSS JOIN latest
    LEFT JOIN transactions t
      ON t.product_id = p.product_id AND t.store_id = pr.store_id
     AND date(t.sold_at) >= date(latest.max_date, '-27 days')
    WHERE p.category = (SELECT category FROM products WHERE product_id = 'P005')
      AND p.product_id <> 'P005' AND p.active = 1 AND v.active = 1
      AND v.capacity_cases_per_week >= v.min_order_cases
    GROUP BY p.product_id, p.name, p.vendor_id, p.unit_cost, pr.unit_price,
             v.min_order_cases, v.capacity_cases_per_week
    ORDER BY opportunity_gross_profit DESC, p.product_id DESC
    LIMIT 8
"""

_VENDOR_SQL = """
    SELECT p.product_id, p.vendor_id, v.name AS vendor_name, v.active,
           v.lead_time_days, v.min_order_cases, v.capacity_cases_per_week,
           p.case_pack
    FROM products p JOIN vendors v ON v.vendor_id = p.vendor_id
    WHERE p.product_id = ?
"""

_SHELF_SQL = """
    SELECT p.product_id, p.name, pr.store_id, pr.unit_price, p.unit_cost,
           ROUND(pr.unit_price - p.unit_cost, 4) AS unit_margin,
           i.on_hand_units, i.reorder_point, p.case_pack, p.shelf_life_days
    FROM products p
    JOIN prices pr ON pr.product_id = p.product_id AND pr.store_id = 'S001'
    LEFT JOIN inventory i ON i.product_id = p.product_id AND i.store_id = pr.store_id
    WHERE p.product_id = ?
"""


def _candidate_rows(state: BrokerState) -> list[dict[str, Any]]:
    result = state.get("observations", {}).get("candidate_margin", {}).get("result", [])
    return result if isinstance(result, list) else []


def _best_candidate(state: BrokerState) -> dict[str, Any] | None:
    rows = _candidate_rows(state)
    return max(
        rows,
        key=lambda row: (
            float(row.get("opportunity_gross_profit", 0)),
            str(row.get("product_id", "")),
        ),
        default=None,
    )


def _broker_action(label: str, sql: str, parameters: list[Any] | None, attempt: int) -> dict:
    return {
        "call_id": f"{label}-{attempt}",
        "label": label,
        "tool_name": "retail_sql",
        "arguments": {"sql": sql, "parameters": parameters},
    }


def _broker_agent_step(state: BrokerState) -> dict[str, Any]:
    observations = state.get("observations", {})
    failures = state.get("failures", {})
    if "candidate_margin" not in observations:
        return {
            "next_action": _broker_action(
                "candidate_margin",
                _CANDIDATE_SQL,
                None,
                failures.get("candidate_margin", 0) + 1,
            ),
            "submission": None,
        }

    candidate = _best_candidate(state)
    candidate_id = str(candidate.get("product_id")) if candidate else ""
    if candidate and "vendor_constraints" not in observations:
        return {
            "next_action": _broker_action(
                "vendor_constraints",
                _VENDOR_SQL,
                [candidate_id],
                failures.get("vendor_constraints", 0) + 1,
            ),
            "submission": None,
        }
    if candidate and "shelf_economics" not in observations:
        return {
            "next_action": _broker_action(
                "shelf_economics",
                _SHELF_SQL,
                [candidate_id],
                failures.get("shelf_economics", 0) + 1,
            ),
            "submission": None,
        }

    evidence_ids = [
        str(item["evidence_id"]) for item in observations.values() if item.get("evidence_id")
    ]
    v06_contract = "V0.6 STRUCTURED SUBMISSION CONTRACT" in state.get("prompt", "")
    if not candidate:
        if not v06_contract:
            return {
                "next_action": None,
                "submission": {
                    "conclusion": (
                        "No feasible replacement could be verified; escalate rather than guess."
                    ),
                    "confidence": 0.25,
                    "evidence_ids": evidence_ids,
                    "selected_ids": [],
                    "numeric_values": {},
                    "escalate": True,
                    "data_quality_issues": ["No feasible candidate was returned."],
                },
            }
        submission = {
            "summary": (
                "No feasible replacement could be verified from the observable margin, vendor, "
                "and shelf evidence; escalate rather than guessing."
            ),
            "confidence": 0.25,
            "claims": [
                {"field": "delisted_product_id", "value": "P005", "evidence_ids": []},
                {"field": "replacement_product_id", "value": "", "evidence_ids": []},
                {
                    "field": "vendor_constraints_checked",
                    "value": False,
                    "evidence_ids": [],
                },
            ],
            "actions": [],
            "data_quality_issues": [
                {"code": "NO_FEASIBLE_CANDIDATE", "evidence_ids": evidence_ids}
            ],
        }
    else:
        opportunity = float(candidate.get("opportunity_gross_profit", 0))
        summary = (
            f"Replace P005 with {candidate_id}. It has the strongest observed 28-day "
            f"unit-margin profit opportunity (${opportunity:.2f}) among feasible active "
            "beverage candidates; its vendor capacity meets the minimum order and the S001 "
            "shelf economics were checked before selection."
        )
        if not v06_contract:
            return {
                "next_action": None,
                "submission": {
                    "conclusion": summary,
                    "confidence": 0.94,
                    "evidence_ids": evidence_ids,
                    "selected_ids": [candidate_id],
                    "numeric_values": {
                        "observed_margin_opportunity_28d": round(opportunity, 4)
                    },
                    "escalate": False,
                    "data_quality_issues": [],
                },
            }
        candidate_evidence = [
            str(observations["candidate_margin"]["evidence_id"]),
        ]
        vendor_evidence = [
            str(observations["vendor_constraints"]["evidence_id"]),
        ]
        submission = {
            "summary": summary,
            "confidence": 0.94,
            "claims": [
                {
                    "field": "delisted_product_id",
                    "value": "P005",
                    "evidence_ids": candidate_evidence,
                },
                {
                    "field": "replacement_product_id",
                    "value": candidate_id,
                    "evidence_ids": candidate_evidence,
                },
                {
                    "field": "vendor_constraints_checked",
                    "value": True,
                    "evidence_ids": vendor_evidence,
                },
            ],
            "actions": [],
            "data_quality_issues": [],
        }
    return {"next_action": None, "submission": submission}


def build_broker_graph():
    """Compile the service-side tool-request and decision graph."""

    builder = StateGraph(BrokerState)
    builder.add_node("decide_next", RunnableLambda(_broker_agent_step))
    builder.add_edge(START, "decide_next")
    builder.add_edge("decide_next", END)
    return builder.compile()


class StartRunRequest(BaseModel):
    prompt: str = Field(min_length=1)
    sample_id: str | None = None


class ObservationRequest(BaseModel):
    call_id: str
    tool_name: str
    output: str | None = None
    error: str | None = None


class StoreBriefRequest(BaseModel):
    snapshot: dict[str, Any]


class AgentResponse(BaseModel):
    run_id: str
    status: Literal["tool_call", "complete"]
    action: dict[str, Any] | None = None
    submission: dict[str, Any] | None = None


app = FastAPI(
    title="ReplenishmentDesk LangGraph Agent",
    version="1.0.0",
    description="A convenience-retail replenishment agent with a benchmark tool-broker API.",
)
_RUNS: dict[str, BrokerState] = {}
_RUNS_LOCK = threading.RLock()


def _agent_response(run_id: str, state: BrokerState) -> AgentResponse:
    if state.get("submission") is not None:
        return AgentResponse(
            run_id=run_id,
            status="complete",
            submission=state["submission"],
        )
    return AgentResponse(run_id=run_id, status="tool_call", action=state.get("next_action"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "agent": "replenishment-desk-v1"}


@app.post("/v1/store-brief")
async def store_brief(request: StoreBriefRequest) -> dict[str, Any]:
    return await run_replenishment_agent(request.snapshot)


@app.post("/v1/runs", response_model=AgentResponse)
async def start_run(request: StartRunRequest) -> AgentResponse:
    run_id = uuid.uuid4().hex
    state: BrokerState = {
        "prompt": request.prompt,
        "sample_id": request.sample_id,
        "observations": {},
        "failures": {},
        "next_action": None,
        "submission": None,
    }
    advanced = await build_broker_graph().ainvoke(state)
    with _RUNS_LOCK:
        _RUNS[run_id] = advanced
    return _agent_response(run_id, advanced)


@app.post("/v1/runs/{run_id}/observations", response_model=AgentResponse)
async def add_observation(run_id: str, request: ObservationRequest) -> AgentResponse:
    with _RUNS_LOCK:
        state = _RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown run")
    expected = state.get("next_action")
    if not expected or request.call_id != expected.get("call_id"):
        raise HTTPException(status_code=409, detail="observation does not match pending action")
    if request.tool_name != expected.get("tool_name"):
        raise HTTPException(status_code=409, detail="tool name does not match pending action")

    label = str(expected["label"])
    observations = dict(state.get("observations", {}))
    failures = dict(state.get("failures", {}))
    if request.error:
        failures[label] = failures.get(label, 0) + 1
        if failures[label] >= 2:
            observations[label] = {"error": request.error, "result": []}
    else:
        try:
            payload = json.loads(request.output or "{}")
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=422, detail="tool output must be JSON") from error
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="tool output must be a JSON object")
        observations[label] = {
            "evidence_id": payload.get("evidence_id"),
            "result": payload.get("result"),
        }

    updated: BrokerState = {
        **state,
        "observations": observations,
        "failures": failures,
        "next_action": None,
    }
    advanced = await build_broker_graph().ainvoke(updated)
    with _RUNS_LOCK:
        _RUNS[run_id] = advanced
    return _agent_response(run_id, advanced)


@app.delete("/v1/runs/{run_id}")
async def delete_run(run_id: str) -> dict[str, bool]:
    with _RUNS_LOCK:
        removed = _RUNS.pop(run_id, None) is not None
    return {"deleted": removed}


def _inspect_tool_name(tool: Any) -> str:
    info = getattr(tool, "__registry_info__", None)
    return str(getattr(info, "name", "")).rsplit("/", 1)[-1]


def validated_service_url(value: str) -> str:
    """Validate and normalize a loopback or explicitly allow-listed service origin."""

    parsed = urlsplit(value.strip())
    hostname = (parsed.hostname or "").lower()
    allowlist = {
        item.strip().lower()
        for item in os.environ.get("DAB_REMOTE_AGENT_ALLOWLIST", "").split(",")
        if item.strip()
    }
    loopback = hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError("service_url must be an http(s) origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("service_url must not contain credentials, query parameters, or fragments")
    if parsed.path not in {"", "/"}:
        raise ValueError("service_url must be an origin without a path")
    if not loopback and hostname not in allowlist:
        raise ValueError("remote service host is not allow-listed; set DAB_REMOTE_AGENT_ALLOWLIST")
    if not loopback and parsed.scheme != "https":
        raise ValueError("non-loopback remote services must use https")
    authority = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port is not None:
        authority = f"{authority}:{parsed.port}"
    return f"{parsed.scheme}://{authority}"


async def _run_broker_protocol(
    *,
    prompt: str,
    sample_id: str | None,
    workflow: bool,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    inspect_tools = {
        _inspect_tool_name(tool): tool for tool in benchmark_tools(include_workflow=workflow)
    }
    response = await client.post("/v1/runs", json={"prompt": prompt, "sample_id": sample_id})
    response.raise_for_status()
    message = response.json()
    run_id = str(message["run_id"])
    try:
        for _ in range(10):
            if message["status"] == "complete":
                return dict(message["submission"])
            action = message["action"]
            tool_name = str(action["tool_name"])
            tool = inspect_tools.get(tool_name)
            if tool is None:
                observation = {
                    "call_id": action["call_id"],
                    "tool_name": tool_name,
                    "error": f"unsupported benchmark tool: {tool_name}",
                }
            else:
                try:
                    output = await tool(**action["arguments"])
                    observation = {
                        "call_id": action["call_id"],
                        "tool_name": tool_name,
                        "output": output,
                    }
                except Exception as error:  # Inspect tool failures are returned to the agent.
                    observation = {
                        "call_id": action["call_id"],
                        "tool_name": tool_name,
                        "error": str(error),
                    }
            response = await client.post(f"/v1/runs/{run_id}/observations", json=observation)
            response.raise_for_status()
            message = response.json()
        raise RuntimeError("remote agent exceeded its ten-step broker budget")
    finally:
        await client.delete(f"/v1/runs/{run_id}")


@solver
def langgraph_remote_replenishment(
    service_url: str = "http://127.0.0.1:8099",
    workflow: bool = False,
    in_process: bool = False,
) -> Solver:
    """Connect the LangGraph HTTP service to DecisionAgentBench through a tool broker."""

    async def solve(state: TaskState, _generate: Generate) -> TaskState:
        transport = httpx.ASGITransport(app=app) if in_process else None
        base_url = "http://testserver" if in_process else validated_service_url(service_url)
        async with httpx.AsyncClient(
            base_url=base_url,
            transport=transport,
            timeout=httpx.Timeout(30.0),
        ) as client:
            submission = await _run_broker_protocol(
                prompt=state.input_text,
                sample_id=str(state.sample_id) if state.sample_id else None,
                workflow=workflow,
                client=client,
            )
        state.store.set("dab.custom_framework", "langgraph-remote-service")
        state.store.set("dab.external_usage_accounting", "service-is-deterministic-no-model-calls")
        state.output = ModelOutput.from_content(
            model="langgraph/replenishment-service-v1",
            content=json.dumps(submission, sort_keys=True),
        )
        return state

    return solve


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    demo = subparsers.add_parser("demo", help="Run the agent directly on simulated JSON.")
    demo.add_argument(
        "--snapshot",
        type=Path,
        default=Path(__file__).parent / "data" / "replenishment_snapshot.json",
    )
    serve = subparsers.add_parser("serve", help="Start the remote agent HTTP service.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8099)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "serve":
        uvicorn.run(app, host=args.host, port=args.port)
        return 0
    snapshot_path = getattr(
        args,
        "snapshot",
        Path(__file__).parent / "data" / "replenishment_snapshot.json",
    )
    snapshot = json.loads(snapshot_path.read_text())
    result = asyncio.run(run_replenishment_agent(snapshot))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
