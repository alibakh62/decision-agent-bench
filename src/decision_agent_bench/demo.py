"""Interactive DecisionAgentBench Lab for replaying and auditing evaluations."""

from __future__ import annotations

import json
import tempfile
import time
from html import escape
from pathlib import Path
from typing import Any

from decision_agent_bench.evals.cases import CASES_BY_ID
from decision_agent_bench.evals.instances import expanded_instance_catalog
from decision_agent_bench.evals.runtime import apply_perturbation, perturbation_kind
from decision_agent_bench.evals.scorer import grade_submission, parse_submission
from decision_agent_bench.lab import (
    REPLAY_AGENTS_BY_KEY,
    agent_choices,
    error_status_html,
    idle_status_html,
    run_replay,
    running_status_html,
    score_explainer_html,
    trace_workbench_html,
    write_run_report,
)
from decision_agent_bench.lab_runtime import run_live_evaluation
from decision_agent_bench.simulator import GenerationConfig, RetailEnvironment, generate_world
from decision_agent_bench.simulator.workflow import workflow_instance_catalog

_CATALOG = {item["instance_id"]: item for item in expanded_instance_catalog()}
_WORKFLOW_CATALOG = {item["instance_id"]: item for item in workflow_instance_catalog()}
_WORLD_TEMPORARY_DIRECTORY: tempfile.TemporaryDirectory[str] | None = None
_WORLD_PATH: Path | None = None
_RUN_WORLD_TEMPORARY_DIRECTORY: tempfile.TemporaryDirectory[str] | None = None
_RUN_WORLD_PATHS: dict[tuple[str, str], Path] = {}

QUERY_LIBRARY = {
    "Regional sales trend": """
        SELECT s.region_id, substr(t.sold_at, 1, 10) AS day,
               SUM(t.units) AS units, ROUND(SUM(t.net_sales), 2) AS net_sales
        FROM transactions t JOIN stores s USING(store_id)
        WHERE date(t.sold_at) >= date('2026-06-30', '-20 days')
        GROUP BY s.region_id, day ORDER BY day DESC, s.region_id LIMIT 18
    """,
    "Feed freshness": """
        SELECT feed_name, scope, last_complete_at, status, expected_frequency_minutes
        FROM data_feed_status ORDER BY feed_name, scope
    """,
    "Active recall": """
        SELECT r.notice_id, r.product_id, r.affected_lot_id, r.issued_at, r.status,
               SUM(l.on_hand_units) AS traced_units
        FROM recall_notices r LEFT JOIN inventory_lots l
          ON r.product_id=l.product_id AND r.affected_lot_id=l.lot_id
        WHERE r.status='active' GROUP BY r.notice_id
    """,
    "Refund clusters": """
        SELECT customer_id, store_id, COUNT(*) AS refunds,
               ROUND(SUM(amount), 2) AS refunded_amount,
               SUM(CASE WHEN receipt_present=0 THEN 1 ELSE 0 END) AS no_receipt
        FROM refunds GROUP BY customer_id, store_id
        ORDER BY refunds DESC, refunded_amount DESC LIMIT 12
    """,
}

_DEMO_CSS = """
:root {
  --lab-bg: #07111f;
  --lab-panel: #0c1828;
  --lab-panel-raised: #111f31;
  --lab-border: #26364b;
  --lab-border-strong: #38506e;
  --lab-text: #e8eef7;
  --lab-muted: #94a3b8;
  --lab-indigo: #536dfe;
  --lab-cyan: #45c8d8;
  --lab-green: #6fd08c;
  --lab-amber: #f3b35b;
  --lab-red: #ef6a6a;
}
html, body, gradio-app, .gradio-container, .main, main {
  background: var(--lab-bg) !important;
  color: var(--lab-text) !important;
  margin: 0 !important;
  max-width: none !important;
  width: 100% !important;
}
.gradio-container {
  box-sizing: border-box !important;
  max-width: none !important;
  padding: 20px 28px 36px !important;
  width: 100vw !important;
}
.contain, .wrap, .app { margin-left: 0 !important; margin-right: 0 !important; max-width: none !important; }
.lab-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 12px;
}
.lab-header h1, .score-workbench h2, .inspector-panel h3 {
  color: var(--lab-text);
  letter-spacing: -0.025em;
  margin: 0;
}
.lab-header h1 { font-size: 26px; }
.lab-header p, .score-title-row p { color: var(--lab-muted); margin: 4px 0 0; }
.mode-badge, .notice-inline, .status-badge, .dimension-chip {
  border: 1px solid #256b62;
  border-radius: 7px;
  color: #74dec3;
  display: inline-flex;
  font-size: 12px;
  font-weight: 650;
  padding: 6px 9px;
}
.config-strip, .run-shell, .score-shell, .decision-shell, .task-shell {
  background: var(--lab-panel) !important;
  border: 1px solid var(--lab-border) !important;
  border-radius: 9px !important;
  padding: 12px !important;
}
.config-strip { margin-bottom: 12px; }
.config-strip label, .config-strip .wrap { color: var(--lab-text) !important; }
.agent-note { min-height: 94px; }
.agent-note strong { display: block; font-size: 16px; margin: 4px 0; }
.agent-note p { color: var(--lab-muted); line-height: 1.45; margin: 0 0 8px; }
.eyebrow {
  color: #8fa4bf;
  display: block;
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.075em;
  text-transform: uppercase;
}
.run-status {
  align-items: center;
  background: var(--lab-panel);
  border: 1px solid var(--lab-border);
  border-radius: 9px;
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(205px, .8fr) 2.4fr;
  margin: 12px 0;
  padding: 13px 16px;
}
.run-status > div { align-items: center; display: grid; grid-template-columns: 14px 1fr; }
.run-status small { color: var(--lab-muted); grid-column: 2; }
.status-dot { background: var(--lab-green); border-radius: 50%; height: 9px; width: 9px; }
.run-status dl { display: grid; gap: 18px; grid-template-columns: repeat(4, 1fr); margin: 0; }
.run-status dl div { border-left: 1px solid var(--lab-border); padding-left: 16px; }
.run-status dt { color: var(--lab-muted); font-size: 11px; }
.run-status dd { color: var(--lab-text); font-size: 13px; font-weight: 650; margin: 2px 0 0; }
.run-shell { padding: 0 !important; overflow: hidden; }
.trace-column { border-right: 1px solid var(--lab-border); padding: 10px !important; }
.inspector-column { padding: 0 !important; }
.inspector-panel { min-height: 565px; padding: 17px; }
.panel-heading { align-items: flex-start; display: flex; justify-content: space-between; gap: 16px; }
.panel-heading h3 { font-size: 19px; margin-top: 3px; }
.inspector-meta { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 18px 0; }
.inspector-meta div { background: #091524; border: 1px solid var(--lab-border); border-radius: 6px; padding: 9px; }
.inspector-meta span { color: var(--lab-muted); display: block; font-size: 11px; }
.inspector-meta strong { display: block; font-size: 12px; margin-top: 3px; overflow-wrap: anywhere; }
.event-summary { color: #c7d2e2; line-height: 1.5; }
.inspector-panel details, .score-section {
  background: #091524;
  border: 1px solid var(--lab-border);
  border-radius: 7px;
  margin-top: 10px;
  padding: 10px 12px;
}
.inspector-panel summary, .score-section > summary { color: var(--lab-text); cursor: pointer; font-weight: 650; }
.code-block {
  background: #050d18;
  border: 1px solid #1e3047;
  border-radius: 6px;
  color: #c4d2e5;
  font-size: 11px;
  line-height: 1.5;
  max-height: 225px;
  overflow: auto;
  padding: 11px;
  white-space: pre-wrap;
}
.score-lineage { border-top: 1px solid var(--lab-border); margin-top: 16px; padding-top: 14px; }
.score-lineage p, .muted, .robustness-note { color: var(--lab-muted); font-size: 12px; line-height: 1.5; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.dimension-chip { border-color: #384d70; color: #b5c4db; padding: 4px 7px; }
.run-phase {
  align-items: center;
  background: #0a1727;
  border: 1px solid var(--lab-border);
  border-radius: 9px;
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(260px, .8fr) 2.4fr;
  margin: 12px 0;
  min-height: 66px;
  padding: 12px 16px;
}
.run-phase > div { display: grid; grid-template-columns: 14px 1fr; }
.run-phase .phase-indicator {
  align-self: center;
  background: #5c708e;
  border-radius: 50%;
  height: 9px;
  width: 9px;
}
.run-phase strong { color: var(--lab-text); }
.run-phase small { color: var(--lab-muted); grid-column: 2; margin-top: 2px; }
.run-phase p { color: var(--lab-muted); font-size: 12px; margin: 0; }
.run-phase dl { display: grid; gap: 16px; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 0; }
.run-phase dl div { border-left: 1px solid var(--lab-border); min-width: 0; padding-left: 13px; }
.run-phase dt { color: var(--lab-muted); font-size: 10px; }
.run-phase dd { color: var(--lab-text); font-size: 12px; font-weight: 650; margin: 3px 0 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-phase.complete .phase-indicator { background: var(--lab-green); box-shadow: 0 0 0 4px #183d2b; }
.run-phase.running .phase-indicator { animation: dab-pulse 1.25s ease-in-out infinite; background: var(--lab-indigo); box-shadow: 0 0 0 4px #1a2855; }
.run-phase.error { border-color: #753e48; }
.run-phase.error .phase-indicator { background: var(--lab-red); box-shadow: 0 0 0 4px #44202a; }
@keyframes dab-pulse { 50% { opacity: .45; transform: scale(.75); } }
.trace-empty {
  align-items: center;
  background: var(--lab-panel);
  border: 1px dashed #38506e;
  border-radius: 9px;
  display: flex;
  justify-content: center;
  min-height: 430px;
  padding: 36px;
  text-align: center;
}
.trace-empty > div { max-width: 620px; }
.trace-empty h3 { color: var(--lab-text); font-size: 22px; margin: 8px 0; }
.trace-empty p { color: var(--lab-muted); line-height: 1.6; margin: 0; }
.live-trace {
  background: #081321;
  border: 1px solid var(--lab-border);
  border-radius: 9px;
  color: var(--lab-text);
  overflow: hidden;
}
.trace-selector, .inspector-tab-radio { opacity: 0; pointer-events: none; position: absolute; }
.trace-run-header {
  align-items: center;
  background: #0d1b2c;
  border-bottom: 1px solid var(--lab-border);
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(210px, .65fr) 2.7fr;
  min-height: 72px;
  padding: 11px 18px;
}
.trace-run-header > div { align-items: center; display: grid; grid-template-columns: 18px 1fr; }
.trace-status-dot { background: var(--lab-green); border-radius: 50%; box-shadow: 0 0 0 4px #173d2b; height: 9px; width: 9px; }
.trace-run-header strong { font-size: 14px; }
.trace-run-header small { color: var(--lab-muted); grid-column: 2; }
.trace-run-header dl { display: grid; grid-template-columns: 1.1fr 1.35fr 1.25fr .65fr .6fr .65fr .8fr; margin: 0; }
.trace-run-header dl div { border-left: 1px solid var(--lab-border); min-width: 0; padding: 0 13px; }
.trace-run-header dt { color: var(--lab-muted); font-size: 10px; }
.trace-run-header dd { font-size: 12px; font-weight: 650; margin: 3px 0 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.trace-layout { display: grid; grid-template-columns: minmax(0, 58%) minmax(420px, 42%); min-height: 650px; }
.trace-event-list {
  border-right: 1px solid var(--lab-border);
  max-height: 720px;
  overflow: auto;
  scrollbar-color: #34485f #091524;
  scrollbar-width: thin;
}
.trace-event-list::-webkit-scrollbar { height: 9px; width: 9px; }
.trace-event-list::-webkit-scrollbar-track { background: #091524; }
.trace-event-list::-webkit-scrollbar-thumb { background: #34485f; border: 2px solid #091524; border-radius: 8px; }
.trace-table-header, .trace-event-row {
  align-items: stretch;
  display: grid;
  grid-template-columns: 14% 16% 38% 16% 16%;
}
.trace-table-header {
  background: #07111e;
  border-bottom: 1px solid var(--lab-border);
  color: var(--lab-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .04em;
  padding: 0 12px;
  position: sticky;
  text-transform: uppercase;
  top: 0;
  z-index: 3;
}
.trace-table-header span { padding: 11px 10px; }
.trace-event-row {
  border-bottom: 1px solid #1c2a3c;
  cursor: pointer;
  min-height: 54px;
  padding: 0 12px;
  transition: background .12s ease, border-color .12s ease;
}
.trace-event-row:hover { background: #12243d; }
.trace-event-row > span { align-items: center; display: flex; min-width: 0; padding: 8px 10px; }
.timeline-cell { color: #afbed1; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px; gap: 10px; position: relative; }
.timeline-cell::after { background: #315273; content: ""; height: 100%; left: 14px; position: absolute; top: 50%; width: 2px; }
.trace-event-row:last-child .timeline-cell::after { display: none; }
.timeline-cell i { background: #65b77c; border: 2px solid #0a1523; border-radius: 50%; flex: 0 0 auto; height: 10px; position: relative; width: 10px; z-index: 2; }
.trace-event-row.warning .timeline-cell i { background: var(--lab-amber); }
.trace-event-row.submitted .timeline-cell i, .trace-event-row.scored .timeline-cell i { background: var(--lab-cyan); }
.actor-cell { color: #aebdd0; font-size: 12px; font-weight: 650; }
.event-cell { align-items: flex-start !important; flex-direction: column; justify-content: center; }
.event-cell strong { color: #e6edf7; font-size: 12px; }
.event-cell small { color: #91a2b8; display: -webkit-box; font-size: 10px; line-height: 1.35; margin-top: 2px; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.evidence-cell { color: #9db5d5; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px; overflow: hidden; text-overflow: ellipsis; }
.outcome-cell b { border: 1px solid #376b48; border-radius: 999px; color: var(--lab-green); font-size: 9px; padding: 3px 7px; }
.trace-event-row.warning .outcome-cell b { border-color: #79592c; color: var(--lab-amber); }
.trace-event-row.submitted .outcome-cell b, .trace-event-row.scored .outcome-cell b { border-color: #2d7180; color: var(--lab-cyan); }
.trace-inspectors { background: #0a1625; min-width: 0; }
.trace-inspector-card { display: none; flex-direction: column; min-height: 650px; }
.trace-inspector-card > header { align-items: center; border-bottom: 1px solid var(--lab-border); display: flex; justify-content: space-between; min-height: 74px; padding: 12px 20px; }
.trace-inspector-card h3 { color: var(--lab-text); font-size: 18px; margin: 4px 0 0; }
.status-badge.warning { border-color: #79592c; color: var(--lab-amber); }
.status-badge.submitted, .status-badge.scored { border-color: #2d7180; color: var(--lab-cyan); }
.inspector-tabs { border-bottom: 1px solid var(--lab-border); display: flex; gap: 26px; padding: 0 20px; }
.inspector-tabs label { border-bottom: 3px solid transparent; color: var(--lab-muted); cursor: pointer; font-size: 12px; font-weight: 650; padding: 14px 2px 11px; }
.trace-inspector-card:has(.inspector-tab-radio.details:checked) .inspector-tabs label.details,
.trace-inspector-card:has(.inspector-tab-radio.payload:checked) .inspector-tabs label.payload,
.trace-inspector-card:has(.inspector-tab-radio.impact:checked) .inspector-tabs label.impact { border-color: var(--lab-indigo); color: #cbd5ff; }
.inspector-tab-panels { padding: 18px 20px 22px; }
.inspector-tab-panel { display: none; }
.trace-inspector-card:has(.inspector-tab-radio.details:checked) .inspector-tab-panel.details,
.trace-inspector-card:has(.inspector-tab-radio.payload:checked) .inspector-tab-panel.payload,
.trace-inspector-card:has(.inspector-tab-radio.impact:checked) .inspector-tab-panel.impact { display: block; }
.inspector-tab-panel h4 { color: #ced8e6; font-size: 12px; margin: 15px 0 8px; }
.inspector-tab-panel h4:first-child { margin-top: 0; }
.trace-metadata { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); margin: 0 0 16px; }
.trace-metadata div { min-width: 0; padding-right: 8px; }
.trace-metadata dt, .payload-summary dt { color: var(--lab-muted); font-size: 9px; }
.trace-metadata dd, .payload-summary dd { color: #dce5f1; font-size: 11px; font-weight: 650; margin: 3px 0 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.payload-summary { background: #0d1d2f; border: 1px solid var(--lab-border); border-radius: 6px; display: grid; grid-template-columns: repeat(3, 1fr); margin: 0; }
.payload-summary div { border-right: 1px solid var(--lab-border); padding: 9px 12px; }
.payload-summary div:last-child { border-right: 0; }
.impact-verdict {
  background: #0d1d2f;
  border: 1px solid #304866;
  border-radius: 7px;
  padding: 12px 13px;
}
.impact-verdict strong { color: #dce8f6; display: block; font-size: 15px; margin-top: 4px; }
.impact-facts { display: grid; gap: 8px; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 10px; }
.impact-fact { background: #091524; border: 1px solid var(--lab-border); border-radius: 6px; padding: 9px; }
.impact-fact span { color: var(--lab-muted); display: block; font-size: 9px; }
.impact-fact strong { color: #dce5f1; display: block; font-size: 11px; margin-top: 3px; }
.impact-reasons { display: grid; gap: 8px; margin-top: 12px; }
.impact-reasons article { background: #0d1d2f; border-left: 3px solid #5d75e8; border-radius: 5px; padding: 10px 12px; }
.impact-reasons strong { color: #dfe7f3; font-size: 12px; }
.impact-reasons p { color: #a8b7ca; font-size: 11px; line-height: 1.55; margin: 4px 0 0; }
.score-causality-note { border-top: 1px solid var(--lab-border); color: var(--lab-muted); font-size: 11px; line-height: 1.55; margin-top: 18px; padding-top: 14px; }
.score-shell { margin-top: 12px; padding: 0 !important; }
.score-workbench { background: var(--lab-panel); padding: 18px; }
.score-title-row { align-items: flex-start; display: flex; gap: 20px; justify-content: space-between; }
.score-title-row h2 { font-size: 22px; margin-top: 3px; }
.overall-score { align-items: end; display: grid; gap: 4px; text-align: right; }
.overall-score span { color: var(--lab-muted); font-size: 11px; }
.overall-score strong { color: #70ddc3; font-size: 30px; line-height: 1; }
.validity-warning {
  align-items: center;
  background: #1b1a13;
  border: 1px solid #6a552b;
  border-radius: 7px;
  color: #d9c79f;
  display: grid;
  gap: 12px;
  grid-template-columns: auto 1fr;
  margin: 14px 0;
  padding: 10px 12px;
}
.validity-warning strong { color: var(--lab-amber); }
.score-section { background: #0a1625; margin-top: 9px; }
.score-section > summary { font-size: 14px; padding: 2px 0 7px; }
.equation { display: grid; gap: 8px; padding: 12px 4px 4px; }
.equation code { color: #c7d2e2; font-size: 12px; overflow-wrap: anywhere; }
.equation strong { color: #82d99a; font-size: 12px; }
.dimension-selector { opacity: 0; pointer-events: none; position: absolute; }
.dimension-grid { display: grid; gap: 8px; grid-template-columns: repeat(7, minmax(125px, 1fr)); margin-top: 10px; }
.dimension-card { background: var(--lab-panel-raised); border: 1px solid var(--lab-border-strong); border-radius: 7px; cursor: pointer; min-width: 0; padding: 11px; transition: background .12s ease, box-shadow .12s ease; }
.dimension-card:hover { background: #15243a; }
.dimension-card.task_effectiveness { border-color: #3c70a5; }
.dimension-card.decision_quality { border-color: #7059a8; }
.dimension-card.safety { border-color: #3e7b55; }
.dimension-card.recovery { border-color: #ad7634; }
.dimension-card.explainability { border-color: #376f88; }
.dimension-card.calibration { border-color: #5b7399; }
.dimension-card.efficiency { border-color: #3c8390; }
.dimension-scorecards:has(.dimension-selector.task_effectiveness:checked) .dimension-card.task_effectiveness,
.dimension-scorecards:has(.dimension-selector.decision_quality:checked) .dimension-card.decision_quality,
.dimension-scorecards:has(.dimension-selector.safety:checked) .dimension-card.safety,
.dimension-scorecards:has(.dimension-selector.recovery:checked) .dimension-card.recovery,
.dimension-scorecards:has(.dimension-selector.explainability:checked) .dimension-card.explainability,
.dimension-scorecards:has(.dimension-selector.calibration:checked) .dimension-card.calibration,
.dimension-scorecards:has(.dimension-selector.efficiency:checked) .dimension-card.efficiency { background: #182943; box-shadow: inset 0 0 0 1px #7182ff; }
.dimension-card-content { display: block; }
.dimension-card-heading { min-height: 39px; }
.dimension-card-heading > span, .dimension-card-heading small { display: block; }
.dimension-card-heading > span { font-size: 12px; font-weight: 650; }
.dimension-card-heading small { color: var(--lab-muted); font-size: 10px; }
.dimension-card-content > strong { display: block; font-size: 23px; margin: 8px 0; }
.dimension-contribution { color: var(--lab-muted); display: block; font-size: 10px; margin: 8px 0 0; }
.dimension-action { color: #a9b9ff; display: block; font-size: 10px; font-weight: 650; margin-top: 9px; }
.dimension-detail { background: #101f31; border: 1px solid #415a7a; border-radius: 7px; display: none; grid-column: 1 / -1; }
.dimension-scorecards:has(.dimension-selector.task_effectiveness:checked) .dimension-detail.task_effectiveness,
.dimension-scorecards:has(.dimension-selector.decision_quality:checked) .dimension-detail.decision_quality,
.dimension-scorecards:has(.dimension-selector.safety:checked) .dimension-detail.safety,
.dimension-scorecards:has(.dimension-selector.recovery:checked) .dimension-detail.recovery,
.dimension-scorecards:has(.dimension-selector.explainability:checked) .dimension-detail.explainability,
.dimension-scorecards:has(.dimension-selector.calibration:checked) .dimension-detail.calibration,
.dimension-scorecards:has(.dimension-selector.efficiency:checked) .dimension-detail.efficiency { display: block; }
.dimension-detail-heading { align-items: center; background: #15243a; border-bottom: 1px solid var(--lab-border); display: flex; justify-content: space-between; padding: 10px 16px; }
.dimension-detail-heading strong { color: #e1e9f5; font-size: 13px; }
.dimension-detail-heading label { color: #a9b9ff; cursor: pointer; font-size: 11px; font-weight: 650; }
.dimension-explanation {
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(240px, 1.25fr) minmax(260px, 1fr) minmax(300px, 1.4fr);
  padding: 15px 17px 17px;
}
.dimension-explanation p { color: #b5c3d5; font-size: 12px; line-height: 1.55; margin: 6px 0 0; }
.dimension-explanation code { color: #dce7f6; display: block; font-size: 11px; line-height: 1.55; margin-top: 6px; overflow-wrap: anywhere; }
.dimension-explanation dl { display: grid; gap: 7px; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; }
.dimension-explanation dl div { background: #0b1727; border: 1px solid var(--lab-border); border-radius: 6px; padding: 8px 9px; }
.dimension-explanation dt { color: var(--lab-muted); font-size: 9px; }
.dimension-explanation dd { color: #dce5f1; font-size: 11px; font-weight: 650; margin: 3px 0 0; }
.meter { background: #26364b; border-radius: 4px; height: 4px; overflow: hidden; }
.meter span { background: var(--lab-cyan); height: 100%; }
.gate-grid { display: grid; gap: 10px; grid-template-columns: repeat(3, 1fr); margin-top: 10px; }
.gate-card { background: var(--lab-panel-raised); border: 1px solid var(--lab-border); border-radius: 7px; padding: 11px; }
.gate-card > div { display: flex; justify-content: space-between; }
.gate-card strong { font-size: 12px; }
.gate-card p { color: var(--lab-muted); font-size: 11px; margin: 8px 0 0; }
.gate-card.pass { border-color: #376b48; }
.gate-card.pass strong { color: var(--lab-green); }
.gate-card.fail { border-color: #853f46; }
.gate-card.fail strong { color: var(--lab-red); }
.gate-result { color: var(--lab-muted); font-size: 12px; }
.ledger-layout { display: grid; gap: 12px; grid-template-columns: 2.2fr 1fr; margin-top: 10px; }
.ledger { border-collapse: collapse; font-size: 11px; width: 100%; }
.ledger th, .ledger td { border-bottom: 1px solid var(--lab-border); padding: 8px; text-align: left; }
.ledger th { color: var(--lab-muted); }
.ledger td:nth-child(3), .ledger tfoot th { color: var(--lab-green); }
.ledger-delta { align-items: center; display: grid; gap: 7px; grid-template-columns: minmax(35px, 1fr) auto; }
.ledger-delta > span { background: var(--lab-cyan); border-radius: 3px; display: block; height: 7px; }
.ledger-delta > span.task_effectiveness { background: #5a91d1; }
.ledger-delta > span.decision_quality { background: #8f72d1; }
.ledger-delta > span.safety { background: #65b77c; }
.ledger-delta > span.recovery { background: #daa151; }
.ledger-delta > span.explainability { background: #5ba4be; }
.ledger-delta > span.calibration { background: #839ac0; }
.ledger-delta > span.efficiency { background: #5fb7c2; }
.evidence-map { background: var(--lab-panel-raised); border: 1px solid var(--lab-border); border-radius: 7px; padding: 10px; }
.evidence-map h4 { font-size: 12px; margin: 0 0 8px; }
.evidence-map ul { list-style: none; margin: 0; padding: 0; }
.evidence-map li { border-top: 1px solid var(--lab-border); display: grid; gap: 6px; grid-template-columns: 70px 1fr; padding: 7px 0; }
.evidence-map li span { color: var(--lab-muted); font-size: 10px; }
.task-context h3 { color: var(--lab-text); margin: 0 0 6px; }
.task-context p { color: #c6d1df; line-height: 1.5; }
.task-meta { display: flex; flex-wrap: wrap; gap: 7px; }
.task-meta span { background: #111f31; border: 1px solid var(--lab-border); border-radius: 6px; color: var(--lab-muted); font-size: 11px; padding: 5px 7px; }
.historical-note { border-left: 3px solid var(--lab-amber); color: #d5c39e !important; padding-left: 10px; }
.empty-panel { color: var(--lab-muted); padding: 30px; }
#run-evaluation { min-height: 44px; }
#trace-table table { font-size: 11px !important; }
#trace-table th { background: #0a1625 !important; color: #98a8bd !important; }
#trace-table td { background: #0c1828 !important; color: #d3ddea !important; }
#trace-table tr:hover td { background: #142642 !important; }
footer { display: none !important; }

/* Trace-first evaluation studio polish. */
html, body, gradio-app, .gradio-container {
  font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}
.gradio-container { padding: 24px 32px 42px !important; }
.lab-header { align-items: center; margin-bottom: 20px; }
.lab-header h1 { font-size: 30px; font-weight: 720; letter-spacing: -.035em; }
.lab-header p { font-size: 14px; margin-top: 5px; }
.mode-badge { background: #0b1d25; border-radius: 8px; font-size: 12px; padding: 7px 11px; }
.config-strip {
  background: #0b1727 !important;
  border-color: #2b3d54 !important;
  border-radius: 12px !important;
  margin-bottom: 12px;
  padding: 14px 16px 16px !important;
}
.config-strip .config-strip {
  background: transparent !important;
  border: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}
.config-strip .block { border-radius: 8px !important; }
.config-strip label { font-size: 13px !important; font-weight: 700 !important; }
.config-strip .info { color: #8fa0b5 !important; font-size: 11px !important; line-height: 1.35 !important; }
.config-strip input, .config-strip button, .config-strip textarea { font-size: 14px !important; }
#evaluation-toolbar { align-items: flex-end !important; gap: 0 !important; }
#evaluation-toolbar > .column {
  align-self: stretch !important;
  display: flex !important;
  justify-content: flex-end !important;
}
#evaluation-toolbar .block { margin-bottom: 0 !important; width: 100% !important; }
.config-strip .wrap:has(input[type="radio"]) {
  align-items: center !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  gap: 6px !important;
}
.config-strip label:has(input[type="radio"]) { min-width: 0 !important; }
#run-evaluation {
  align-self: end;
  border: 1px solid #667cff !important;
  border-radius: 8px !important;
  box-shadow: none !important;
  font-size: 14px !important;
  font-weight: 740 !important;
  flex: 0 0 48px !important;
  height: 48px !important;
  margin: 0 0 1px !important;
  max-height: 48px !important;
  min-height: 48px;
}
#run-evaluation:focus-visible { outline: 2px solid #8d9bff !important; outline-offset: 2px; }
.run-context-bar {
  align-items: start;
  background: #091524;
  border: 1px solid #263950;
  border-radius: 10px;
  display: grid;
  gap: 22px;
  grid-template-columns: minmax(210px, .9fr) minmax(440px, 2.1fr) minmax(330px, 1.2fr);
  margin: 0 0 10px;
  padding: 14px 18px;
}
.run-context-bar > div { min-width: 0; }
.run-context-bar strong { color: #edf3fb; display: block; font-size: 14px; margin: 3px 0; }
.run-context-bar small { color: #96a7bc; display: block; font-size: 12px; line-height: 1.4; }
.run-context-bar > div:first-child small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-context-task small { color: #b5c3d5; line-height: 1.55; margin-top: 5px; overflow: visible; white-space: normal; }
.run-context-task { border-left: 1px solid #263950; padding-left: 20px; }
.run-context-bar dl { display: grid; grid-template-columns: .8fr 1.25fr .75fr; margin: 0; }
.run-context-bar dl div { border-left: 1px solid #263950; min-width: 0; padding-left: 13px; }
.run-context-bar dt { color: #8193aa; font-size: 10px; text-transform: uppercase; }
.run-context-bar dd { color: #dbe5f2; font-size: 12px; font-weight: 650; margin: 3px 0 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.custom-agent-panel { background: #0b1727 !important; border-color: #263950 !important; margin-bottom: 10px !important; }
.custom-agent-panel > .label-wrap { font-size: 13px !important; }
.run-phase { border-radius: 10px; margin: 10px 0; min-height: 58px; padding: 10px 16px; }
.run-phase strong { font-size: 14px; }
.run-phase small, .run-phase p { font-size: 12px; }
.trace-empty { border-radius: 10px; min-height: 340px; }
.trace-empty.score-empty { min-height: 230px; }
.trace-empty h3 { font-size: 24px; }
.trace-empty p { font-size: 14px; }
.live-trace { border-color: #2a3d55; border-radius: 10px; }
.trace-run-header { min-height: 82px; padding: 13px 20px; }
.trace-run-header strong { font-size: 16px; }
.trace-run-header small { font-size: 12px; margin-top: 2px; }
.trace-run-header dt { font-size: 11px; }
.trace-run-header dd { font-size: 13px; margin-top: 4px; }
.trace-layout { min-height: 560px; }
.trace-event-list { max-height: 640px; }
.trace-table-header { font-size: 11px; letter-spacing: .045em; padding: 0 14px; }
.trace-table-header span { padding: 13px 11px; }
.trace-event-row { min-height: 66px; padding: 0 14px; }
.trace-event-row > span { padding: 9px 11px; }
.timeline-cell { font-size: 12px; }
.actor-cell { font-size: 14px; }
.event-cell strong { font-size: 14px; }
.event-cell small { font-size: 12px; line-height: 1.4; margin-top: 3px; }
.evidence-cell { font-size: 12px; }
.outcome-cell b { font-size: 10px; padding: 4px 8px; }
.trace-inspector-card { min-height: 560px; }
.trace-inspector-card > header { min-height: 82px; padding: 14px 22px; }
.trace-inspector-card h3 { font-size: 20px; }
.inspector-tabs { gap: 30px; padding: 0 22px; }
.inspector-tabs label { font-size: 13px; padding: 16px 2px 12px; }
.inspector-tab-panels { padding: 21px 22px 24px; }
.inspector-tab-panel h4 { font-size: 13px; }
.trace-metadata dt, .payload-summary dt { font-size: 10px; }
.trace-metadata dd, .payload-summary dd { font-size: 12px; }
.event-summary { font-size: 14px; }
.code-block { font-size: 12px; line-height: 1.55; max-height: 250px; padding: 13px; }
.live-trace.status-error .trace-layout,
.live-trace.status-error .trace-inspector-card { min-height: 340px; }
.live-trace.status-error .trace-event-list { max-height: 340px; }
.live-trace.status-error .trace-status-dot { background: var(--lab-red); box-shadow: 0 0 0 4px #44202a; }
.live-trace.status-incomplete .trace-status-dot { background: var(--lab-amber); box-shadow: 0 0 0 4px #47351f; }
.live-trace.status-incomplete .trace-layout,
.live-trace.status-incomplete .trace-inspector-card { min-height: 420px; }
.error-code.warning { background: #2a2113; border-color: #765b2f; color: #f3c576; }
.score-shell { border-color: #2a3d55 !important; border-radius: 10px !important; }
.score-workbench { padding: 22px; }
.score-title-row h2, .score-unavailable h2 { font-size: 26px; }
.score-workbench > p { color: #b8c6d8; font-size: 14px; line-height: 1.55; }
.score-section { padding: 12px 14px; }
.score-section > summary { font-size: 15px; }
.error-result-heading { align-items: center; display: flex; gap: 20px; justify-content: space-between; }
.error-code { background: #281820; border: 1px solid #763f4b; border-radius: 7px; color: #f0a3ae; font-size: 11px; font-weight: 750; padding: 6px 9px; }
.error-next-step { background: #101f31; border: 1px solid #324a67; border-radius: 8px; display: grid; gap: 4px; margin: 16px 0 10px; padding: 12px 14px; }
.error-next-step strong { color: #dae6f4; font-size: 12px; }
.error-next-step span { color: #aebed1; font-size: 13px; }
@media (max-width: 1050px) {
  .run-status { grid-template-columns: 1fr; }
  .run-status dl { grid-template-columns: repeat(2, 1fr); }
  .run-phase { grid-template-columns: 1fr; }
  .trace-run-header { grid-template-columns: 1fr; }
  .trace-run-header dl { grid-template-columns: repeat(3, 1fr); }
  .trace-layout { grid-template-columns: 1fr; }
  .trace-event-list { border-bottom: 1px solid var(--lab-border); border-right: 0; max-height: 520px; }
  .dimension-grid { grid-template-columns: repeat(2, 1fr); }
  .dimension-explanation { grid-template-columns: 1fr; }
  .impact-facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ledger-layout { grid-template-columns: 1fr; }
  .run-context-bar { grid-template-columns: 1fr; }
  .run-context-task { border-left: 0; border-top: 1px solid #263950; padding: 12px 0 0; }
}
@media (max-width: 700px) {
  .gradio-container { padding: 12px !important; }
  .lab-header, .score-title-row { flex-direction: column; }
  .run-status dl, .gate-grid, .inspector-meta { grid-template-columns: 1fr; }
  .run-phase dl, .trace-run-header dl, .trace-metadata { grid-template-columns: 1fr 1fr; }
  .trace-table-header, .trace-event-row { grid-template-columns: 24% 24% 52%; }
  .trace-table-header span:nth-child(4), .trace-table-header span:nth-child(5),
  .evidence-cell, .outcome-cell { display: none; }
  .dimension-grid { grid-template-columns: 1fr; }
  .impact-facts { grid-template-columns: 1fr; }
}
"""


def _world_path() -> Path:
    global _WORLD_PATH, _WORLD_TEMPORARY_DIRECTORY
    if _WORLD_PATH is None:
        _WORLD_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory(prefix="dab-demo-")
        _WORLD_PATH = generate_world(Path(_WORLD_TEMPORARY_DIRECTORY.name), GenerationConfig())
    return _WORLD_PATH


def _catalog_item(instance_id: str) -> dict[str, Any]:
    """Return one allow-listed public catalog item."""

    try:
        return _CATALOG[instance_id]
    except KeyError as error:
        raise ValueError(f"unknown task instance: {instance_id!r}") from error


def _safe_variant(variant: str) -> str:
    """Convert an untrusted UI value to one of the two supported constants."""

    if variant == "clean":
        return "clean"
    if variant == "perturbed":
        return "perturbed"
    raise ValueError(f"unknown evaluation condition: {variant!r}")


def _safe_agent_key(agent_key: str) -> str:
    """Convert an untrusted UI value to an allow-listed replay profile key."""

    for _label, known_key in agent_choices():
        if agent_key == known_key:
            return known_key
    raise ValueError(f"unknown agent architecture: {agent_key!r}")


def _run_world_path(instance_id: str, variant: str) -> Path:
    """Return a cached isolated world matching the selected instance and paired variant."""

    global _RUN_WORLD_TEMPORARY_DIRECTORY
    item = _catalog_item(instance_id)
    selected_variant = _safe_variant(variant)
    catalog_instance_id = str(item["instance_id"])
    key = (catalog_instance_id, selected_variant)
    if key in _RUN_WORLD_PATHS:
        return _RUN_WORLD_PATHS[key]
    if _RUN_WORLD_TEMPORARY_DIRECTORY is None:
        _RUN_WORLD_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory(prefix="dab-lab-runs-")
    destination = Path(tempfile.mkdtemp(prefix="world-", dir=_RUN_WORLD_TEMPORARY_DIRECTORY.name))
    database_path = generate_world(
        destination,
        GenerationConfig(seed=int(item["scenario_seed"])),
    )
    if selected_variant == "perturbed":
        apply_perturbation(database_path, str(item["perturbation"]))
    _RUN_WORLD_PATHS[key] = database_path
    return database_path


def task_context_html(instance_id: str, variant: str) -> str:
    """Render public task context without exposing hidden grading targets or oracle fields."""

    item = _catalog_item(instance_id)
    selected_variant = _safe_variant(variant)
    sample_id = item[f"{selected_variant}_sample_id"]
    perturbation = (
        "Clean paired sample; no controlled perturbation is applied."
        if selected_variant == "clean"
        else f"Controlled perturbation: {item['perturbation']}"
    )
    return f"""
    <section class="task-context">
      <span class="eyebrow">Selected task</span>
      <h3>{escape(str(item["family_id"]))} · {escape(str(item["category"]).replace("_", " "))}</h3>
      <p>{escape(str(item["prompt"]))}</p>
      <div class="task-meta">
        <span>Sample {escape(str(sample_id))}</span>
        <span>Difficulty {escape(str(item["difficulty"]))}</span>
        <span>Seed {item["scenario_seed"]}</span>
        <span>Optimal tool calls {item["optimal_tool_calls"]}</span>
        <span>Evidence dependency depth {item["enforced_dependency_depth"]}</span>
      </div>
      <p class="historical-note">{escape(perturbation)} The v0.2 catalog is a historical
      evidence-gated contract; it does not establish long-horizon capability.</p>
    </section>
    """


def _execute_lab_run(agent_key: str, instance_id: str, variant: str) -> dict[str, Any]:
    selected_agent = _safe_agent_key(agent_key)
    item = _catalog_item(instance_id)
    selected_variant = _safe_variant(variant)
    run = run_replay(
        agent_key=selected_agent,
        instance=item,
        variant=selected_variant,
        database_path=_run_world_path(instance_id, selected_variant),
    )
    return run.as_payload()


def task_view(instance_id: str, variant: str) -> tuple[str, dict[str, Any], str]:
    """Return prompt, metadata, and perturbation explanation for one catalog entry."""

    item = _catalog_item(instance_id)
    selected_variant = _safe_variant(variant)
    sample_id = (
        item["clean_sample_id"] if selected_variant == "clean" else item["perturbed_sample_id"]
    )
    metadata = {
        "sample_id": sample_id,
        "family_id": item["family_id"],
        "category": item["category"],
        "difficulty": item["difficulty"],
        "declared_workflow_steps": item["declared_workflow_steps"],
        "optimal_tool_calls": item["optimal_tool_calls"],
        "enforced_dependency_depth": item["enforced_dependency_depth"],
        "horizon_claim": item["horizon_claim"],
        "scenario_seed": item["scenario_seed"],
        "benchmark_version": item["benchmark_version"],
    }
    perturbation = (
        "No perturbation. This is the clean paired sample."
        if selected_variant == "clean"
        else f"Controlled perturbation: `{item['perturbation']}`"
    )
    return str(item["prompt"]), metadata, perturbation


def workflow_view(instance_id: str, variant: str) -> tuple[str, dict[str, Any], str]:
    """Return the public v0.3 prompt, measured contract, and paired stress event."""

    item = _WORKFLOW_CATALOG[instance_id]
    metadata = {
        "sample_id": item[f"{variant}_sample_id"],
        "workflow_id": item["workflow_id"],
        "category": item["category"],
        "scenario_seed": item["scenario_seed"],
        "enforced_transitions": item["enforced_transitions"],
        "dependency_span_target": item["dependency_span_target"],
        "minimum_simulated_days": item["minimum_simulated_days"],
        "horizon_claim": item["horizon_claim"],
        "benchmark_version": item["benchmark_version"],
    }
    event = (
        "No disruption. Delayed checkpoints still apply."
        if variant == "clean"
        else f"Delayed recovery event: `{item['perturbation']}`"
    )
    return str(item["prompt"]), metadata, event


def _evidence_calls(family_id: str, evidence_pack: str) -> list[dict[str, Any]]:
    if evidence_pack == "none":
        return []
    contract = CASES_BY_ID[family_id]
    tools = list(contract.required_tools)
    target_count = contract.min_evidence if evidence_pack == "complete" else 1
    while len(tools) < target_count:
        tools.append(tools[-1] if tools else "retail_sql")
    return [
        {
            "index": index,
            "tool": tool_name,
            "status": "success",
            "arguments": {},
            "evidence_id": f"E{index:03d}",
            "result_sha256": "demo-evidence",
        }
        for index, tool_name in enumerate(tools, start=1)
    ]


def score_candidate(
    family_id: str,
    variant: str,
    evidence_pack: str,
    candidate_json: str,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Grade a user-authored decision with a transparent simulated evidence ledger."""

    case = CASES_BY_ID[family_id]
    calls = _evidence_calls(family_id, evidence_pack)
    perturbation = (
        next(item["perturbation"] for item in _CATALOG.values() if item["family_id"] == family_id)
        if variant == "perturbed"
        else None
    )
    grade = grade_submission(
        contract={**case.target(), "contract_version": "0.2.1"},
        submission=parse_submission(candidate_json, strict=True),
        tool_calls=calls,
        recoveries=[calls[0]["tool"]] if calls and variant == "perturbed" else [],
        variant=variant,
        perturbation_kind=perturbation_kind(perturbation),
        database_path=_world_path(),
    )
    details = {
        "failure_taxonomy": list(grade.failures),
        "explanation": grade.explanation,
        "available_evidence_ids": [call["evidence_id"] for call in calls],
        "evidence_tools": [call["tool"] for call in calls],
        "hard_safety_gate": grade.values["safety"] == 0,
        "evidence_eligible": "F-EVID" not in grade.failures,
    }
    return grade.values, details


def world_snapshot(query_name: str) -> list[dict[str, Any]]:
    """Run one allow-listed, read-only reference-world query."""

    with RetailEnvironment(_world_path(), row_limit=24) as environment:
        return environment.query_sql(QUERY_LIBRARY[query_name])


def default_candidate() -> str:
    """Return a valid example submission for the first task family."""

    return json.dumps(
        {
            "conclusion": "R03 shows a material decline in unit demand; investigate locally.",
            "confidence": 0.85,
            "evidence_ids": ["E001", "E002"],
            "selected_ids": ["R03"],
            "numeric_values": {},
            "escalate": False,
            "data_quality_issues": [],
        },
        indent=2,
    )


def build_demo() -> Any:
    """Build the live Inspect evaluation workbench; Gradio remains optional."""

    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError('install the demo extra with `pip install -e ".[demo]"`') from error

    default_instance = "DAB-ASS-001-i1"
    if default_instance not in _CATALOG:
        default_instance = sorted(_CATALOG)[0]
    task_choices = [
        (
            f"{item['family_id']} · {str(item['category']).replace('_', ' ')} · {instance_id}",
            instance_id,
        )
        for instance_id, item in sorted(_CATALOG.items())
    ]
    empty_score = """
    <section class="trace-empty score-empty"><div><span class="eyebrow">Transparent scoring</span>
    <h3>Score calculation will appear after the run</h3><p>No default score is shown. The weighted
    equation, dimension contributions, evidence gates, and final ledger will be rendered from the
    scorer output in the completed Inspect log.</p></div></section>
    """

    agent_options = [*agent_choices(), ("Custom Inspect solver", "custom")]

    def runtime_selection(agent_key: str) -> tuple[str, str]:
        if agent_key == "custom":
            return "Custom Inspect solver", "single_agent"
        return "Built-in baseline", _safe_agent_key(agent_key)

    def run_context_html(
        agent_key: str,
        solver_reference: str,
        system_name: str,
        instance_id: str,
        variant: str,
    ) -> str:
        item = _catalog_item(instance_id)
        selected_variant = _safe_variant(variant)
        if agent_key == "custom":
            agent_label = system_name or "Unnamed custom system"
            architecture = f"Custom solver · {solver_reference}"
        else:
            agent = REPLAY_AGENTS_BY_KEY[_safe_agent_key(agent_key)]
            agent_label = agent.label
            architecture = agent.architecture
        condition = (
            "Clean paired sample"
            if selected_variant == "clean"
            else f"Perturbed · {item['perturbation']}"
        )
        sample_id = item[f"{selected_variant}_sample_id"]
        return f"""
        <section class="run-context-bar">
          <div><span class="eyebrow">Agent</span><strong>{escape(agent_label)}</strong>
          <small>{escape(architecture)}</small></div>
          <div class="run-context-task"><span class="eyebrow">Evaluation target</span>
          <strong>{escape(str(item["family_id"]))} · {escape(str(item["category"]).replace("_", " "))}</strong>
          <small class="target-prompt">{escape(str(item["prompt"]))}</small></div>
          <dl><div><dt>Sample</dt><dd>{escape(str(sample_id))}</dd></div>
          <div><dt>Condition</dt><dd>{escape(condition)}</dd></div>
          <div><dt>Tool target</dt><dd>{item["optimal_tool_calls"]} calls</dd></div></dl>
        </section>
        """

    def execute_for_ui(
        agent_key: str,
        solver_reference: str,
        system_name: str,
        model_name: str,
        instance_id: str,
        variant: str,
    ) -> Any:
        source, baseline = runtime_selection(agent_key)
        context = task_context_html(instance_id, variant)
        yield (
            {},
            running_status_html(
                "Preparing isolated sample",
                "Validating the model, agent, task, and local solver boundary.",
            ),
            trace_workbench_html(None),
            {},
            empty_score,
            context,
            None,
            None,
        )
        yield (
            {},
            running_status_html(
                "Running model and tools",
                f"Inspect is executing {model_name}; events will populate from its finalized log.",
            ),
            trace_workbench_html(None),
            {},
            empty_score,
            context,
            None,
            None,
        )
        try:
            item = _catalog_item(instance_id)
            selected_variant = _safe_variant(variant)
            payload = run_live_evaluation(
                agent_source=source,
                baseline=baseline,
                solver_reference=solver_reference,
                system_name=system_name,
                model_name=model_name,
                instance=item,
                variant=selected_variant,
            )
        except Exception as error:
            failure_payload = {"grade": {"available": False}, "error": str(error)}
            yield (
                {},
                error_status_html(error),
                "",
                {},
                score_explainer_html(failure_payload),
                context,
                None,
                None,
            )
            return
        completed_trace = list(payload["trace"])
        stride = max(1, len(completed_trace) // 18)
        counts = list(range(1, len(completed_trace) + 1, stride))
        if counts[-1] != len(completed_trace):
            counts.append(len(completed_trace))
        for count in counts:
            preview = {**payload, "status": "running", "trace": completed_trace[:count]}
            yield (
                preview,
                running_status_html(
                    "Building the auditable trace",
                    f"Rendered {count} of {len(completed_trace)} recorded events.",
                ),
                trace_workbench_html(preview),
                {},
                empty_score,
                context,
                None,
                None,
            )
            time.sleep(0.035)
        report_path = write_run_report(payload)
        inspect_log_path = payload.get("log_path") or None
        yield (
            payload,
            "",
            trace_workbench_html(payload),
            payload["submission"],
            score_explainer_html(payload),
            context,
            report_path,
            inspect_log_path,
        )

    theme = gr.themes.Base(primary_hue="indigo", neutral_hue="slate")
    blocks_options: dict[str, Any] = {
        "title": "DecisionAgentBench Lab",
        "fill_width": True,
    }
    if int(str(gr.__version__).split(".", maxsplit=1)[0]) < 6:
        blocks_options.update({"theme": theme, "css": _DEMO_CSS})
    with gr.Blocks(**blocks_options) as demo:
        run_state = gr.State({})
        gr.HTML(
            """
            <header class="lab-header"><div><h1>DecisionAgentBench Lab</h1>
            <p>Evaluation Studio · run an agent, inspect every event, and audit every score.</p></div>
            <span class="mode-badge">Local runner · provider calls use your credentials</span></header>
            """
        )
        with gr.Group(elem_classes="config-strip"):
            with gr.Row(equal_height=True, elem_id="evaluation-toolbar"):
                with gr.Column(scale=3, min_width=210):
                    selected_agent = gr.Dropdown(
                        choices=agent_options,
                        value="planner_executor",
                        label="Agent",
                    )
                with gr.Column(scale=3, min_width=210):
                    selected_model = gr.Dropdown(
                        choices=[
                            ("OpenAI · openai/gpt-5.6-luna", "openai/gpt-5.6-luna"),
                            ("Local plumbing only · mockllm/model", "mockllm/model"),
                        ],
                        value="openai/gpt-5.6-luna",
                        allow_custom_value=True,
                        label="Model",
                    )
                with gr.Column(scale=4, min_width=280):
                    selected_task = gr.Dropdown(
                        choices=task_choices,
                        value=default_instance,
                        label="Task instance",
                    )
                with gr.Column(scale=3, min_width=180):
                    selected_variant = gr.Radio(
                        ["clean", "perturbed"],
                        value="clean",
                        label="Condition",
                    )
                with gr.Column(scale=2, min_width=140):
                    run_button = gr.Button(
                        "Run evaluation",
                        variant="primary",
                        elem_id="run-evaluation",
                    )
        selected_run_context = gr.HTML(
            run_context_html(
                "planner_executor",
                "examples/custom_solver.py@custom_agent",
                "decision-agent-bench-lab",
                default_instance,
                "clean",
            )
        )
        with gr.Accordion("Custom agent adapter", open=False, elem_classes="custom-agent-panel"):
            with gr.Row():
                with gr.Column(scale=5, min_width=330):
                    custom_solver = gr.Textbox(
                        value="examples/custom_solver.py@custom_agent",
                        label="Custom Inspect solver",
                        info="Trusted local path.py@solver under agents/ or examples/.",
                    )
                with gr.Column(scale=3, min_width=240):
                    system_name = gr.Textbox(
                        value="decision-agent-bench-lab",
                        label="System name",
                        info="Stable label recorded in the Inspect log and report.",
                    )
            gr.Markdown(
                "Select **Custom Inspect solver** in the Agent menu to use these fields. "
                "Only repository files under `agents/` or `examples/` are loadable. "
                "See [`docs/evaluating-your-agent.md`](file/docs/evaluating-your-agent.md)."
            )

        selected_task_context = gr.HTML(task_context_html(default_instance, "clean"), visible=False)

        status = gr.HTML(idle_status_html())
        trace_surface = gr.HTML(trace_workbench_html(None))

        with gr.Group(elem_classes="score-shell"):
            score_explainer = gr.HTML(empty_score)
        with gr.Accordion("Final structured decision and portable report", open=False):
            with gr.Row():
                final_decision = gr.JSON({}, label="Submitted JSON")
                with gr.Column(min_width=220):
                    gr.Markdown(
                        "The Lab report contains the public task metadata, real Inspect trace, "
                        "evidence lineage, final JSON, every score, gates, model usage, and log path."
                    )
                    report = gr.DownloadButton(
                        "Download run report",
                        value=None,
                        variant="secondary",
                    )
                    inspect_log = gr.DownloadButton(
                        "Download Inspect log",
                        value=None,
                        variant="secondary",
                    )

        for control in (
            selected_agent,
            custom_solver,
            system_name,
            selected_task,
            selected_variant,
        ):
            control.change(
                run_context_html,
                inputs=[
                    selected_agent,
                    custom_solver,
                    system_name,
                    selected_task,
                    selected_variant,
                ],
                outputs=selected_run_context,
                show_progress="hidden",
                api_name=False,
            )
        selected_task.change(
            task_context_html,
            inputs=[selected_task, selected_variant],
            outputs=selected_task_context,
            show_progress="hidden",
            api_name=False,
        )
        selected_variant.change(
            task_context_html,
            inputs=[selected_task, selected_variant],
            outputs=selected_task_context,
            show_progress="hidden",
            api_name=False,
        )
        run_button.click(
            execute_for_ui,
            inputs=[
                selected_agent,
                custom_solver,
                system_name,
                selected_model,
                selected_task,
                selected_variant,
            ],
            outputs=[
                run_state,
                status,
                trace_surface,
                final_decision,
                score_explainer,
                selected_task_context,
                report,
                inspect_log,
            ],
            show_progress="minimal",
            api_name=False,
        )
    return demo.queue(default_concurrency_limit=1)


def launch_demo(host: str = "127.0.0.1", port: int = 7860) -> None:
    """Launch the local-only interactive demo."""

    demo = build_demo()
    import gradio as gr

    launch_options: dict[str, Any] = {
        "server_name": host,
        "server_port": port,
        "share": False,
        "show_error": True,
    }
    if int(str(gr.__version__).split(".", maxsplit=1)[0]) >= 6:
        launch_options.update(
            {
                "css": _DEMO_CSS,
                "theme": gr.themes.Base(primary_hue="indigo", neutral_hue="slate"),
            }
        )
    demo.launch(
        **launch_options,
    )
