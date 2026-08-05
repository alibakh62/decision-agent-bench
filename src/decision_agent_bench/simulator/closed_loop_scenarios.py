"""Published causal interventions and replay helpers for the v0.7 world."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from decision_agent_bench.simulator.closed_loop import (
    ClosedLoopConfig,
    ClosedLoopEnvironment,
    EpisodeOutcome,
    generate_closed_loop_world,
    validate_closed_loop_world,
)

CAUSAL_SCENARIOS = (
    "replenishment",
    "pricing",
    "shelf_allocation",
    "promotion_approval",
)


@dataclass(frozen=True)
class CausalScenarioResult:
    """Outcome comparison under matched exogenous draws and different feasible actions."""

    scenario: str
    seed: int
    alternative_a: str
    alternative_b: str
    outcome_a: EpisodeOutcome
    outcome_b: EpisodeOutcome
    gross_profit_delta_b_minus_a: float
    service_level_delta_b_minus_a: float
    later_state_changed: bool


def replay_actions(
    output_dir: Path,
    config: ClosedLoopConfig,
    actions: list[dict[str, Any]],
    *,
    overwrite: bool = False,
) -> EpisodeOutcome:
    """Replay a declared day/action sequence against matched keyed exogenous draws."""

    database = generate_closed_loop_world(output_dir, config, overwrite=overwrite)
    actions_by_day: dict[int, list[dict[str, Any]]] = {}
    for action in actions:
        day = action.get("day")
        if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= config.horizon_days:
            raise ValueError("every action day must be within the configured episode horizon")
        actions_by_day.setdefault(day, []).append(action)
    with ClosedLoopEnvironment(database) as environment:
        for day in range(1, config.horizon_days + 1):
            for action in actions_by_day.get(day, []):
                _apply_action(environment, action)
            environment.advance_day()
        outcome = environment.outcome()
    validate_closed_loop_world(database)
    (output_dir / "replay.json").write_text(
        json.dumps(
            {
                "schema_version": "0.7.0",
                "config": asdict(config),
                "actions": actions,
                "outcome": asdict(outcome),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return outcome


def run_causal_scenario(
    output_dir: Path,
    scenario: str,
    config: ClosedLoopConfig | None = None,
    *,
    overwrite: bool = False,
) -> CausalScenarioResult:
    """Run both published alternatives under the same seed and latent event stream."""

    if scenario not in CAUSAL_SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    selected = config or ClosedLoopConfig(horizon_days=28)
    actions_a, actions_b, label_a, label_b = _scenario_actions(scenario, selected)
    output_dir.mkdir(parents=True, exist_ok=True)
    outcome_a = replay_actions(
        output_dir / "alternative-a", selected, actions_a, overwrite=overwrite
    )
    outcome_b = replay_actions(
        output_dir / "alternative-b", selected, actions_b, overwrite=overwrite
    )
    result = CausalScenarioResult(
        scenario=scenario,
        seed=selected.seed,
        alternative_a=label_a,
        alternative_b=label_b,
        outcome_a=outcome_a,
        outcome_b=outcome_b,
        gross_profit_delta_b_minus_a=round(
            outcome_b.gross_profit - outcome_a.gross_profit, 2
        ),
        service_level_delta_b_minus_a=round(
            outcome_b.service_level - outcome_a.service_level, 6
        ),
        later_state_changed=(
            outcome_a.final_digest != outcome_b.final_digest
            and (
                outcome_a.gross_profit != outcome_b.gross_profit
                or outcome_a.service_level != outcome_b.service_level
                or outcome_a.ending_cash != outcome_b.ending_cash
            )
        ),
    )
    (output_dir / "causal-comparison.json").write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def _scenario_actions(
    scenario: str, config: ClosedLoopConfig
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    if scenario == "replenishment":
        return (
            [],
            [
                {
                    "day": 1,
                    "action_type": "place_order",
                    "store_id": "S001",
                    "product_id": "P001",
                    "cases": 6,
                }
            ],
            "no replenishment",
            "order six cases of P001",
        )
    if scenario == "pricing":
        return (
            [],
            [
                {
                    "day": 1,
                    "action_type": "change_price",
                    "store_id": "S001",
                    "product_id": "P001",
                    "new_price": 2.56,
                }
            ],
            "hold price",
            "raise S001 P001 price within autonomous authority",
        )
    if scenario == "shelf_allocation":
        return (
            [],
            [
                {
                    "day": 1,
                    "action_type": "allocate_shelf",
                    "store_id": "S001",
                    "allocations": {"P001": 28, "P004": 4},
                }
            ],
            "hold shelf allocation",
            "shift shelf capacity from P004 to P001",
        )
    start = config.start_date
    end = str(date.fromisoformat(config.start_date) + timedelta(days=6))
    payload = {
        "store_id": "S001",
        "product_id": "P001",
        "start_date": start,
        "end_date": end,
        "discount_pct": 0.15,
    }
    return (
        [
            {
                "day": 1,
                "action_type": "approval_promotion",
                "payload": payload,
                "approved": False,
            }
        ],
        [
            {
                "day": 1,
                "action_type": "approval_promotion",
                "payload": payload,
                "approved": True,
            }
        ],
        "promotion rejected and aborted",
        "promotion approved and resumed",
    )

def _apply_action(environment: ClosedLoopEnvironment, action: dict[str, Any]) -> None:
    action_type = action.get("action_type")
    if action_type == "place_order":
        environment.place_order(
            str(action["store_id"]),
            str(action["product_id"]),
            int(action["cases"]),
            actor="scenario-policy",
        )
    elif action_type == "change_price":
        environment.change_price(
            str(action["store_id"]),
            str(action["product_id"]),
            float(action["new_price"]),
            actor="scenario-policy",
        )
    elif action_type == "allocate_shelf":
        environment.allocate_shelf(
            str(action["store_id"]),
            {str(key): int(value) for key, value in action["allocations"].items()},
            actor="scenario-policy",
        )
    elif action_type == "approval_promotion":
        payload = dict(action["payload"])
        approval_id = environment.request_approval(
            "promotion", actor="scenario-policy", payload=payload
        )
        approved = bool(action["approved"])
        environment.resolve_approval(approval_id, approved=approved)
        if approved:
            environment.schedule_promotion(
                str(payload["store_id"]),
                str(payload["product_id"]),
                start_date=str(payload["start_date"]),
                end_date=str(payload["end_date"]),
                discount_pct=float(payload["discount_pct"]),
                actor="scenario-policy",
                approval_id=approval_id,
            )
        else:
            environment.abort_approval(approval_id, actor="scenario-policy")
    else:
        raise ValueError(f"unsupported replay action type: {action_type}")
