"""Dependency-enforced, stateful workflow simulator for DecisionAgentBench v0.3."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORKFLOW_VERSION = "0.3.0"
WORKFLOW_STEP_COUNT = 20
WORKFLOW_DEPENDENCY_SPAN = 19
WORKFLOW_MINIMUM_DAYS = 15
WORKFLOW_INTERNAL_TABLES = frozenset(
    {
        "dab_workflow_runs",
        "dab_workflow_steps",
        "dab_workflow_events",
        "dab_workflow_mutations",
        "dab_workflow_trace",
    }
)


class WorkflowError(RuntimeError):
    """A safe workflow transition error that can be shown to an evaluated agent."""


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    title: str
    dependencies: tuple[str, ...]
    min_day: int
    required_tools: tuple[str, ...]
    required_event: str | None = None
    effect: str | None = None
    reversible: bool = False


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    title: str
    category: str
    prompt: str
    step_titles: tuple[str, ...]
    evidence_tools: tuple[str, ...]
    reversible_effect: str
    final_effect: str
    stress_event: str
    activation_effect: str | None = None


WORKFLOWS: tuple[WorkflowDefinition, ...] = (
    WorkflowDefinition(
        workflow_id="DAB-LH-REGION",
        title="Regional demand turnaround",
        category="stateful_regional_operations",
        prompt=(
            "Execute the regional demand-turnaround workflow to completion. Establish the factual "
            "baseline, apply the approved pilot, advance simulated time for every checkpoint, and "
            "recover from any event the simulator reveals. Inspect the workflow before executing "
            "transitions and after advancing time; "
            "a narrative plan without executed transitions is incomplete."
        ),
        step_titles=(
            "scope affected stores",
            "verify demand signal",
            "forecast pilot demand",
            "check inventory cover",
            "obtain pilot authorization",
            "open regional pilot",
            "stage replenishment",
            "apply pilot price",
            "record launch controls",
            "complete first checkpoint",
            "assess checkpoint outcome",
            "reconcile inventory",
            "confirm policy compliance",
            "adjust operating plan",
            "complete second checkpoint",
            "assess final signal",
            "validate financial exposure",
            "prepare closeout",
            "confirm regional readiness",
            "close regional pilot",
        ),
        evidence_tools=(
            "retail_sql",
            "retail_sql",
            "forecast_demand",
            "recommend_inventory",
            "request_approval",
        ),
        reversible_effect="regional_price_pilot",
        final_effect="regional_closeout",
        stress_event="regional_budget_cut",
    ),
    WorkflowDefinition(
        workflow_id="DAB-LH-VENDOR",
        title="Vendor product pilot",
        category="stateful_vendor_operations",
        prompt=(
            "Execute the vendor-product pilot workflow to completion. Verify qualification and "
            "economics, stage the pilot, wait for delayed checkpoints, and perform any required "
            "rollback before closeout. Only simulator-confirmed transitions count."
        ),
        step_titles=(
            "scope candidate product",
            "verify vendor status",
            "forecast pilot demand",
            "calculate initial order",
            "obtain pilot authorization",
            "open vendor pilot",
            "reserve shelf capacity",
            "stage pilot inventory",
            "record launch controls",
            "complete first checkpoint",
            "assess sell-through",
            "reconcile vendor capacity",
            "confirm quality controls",
            "adjust replenishment plan",
            "complete second checkpoint",
            "assess final economics",
            "validate service level",
            "prepare vendor review",
            "confirm pilot disposition",
            "close vendor pilot",
        ),
        evidence_tools=(
            "retail_sql",
            "search_documents",
            "forecast_demand",
            "recommend_inventory",
            "request_approval",
        ),
        reversible_effect="vendor_inventory_pilot",
        final_effect="vendor_closeout",
        stress_event="vendor_underperformance",
    ),
    WorkflowDefinition(
        workflow_id="DAB-LH-RECALL",
        title="Recall containment and recovery",
        category="stateful_safety_operations",
        prompt=(
            "Execute the recall-containment workflow to completion. Verify the authoritative "
            "notice "
            "and lot scope, contain the affected stock, advance time for trace checkpoints, and "
            "recover safely from any substitute-supply event. Do not close the notice early."
        ),
        step_titles=(
            "identify active notice",
            "verify authoritative instructions",
            "quantify affected lots",
            "assess replacement cover",
            "obtain recovery authorization",
            "open containment",
            "quarantine affected lots",
            "stage substitute inventory",
            "record trace controls",
            "complete first trace checkpoint",
            "assess containment",
            "reconcile lot counts",
            "confirm customer safeguards",
            "adjust substitute plan",
            "complete second trace checkpoint",
            "assess final trace",
            "validate residual exposure",
            "prepare incident review",
            "confirm closure readiness",
            "close recall notice",
        ),
        evidence_tools=(
            "retail_sql",
            "search_documents",
            "retail_sql",
            "recommend_inventory",
            "request_approval",
        ),
        reversible_effect="recall_substitute_stage",
        final_effect="recall_closeout",
        stress_event="substitute_supply_shortage",
        activation_effect="recall_quarantine",
    ),
)

_BY_ID = {workflow.workflow_id: workflow for workflow in WORKFLOWS}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dab_workflow_runs (
    workflow_id TEXT PRIMARY KEY,
    workflow_version TEXT NOT NULL,
    variant TEXT NOT NULL,
    scenario_seed INTEGER NOT NULL,
    current_day INTEGER NOT NULL DEFAULT 0,
    required_rollback_step TEXT,
    completed_day INTEGER
);
CREATE TABLE IF NOT EXISTS dab_workflow_steps (
    step_id TEXT PRIMARY KEY,
    ordinal INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    dependencies_json TEXT NOT NULL,
    min_day INTEGER NOT NULL,
    required_tools_json TEXT NOT NULL,
    required_event TEXT,
    effect TEXT,
    reversible INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    completed_day INTEGER,
    rolled_back_day INTEGER
);
CREATE TABLE IF NOT EXISTS dab_workflow_events (
    event_id TEXT PRIMARY KEY,
    scheduled_day INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    applied INTEGER NOT NULL DEFAULT 0,
    resolved INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS dab_workflow_mutations (
    mutation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    key_json TEXT NOT NULL,
    column_name TEXT NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS dab_workflow_trace (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    step_id TEXT,
    status TEXT NOT NULL,
    details_json TEXT NOT NULL
);
"""


def workflow_catalog() -> list[dict[str, Any]]:
    """Return the public, deterministic v0.3 workflow catalog."""

    return [
        {
            "workflow_id": item.workflow_id,
            "version": WORKFLOW_VERSION,
            "title": item.title,
            "category": item.category,
            "enforced_transitions": WORKFLOW_STEP_COUNT,
            "dependency_span_target": WORKFLOW_DEPENDENCY_SPAN,
            "minimum_simulated_days": WORKFLOW_MINIMUM_DAYS,
            "stress_event": item.stress_event,
        }
        for item in WORKFLOWS
    ]


def workflow_instance_catalog() -> list[dict[str, Any]]:
    """Return the 12 stable seeded workflow instances behind the 24 paired samples."""

    return [
        {
            "benchmark_version": WORKFLOW_VERSION,
            "contract_version": WORKFLOW_VERSION,
            "workflow_id": workflow.workflow_id,
            "instance_id": f"{workflow.workflow_id}-i{instance_index + 1}",
            "scenario_seed": 20260717 + instance_index,
            "category": workflow.category,
            "difficulty": "expert",
            "prompt": workflow.prompt,
            "clean_sample_id": (f"{workflow.workflow_id}-i{instance_index + 1}-clean"),
            "perturbed_sample_id": (f"{workflow.workflow_id}-i{instance_index + 1}-perturbed"),
            "perturbation": workflow.stress_event,
            "enforced_transitions": WORKFLOW_STEP_COUNT,
            "dependency_span_target": WORKFLOW_DEPENDENCY_SPAN,
            "minimum_simulated_days": WORKFLOW_MINIMUM_DAYS,
            "horizon_claim": "dependency_enforced_preview",
        }
        for workflow in WORKFLOWS
        for instance_index in range(4)
    ]


def write_workflow_instance_catalog(output_path: Path) -> Path:
    """Write the stable v0.3 workflow-instance catalog."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(workflow_instance_catalog(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _steps(definition: WorkflowDefinition) -> tuple[WorkflowStep, ...]:
    steps: list[WorkflowStep] = []
    for index, title in enumerate(definition.step_titles, start=1):
        step_id = f"S{index:02d}"
        dependencies: tuple[str, ...] = () if index == 1 else (f"S{index - 1:02d}",)
        if index == WORKFLOW_STEP_COUNT:
            dependencies = (*dependencies, "S01")
        min_day = 0 if index <= 5 else 5 if index <= 10 else 10 if index <= 15 else 15
        required_event = {6: "checkpoint_1", 11: "checkpoint_2", 16: "final_signal"}.get(index)
        required_tools = (
            (definition.evidence_tools[index - 1],)
            if index <= len(definition.evidence_tools)
            else ("execute_workflow_step",)
        )
        effect = (
            definition.activation_effect
            if index == 7
            else definition.reversible_effect
            if index == 8
            else definition.final_effect
            if index == 20
            else None
        )
        steps.append(
            WorkflowStep(
                step_id=step_id,
                title=title,
                dependencies=dependencies,
                min_day=min_day,
                required_tools=required_tools,
                required_event=required_event,
                effect=effect,
                reversible=index == 8,
            )
        )
    return tuple(steps)


def initialize_workflow(
    database_path: Path, workflow_id: str, *, variant: str, scenario_seed: int
) -> None:
    """Install a fresh v0.3 workflow state machine in a generated world."""

    if workflow_id not in _BY_ID:
        raise ValueError(f"unknown workflow_id {workflow_id!r}")
    if variant not in {"clean", "perturbed"}:
        raise ValueError("workflow variant must be clean or perturbed")
    definition = _BY_ID[workflow_id]
    with sqlite3.connect(database_path) as connection:
        connection.executescript(_SCHEMA)
        connection.execute(
            "INSERT INTO dab_workflow_runs VALUES (?, ?, ?, ?, 0, NULL, NULL)",
            (workflow_id, WORKFLOW_VERSION, variant, scenario_seed),
        )
        connection.executemany(
            """
            INSERT INTO dab_workflow_steps
            (step_id, ordinal, title, dependencies_json, min_day, required_tools_json,
             required_event, effect, reversible)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    step.step_id,
                    index,
                    step.title,
                    json.dumps(step.dependencies),
                    step.min_day,
                    json.dumps(step.required_tools),
                    step.required_event,
                    step.effect,
                    int(step.reversible),
                )
                for index, step in enumerate(_steps(definition), start=1)
            ],
        )
        events = [
            ("checkpoint_1", 5, "checkpoint", {"phase": 1}),
            ("checkpoint_2", 10, "checkpoint", {"phase": 2}),
            ("final_signal", 15, "outcome", {"phase": 3}),
        ]
        if variant == "perturbed":
            magnitude = 10 + scenario_seed % 11
            events.append(
                (
                    definition.stress_event,
                    10,
                    "disruption",
                    {"required_rollback_step": "S08", "magnitude_pct": magnitude},
                )
            )
        connection.executemany(
            "INSERT INTO dab_workflow_events VALUES (?, ?, ?, ?, 0, 0)",
            [
                (event_id, day, kind, json.dumps(payload, sort_keys=True))
                for event_id, day, kind, payload in events
            ],
        )
        _trace(connection, 0, "workflow_initialized", None, "success", {"variant": variant})
        connection.commit()


def _trace(
    connection: sqlite3.Connection,
    day: int,
    event_type: str,
    step_id: str | None,
    status: str,
    details: dict[str, Any],
) -> None:
    connection.execute(
        """INSERT INTO dab_workflow_trace
           (day, event_type, step_id, status, details_json)
           VALUES (?, ?, ?, ?, ?)""",
        (day, event_type, step_id, status, json.dumps(details, sort_keys=True)),
    )


def _run(connection: sqlite3.Connection) -> sqlite3.Row:
    connection.row_factory = sqlite3.Row
    row = connection.execute("SELECT * FROM dab_workflow_runs").fetchone()
    if row is None:
        raise WorkflowError("this sample has no stateful workflow")
    return row


def inspect_workflow_state(database_path: Path) -> dict[str, Any]:
    """Return current public workflow state and transition requirements."""

    with sqlite3.connect(database_path) as connection:
        run = _run(connection)
        steps = connection.execute("SELECT * FROM dab_workflow_steps ORDER BY ordinal").fetchall()
        events = connection.execute(
            """SELECT event_id, scheduled_day, event_type, payload_json, resolved
               FROM dab_workflow_events WHERE applied=1
               ORDER BY scheduled_day, event_id"""
        ).fetchall()
        public_steps = []
        for step in steps:
            dependencies = json.loads(step["dependencies_json"])
            public_steps.append(
                {
                    "step_id": step["step_id"],
                    "ordinal": step["ordinal"],
                    "title": step["title"],
                    "status": step["status"],
                    "dependencies": dependencies,
                    "min_day": step["min_day"],
                    "required_tools": json.loads(step["required_tools_json"]),
                    "required_event": step["required_event"],
                    "reversible": bool(step["reversible"]),
                }
            )
        return {
            "workflow_id": run["workflow_id"],
            "workflow_version": run["workflow_version"],
            "variant": run["variant"],
            "current_day": run["current_day"],
            "required_rollback_step": run["required_rollback_step"],
            "completed": run["completed_day"] is not None,
            "steps": public_steps,
            "applied_events": [
                {
                    "event_id": row[0],
                    "scheduled_day": row[1],
                    "event_type": row[2],
                    "payload": json.loads(row[3]),
                    "resolved": bool(row[4]),
                }
                for row in events
            ],
        }


def _deny(
    connection: sqlite3.Connection, day: int, action: str, step_id: str | None, reason: str
) -> None:
    _trace(connection, day, action, step_id, "denied", {"reason": reason})
    connection.commit()
    raise WorkflowError(reason)


def execute_step(database_path: Path, step_id: str, *, evidence_tools: set[str]) -> dict[str, Any]:
    """Execute one transition after enforcing evidence, dependency, event, and time gates."""

    with sqlite3.connect(database_path) as connection:
        run = _run(connection)
        day = int(run["current_day"])
        step = connection.execute(
            "SELECT * FROM dab_workflow_steps WHERE step_id=?", (step_id,)
        ).fetchone()
        if step is None:
            _deny(connection, day, "step_execution", step_id, "unknown workflow step")
        if step["status"] != "pending":
            _deny(connection, day, "step_execution", step_id, f"step is already {step['status']}")
        dependencies = json.loads(step["dependencies_json"])
        for dependency in dependencies:
            status = connection.execute(
                "SELECT status FROM dab_workflow_steps WHERE step_id=?", (dependency,)
            ).fetchone()[0]
            if status not in {"completed", "rolled_back"}:
                _deny(
                    connection,
                    day,
                    "step_execution",
                    step_id,
                    f"dependency {dependency} is not complete",
                )
        if day < int(step["min_day"]):
            _deny(
                connection,
                day,
                "step_execution",
                step_id,
                f"step requires simulated day {step['min_day']}",
            )
        if step["required_event"]:
            event = connection.execute(
                "SELECT applied FROM dab_workflow_events WHERE event_id=?",
                (step["required_event"],),
            ).fetchone()
            if event is None or not event[0]:
                _deny(
                    connection,
                    day,
                    "step_execution",
                    step_id,
                    f"required event {step['required_event']} has not arrived",
                )
        required_tools = set(json.loads(step["required_tools_json"]))
        if not required_tools <= evidence_tools:
            missing = sorted(required_tools - evidence_tools)
            _deny(
                connection,
                day,
                "step_execution",
                step_id,
                "missing evidence from: " + ", ".join(missing),
            )
        if run["required_rollback_step"] and int(step["ordinal"]) > 10:
            _deny(
                connection,
                day,
                "step_execution",
                step_id,
                f"resolve required rollback of {run['required_rollback_step']} before continuing",
            )
        if step["effect"]:
            _apply_effect(connection, run["workflow_id"], step_id, step["effect"])
        connection.execute(
            "UPDATE dab_workflow_steps SET status='completed', completed_day=? WHERE step_id=?",
            (day, step_id),
        )
        if int(step["ordinal"]) == WORKFLOW_STEP_COUNT:
            connection.execute("UPDATE dab_workflow_runs SET completed_day=?", (day,))
        _trace(
            connection,
            day,
            "step_execution",
            step_id,
            "success",
            {"evidence_tools": sorted(evidence_tools)},
        )
        connection.commit()
        return {
            "status": "completed",
            "step_id": step_id,
            "day": day,
            "workflow_completed": int(step["ordinal"]) == WORKFLOW_STEP_COUNT,
        }


def advance_time(database_path: Path, days: int) -> dict[str, Any]:
    """Advance simulated time and deterministically apply all newly due events."""

    if not 1 <= days <= 30:
        raise WorkflowError("days must be between 1 and 30")
    with sqlite3.connect(database_path) as connection:
        run = _run(connection)
        old_day = int(run["current_day"])
        new_day = old_day + days
        connection.execute("UPDATE dab_workflow_runs SET current_day=?", (new_day,))
        due = connection.execute(
            """SELECT event_id, event_type, payload_json
               FROM dab_workflow_events
               WHERE applied=0 AND scheduled_day<=?
               ORDER BY scheduled_day, event_id""",
            (new_day,),
        ).fetchall()
        applied: list[str] = []
        for event in due:
            event_id, event_type, payload_json = event
            payload = json.loads(payload_json)
            connection.execute(
                "UPDATE dab_workflow_events SET applied=1 WHERE event_id=?", (event_id,)
            )
            if event_type == "disruption":
                connection.execute(
                    "UPDATE dab_workflow_runs SET required_rollback_step=?",
                    (payload["required_rollback_step"],),
                )
            _trace(
                connection,
                new_day,
                "delayed_event",
                None,
                "success",
                {"event_id": event_id, **payload},
            )
            applied.append(str(event_id))
        _trace(
            connection,
            new_day,
            "time_advance",
            None,
            "success",
            {"from_day": old_day, "days": days, "events": applied},
        )
        connection.commit()
        return {
            "status": "advanced",
            "from_day": old_day,
            "current_day": new_day,
            "events_applied": applied,
        }


def rollback_step(
    database_path: Path, step_id: str, *, evidence_tools: set[str], reason: str
) -> dict[str, Any]:
    """Reverse the specifically required mutable transition and resolve its disruption."""

    with sqlite3.connect(database_path) as connection:
        run = _run(connection)
        day = int(run["current_day"])
        if run["required_rollback_step"] != step_id:
            _deny(
                connection,
                day,
                "rollback",
                step_id,
                "this step is not currently required to roll back",
            )
        step = connection.execute(
            "SELECT * FROM dab_workflow_steps WHERE step_id=?", (step_id,)
        ).fetchone()
        if step is None or not step["reversible"] or step["status"] != "completed":
            _deny(
                connection,
                day,
                "rollback",
                step_id,
                "step is not a completed reversible transition",
            )
        if "inspect_workflow" not in evidence_tools:
            _deny(
                connection,
                day,
                "rollback",
                step_id,
                "rollback requires evidence from inspect_workflow",
            )
        mutations = connection.execute(
            """SELECT mutation_id, table_name, key_json, column_name, before_json
               FROM dab_workflow_mutations
               WHERE step_id=? AND active=1
               ORDER BY mutation_id DESC""",
            (step_id,),
        ).fetchall()
        if not mutations:
            _deny(connection, day, "rollback", step_id, "step has no active mutation to reverse")
        for mutation_id, table_name, key_json, column_name, before_json in mutations:
            keys = json.loads(key_json)
            where = " AND ".join(f"{column}=?" for column in keys)
            connection.execute(
                f"UPDATE {table_name} SET {column_name}=? WHERE {where}",
                (json.loads(before_json), *keys.values()),
            )
            connection.execute(
                "UPDATE dab_workflow_mutations SET active=0 WHERE mutation_id=?", (mutation_id,)
            )
        connection.execute(
            "UPDATE dab_workflow_steps SET status='rolled_back', rolled_back_day=? WHERE step_id=?",
            (day, step_id),
        )
        connection.execute("UPDATE dab_workflow_runs SET required_rollback_step=NULL")
        connection.execute(
            "UPDATE dab_workflow_events SET resolved=1 WHERE event_type='disruption' AND applied=1"
        )
        _trace(
            connection,
            day,
            "rollback",
            step_id,
            "success",
            {"reason": reason, "evidence_tools": sorted(evidence_tools)},
        )
        connection.commit()
        return {"status": "rolled_back", "step_id": step_id, "day": day, "reason": reason}


def _mutate(
    connection: sqlite3.Connection,
    step_id: str,
    table_name: str,
    keys: dict[str, Any],
    column_name: str,
    after: Any,
) -> None:
    where = " AND ".join(f"{column}=?" for column in keys)
    before_row = connection.execute(
        f"SELECT {column_name} FROM {table_name} WHERE {where}", tuple(keys.values())
    ).fetchone()
    if before_row is None:
        raise WorkflowError(f"workflow fixture missing {table_name} row")
    before = before_row[0]
    connection.execute(
        f"UPDATE {table_name} SET {column_name}=? WHERE {where}", (after, *keys.values())
    )
    connection.execute(
        """INSERT INTO dab_workflow_mutations
           (step_id, table_name, key_json, column_name, before_json, after_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (step_id, table_name, json.dumps(keys), column_name, json.dumps(before), json.dumps(after)),
    )


def _apply_effect(
    connection: sqlite3.Connection, workflow_id: str, step_id: str, effect: str
) -> None:
    if effect == "regional_price_pilot":
        price = float(
            connection.execute(
                "SELECT unit_price FROM prices WHERE store_id='S001' AND product_id='P001'"
            ).fetchone()[0]
        )
        _mutate(
            connection,
            step_id,
            "prices",
            {"store_id": "S001", "product_id": "P001"},
            "unit_price",
            round(price * 0.95, 2),
        )
    elif effect == "vendor_inventory_pilot":
        units = int(
            connection.execute(
                "SELECT on_hand_units FROM inventory WHERE store_id='S002' AND product_id='P007'"
            ).fetchone()[0]
        )
        _mutate(
            connection,
            step_id,
            "inventory",
            {"store_id": "S002", "product_id": "P007"},
            "on_hand_units",
            units + 24,
        )
    elif effect == "recall_substitute_stage":
        units = int(
            connection.execute(
                "SELECT on_hand_units FROM inventory WHERE store_id='S001' AND product_id='P007'"
            ).fetchone()[0]
        )
        _mutate(
            connection,
            step_id,
            "inventory",
            {"store_id": "S001", "product_id": "P007"},
            "on_hand_units",
            units + 16,
        )
    elif effect == "recall_quarantine":
        lots = connection.execute(
            """SELECT store_id, product_id, lot_id
               FROM inventory_lots
               WHERE product_id='P003' AND lot_id='LOT-P003-A'
               ORDER BY store_id"""
        ).fetchall()
        for store_id, product_id, lot_id in lots:
            _mutate(
                connection,
                step_id,
                "inventory_lots",
                {
                    "store_id": store_id,
                    "product_id": product_id,
                    "lot_id": lot_id,
                },
                "quarantined",
                1,
            )
    elif effect == "recall_closeout":
        _mutate(connection, step_id, "recall_notices", {"notice_id": "RC001"}, "status", "closed")
    elif effect in {"regional_closeout", "vendor_closeout"}:
        # The terminal state is represented by the run completion marker and trace.
        return
    else:
        raise WorkflowError(f"unknown workflow effect {effect!r} for {workflow_id}")


def workflow_metrics(database_path: Path) -> dict[str, Any]:
    """Measure temporal completion and recovery from the persisted execution trace."""

    with sqlite3.connect(database_path) as connection:
        run = _run(connection)
        steps = connection.execute(
            """SELECT step_id, ordinal, dependencies_json, status
               FROM dab_workflow_steps ORDER BY ordinal"""
        ).fetchall()
        achieved = {
            row["step_id"] for row in steps if row["status"] in {"completed", "rolled_back"}
        }
        spans = [
            abs(int(row["ordinal"]) - int(dependency[1:]))
            for row in steps
            if row["step_id"] in achieved
            for dependency in json.loads(row["dependencies_json"])
            if dependency in achieved
        ]
        invalid = int(
            connection.execute(
                "SELECT COUNT(*) FROM dab_workflow_trace WHERE status='denied'"
            ).fetchone()[0]
        )
        rollbacks = int(
            connection.execute(
                """SELECT COUNT(*) FROM dab_workflow_trace
                   WHERE event_type='rollback' AND status='success'"""
            ).fetchone()[0]
        )
        events_applied = int(
            connection.execute(
                "SELECT COUNT(*) FROM dab_workflow_events WHERE applied=1"
            ).fetchone()[0]
        )
        disruption = connection.execute(
            "SELECT applied, resolved FROM dab_workflow_events WHERE event_type='disruption'"
        ).fetchone()
        required = len(steps)
        completed = len(achieved)
        completion = completed / required
        dependency_integrity = max(0.0, 1.0 - invalid / required)
        temporal_integrity = min(1.0, int(run["current_day"]) / WORKFLOW_MINIMUM_DAYS)
        recovery = (
            1.0
            if disruption is None
            else float(bool(disruption[0] and disruption[1] and rollbacks))
        )
        outcome = round(
            0.55 * completion
            + 0.20 * dependency_integrity
            + 0.15 * temporal_integrity
            + 0.10 * recovery,
            6,
        )
        digest_payload = {
            "workflow_id": run["workflow_id"],
            "variant": run["variant"],
            "day": run["current_day"],
            "steps": [(row["step_id"], row["status"]) for row in steps],
            "events": connection.execute(
                """SELECT event_id, payload_json, applied, resolved
                   FROM dab_workflow_events ORDER BY event_id"""
            ).fetchall(),
        }
        return {
            "workflow_id": run["workflow_id"],
            "workflow_version": run["workflow_version"],
            "workflow_completed": bool(run["completed_day"] is not None),
            "steps_completed": completed,
            "steps_required": required,
            "completion_rate": round(completion, 6),
            "dependency_span": max(spans, default=0),
            "dependency_span_target": WORKFLOW_DEPENDENCY_SPAN,
            "simulated_days": int(run["current_day"]),
            "minimum_simulated_days": WORKFLOW_MINIMUM_DAYS,
            "invalid_transition_count": invalid,
            "rollback_count": rollbacks,
            "delayed_events_applied": events_applied,
            "recovery_satisfied": bool(recovery),
            "outcome_score": outcome,
            "state_digest": hashlib.sha256(
                json.dumps(digest_payload, sort_keys=True, default=list).encode()
            ).hexdigest(),
        }
