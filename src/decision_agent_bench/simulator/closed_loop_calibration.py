"""Public calibration assumptions and deterministic sensitivity analysis for v0.7."""

from __future__ import annotations

import hashlib
import json
import statistics
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from decision_agent_bench.simulator.closed_loop import REGIMES, ClosedLoopConfig
from decision_agent_bench.simulator.closed_loop_baselines import run_baseline

CALIBRATION_SOURCES = (
    {
        "construct": "retail sales, inventories, and seasonal variation",
        "source": "U.S. Census Bureau Monthly Retail Trade Survey",
        "url": "https://www.census.gov/retail/mrts/about_the_surveys.html",
        "use": "motivates store-level sales/inventory outputs and explicit seasonal factors",
        "status": "structural grounding; simulator levels are not fitted to confidential microdata",
    },
    {
        "construct": "own-price and cross-product demand response",
        "source": "USDA Economic Research Service Food Demand Analysis",
        "url": "https://www.ers.usda.gov/topics/food-choices-health/food-consumption-demand/food-demand-analysis",
        "use": "grounds negative own-price elasticity and positive within-category substitution",
        "status": "range-informed; convenience-store product coefficients remain synthetic",
    },
    {
        "construct": "fresh-food retail loss",
        "source": "USDA ERS Food Availability and Food Loss data",
        "url": "https://www.ers.usda.gov/data-products/food-availability-per-capita-data-system/food-loss/",
        "use": "grounds higher loss exposure for perishable categories",
        "status": "range-informed; episode spoilage is intentionally stress-testable",
    },
    {
        "construct": "food price measurement",
        "source": "U.S. Bureau of Labor Statistics Consumer Price Index",
        "url": "https://www.bls.gov/cpi/",
        "use": "motivates separate nominal price state and explicit price interventions",
        "status": "structural grounding; the benchmark does not forecast CPI",
    },
)

PARAMETER_RANGES = {
    "demand_scale": {"low": 0.8, "base": 1.0, "high": 1.2, "provenance": "synthetic"},
    "price_elasticity_scale": {
        "low": 0.75,
        "base": 1.0,
        "high": 1.25,
        "provenance": "USDA range-informed",
    },
    "return_rate_scale": {
        "low": 0.5,
        "base": 1.0,
        "high": 1.5,
        "provenance": "synthetic",
    },
    "lead_time_scale": {
        "low": 0.75,
        "base": 1.0,
        "high": 1.5,
        "provenance": "synthetic",
    },
    "disruption_scale": {
        "low": 0.5,
        "base": 1.0,
        "high": 1.5,
        "provenance": "synthetic stress parameter",
    },
}


def _digest_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def write_calibration_report(
    output_path: Path,
    *,
    seeds: tuple[int, ...] = (20260805, 20260806, 20260807),
    horizon_days: int = 28,
) -> dict[str, Any]:
    """Run regime and one-at-a-time parameter checks and write a content-addressed report."""

    if not seeds:
        raise ValueError("at least one calibration seed is required")
    regime_runs: list[dict[str, Any]] = []
    sensitivity_runs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="dab-v07-calibration-") as temporary:
        root = Path(temporary)
        for regime in REGIMES:
            for seed in seeds:
                config = ClosedLoopConfig(
                    seed=seed, horizon_days=horizon_days, regime=regime
                )
                run = run_baseline(
                    root / f"regime-{regime}-{seed}", "information_matched", config
                )
                regime_runs.append(
                    {
                        "regime": regime,
                        "seed": seed,
                        **_outcome_metrics(run.outcome),
                    }
                )
        base = ClosedLoopConfig(
            seed=seeds[0], horizon_days=horizon_days, regime="stress_mixed"
        )
        base_run = run_baseline(root / "sensitivity-base", "information_matched", base)
        sensitivity_runs.append(
            {
                "parameter": "base",
                "level": "base",
                "value": 1.0,
                **_outcome_metrics(base_run.outcome),
            }
        )
        for parameter, bounds in PARAMETER_RANGES.items():
            for level in ("low", "high"):
                value = float(bounds[level])
                config = replace(base, **{parameter: value})
                run = run_baseline(
                    root / f"sensitivity-{parameter}-{level}",
                    "information_matched",
                    config,
                )
                sensitivity_runs.append(
                    {
                        "parameter": parameter,
                        "level": level,
                        "value": value,
                        **_outcome_metrics(run.outcome),
                    }
                )
    regime_summary = []
    for regime in REGIMES:
        rows = [row for row in regime_runs if row["regime"] == regime]
        regime_summary.append(
            {
                "regime": regime,
                "n": len(rows),
                "gross_profit_mean": round(
                    statistics.fmean(float(row["gross_profit"]) for row in rows), 2
                ),
                "service_level_mean": round(
                    statistics.fmean(float(row["service_level"]) for row in rows), 6
                ),
                "spoilage_mean": round(
                    statistics.fmean(float(row["spoiled_units"]) for row in rows), 3
                ),
            }
        )
    payload: dict[str, Any] = {
        "schema_version": "0.7.0",
        "status": "engineering calibration; not external predictive validation",
        "horizon_days": horizon_days,
        "seeds": list(seeds),
        "policy": "information_matched",
        "sources": list(CALIBRATION_SOURCES),
        "parameter_ranges": PARAMETER_RANGES,
        "regime_summary": regime_summary,
        "regime_runs": regime_runs,
        "one_at_a_time_sensitivity": sensitivity_runs,
        "claim_boundary": (
            "The report verifies deterministic sensitivity and plausible directional behavior. "
            "It does not establish convenience-retail forecast accuracy or external validity."
        ),
    }
    payload["report_sha256"] = _digest_payload(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def verify_calibration_report(path: Path) -> dict[str, Any]:
    """Verify report schema, sources, coverage, and its content digest."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    issues = []
    digest = payload.pop("report_sha256", None)
    if payload.get("schema_version") != "0.7.0":
        issues.append("unsupported calibration report schema")
    if {row.get("regime") for row in payload.get("regime_summary", [])} != set(REGIMES):
        issues.append("calibration report does not cover every regime")
    if {row.get("parameter") for row in payload.get("one_at_a_time_sensitivity", [])} != {
        "base",
        *PARAMETER_RANGES,
    }:
        issues.append("calibration report does not cover every sensitivity parameter")
    if not all(
        str(source.get("url", "")).startswith("https://")
        for source in payload.get("sources", [])
    ):
        issues.append("calibration source URL is missing or not HTTPS")
    if digest != _digest_payload(payload):
        issues.append("calibration report digest mismatch")
    payload["report_sha256"] = digest
    return {"verified": not issues, "issues": issues, "report": payload}


def _outcome_metrics(outcome: Any) -> dict[str, Any]:
    selected = asdict(outcome)
    selected.pop("final_digest", None)
    return selected
