# Runnable custom-agent examples

These examples turn the abstract adapter patterns in
[`docs/evaluating-your-agent.md`](../docs/evaluating-your-agent.md) into complete convenience-retail
agents.

| Example | Runs by itself | DecisionAgentBench route | Best smoke-test task |
| --- | --- | --- | --- |
| [`langgraph_store_assistant.py`](langgraph_store_assistant.py) | Daily recall and operations brief from simulated store JSON | In-process Python framework adapter | `DAB-ASS-004` |
| [`langgraph_replenishment_service.py`](langgraph_replenishment_service.py) | Replenishment plan from simulated store JSON or HTTP | Remote service with an Inspect tool broker | `DAB-ASS-001-i1` |

Install everything required by both examples and the Lab:

```bash
python -m pip install -e ".[agents,demo]"
```

Run the agents without DecisionAgentBench:

```bash
python examples/langgraph_store_assistant.py
python examples/langgraph_replenishment_service.py demo
```

Complete setup, architecture, input, service, Lab upload, CLI evaluation, adaptation, and safety
instructions are in:

- [In-process LangGraph store assistant](../docs/examples/langgraph-store-assistant.md)
- [Remote LangGraph replenishment service](../docs/examples/langgraph-remote-replenishment.md)
