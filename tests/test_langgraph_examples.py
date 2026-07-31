from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from inspect_ai import eval
from pytest import MonkeyPatch

from decision_agent_bench.evals.task import (
    decision_agent_bench,
    decision_agent_bench_v0_2,
)
from decision_agent_bench.experiments.analysis import records_from_eval_log
from decision_agent_bench.lab_runtime import stage_uploaded_solver
from examples.langgraph_replenishment_service import (
    app,
    langgraph_remote_replenishment,
    run_replenishment_agent,
    validated_service_url,
)
from examples.langgraph_store_assistant import (
    langgraph_store_assistant,
    run_store_assistant,
)

ROOT = Path(__file__).resolve().parents[1]


def _read_example_data(name: str) -> dict:
    return json.loads((ROOT / "examples" / "data" / name).read_text())


def _isolate_inspect(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "inspect_ai._util.appdirs.user_data_path", lambda _package: tmp_path / "inspect-data"
    )
    monkeypatch.setattr(
        "inspect_ai._util.appdirs.user_cache_path", lambda _package: tmp_path / "inspect-cache"
    )


def test_store_assistant_runs_standalone() -> None:
    result = asyncio.run(run_store_assistant(_read_example_data("store_shift_snapshot.json")))

    assert result["priority"] == "critical"
    assert result["affected_lots"] == ["LOT-P003-RECALL"]
    assert result["recommended_substitute"] == "P021"
    assert result["policy_id"] == "POL-RECALL-004"


def test_replenishment_service_agent_runs_standalone() -> None:
    result = asyncio.run(run_replenishment_agent(_read_example_data("replenishment_snapshot.json")))

    assert result["store_id"] == "S001"
    assert result["orders"][0]["product_id"] == "P021"
    assert result["orders"][0]["arrival_stockout_units"] > 0
    assert sum(item["approved_cases"] for item in result["orders"]) <= 10


def test_remote_service_exposes_health_and_standalone_brief() -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            health = await client.get("/health")
            assert health.json()["status"] == "ok"
            response = await client.post(
                "/v1/store-brief",
                json={"snapshot": _read_example_data("replenishment_snapshot.json")},
            )
            response.raise_for_status()
            assert response.json()["orders"][0]["product_id"] == "P021"

    asyncio.run(exercise())


def test_both_example_files_are_lab_uploadable() -> None:
    store = stage_uploaded_solver(ROOT / "examples" / "langgraph_store_assistant.py")
    remote = stage_uploaded_solver(ROOT / "examples" / "langgraph_replenishment_service.py")

    assert store.entrypoints == ("langgraph_store_assistant",)
    assert remote.entrypoints == ("langgraph_remote_replenishment",)


def test_remote_service_url_is_loopback_or_explicitly_allowlisted(
    monkeypatch: MonkeyPatch,
) -> None:
    assert validated_service_url("http://127.0.0.1:8099/") == "http://127.0.0.1:8099"
    with pytest.raises(ValueError, match="not allow-listed"):
        validated_service_url("https://agents.example.com")
    monkeypatch.setenv("DAB_REMOTE_AGENT_ALLOWLIST", "agents.example.com")
    assert validated_service_url("https://agents.example.com") == "https://agents.example.com"
    with pytest.raises(ValueError, match="must use https"):
        validated_service_url("http://agents.example.com")


def test_store_assistant_scores_through_real_benchmark_tools(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _isolate_inspect(tmp_path, monkeypatch)
    logs = eval(
        decision_agent_bench(
            category="assortment",
            variant="clean",
            system_name="langgraph-store-assistant-v1",
        ),
        model="mockllm/model",
        solver=langgraph_store_assistant(),
        sample_id="DAB-ASS-004-clean",
        log_dir=str(tmp_path / "store-assistant"),
        display="none",
    )

    assert logs[0].status == "success"
    record = records_from_eval_log(logs[0])[0]
    assert record.task_id == "DAB-ASS-004"
    assert record.scores["task_effectiveness"] == 1
    assert record.scores["safety"] == 1
    assert record.tool_calls == 3


def test_remote_agent_brokers_tools_and_scores_with_oracle(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _isolate_inspect(tmp_path, monkeypatch)
    logs = eval(
        decision_agent_bench_v0_2(
            category="assortment",
            variant="clean",
            instances_per_family=4,
            system_name="langgraph-replenishment-service-v1",
        ),
        model="mockllm/model",
        solver=langgraph_remote_replenishment(in_process=True),
        sample_id="DAB-ASS-001-i1-clean",
        log_dir=str(tmp_path / "remote-agent"),
        display="none",
    )

    assert logs[0].status == "success"
    record = records_from_eval_log(logs[0])[0]
    assert record.task_id == "DAB-ASS-001"
    assert record.scores["decision_quality"] == 1
    assert record.normalized_regret == 0
    assert record.tool_calls == 3
