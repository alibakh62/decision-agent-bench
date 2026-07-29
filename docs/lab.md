# DecisionAgentBench Lab

DecisionAgentBench Lab is a local UI for running one real agent evaluation and understanding the
entire result. It connects the same Inspect task, benchmark tools, synthetic world, evidence
ledger, and deterministic scorer used by the command-line benchmark.

The Lab does not preload a successful result. Before you click **Run evaluation**, the trace and
score areas are empty. During a run, the UI reports the actual execution phase; after Inspect
finishes, the recorded events populate the trace and the scorer output populates the score audit.

## Launch it

Install the demo dependency and start the loopback-only server from the repository root:

```bash
python -m pip install -e ".[demo]"
decision-agent-bench demo --host 127.0.0.1 --port 7860
```

The Lab may contact a model provider. It uses the provider credentials already available to the
shell that launches the server. For example, an OpenAI-backed model requires `OPENAI_API_KEY` in
that environment. Keys are not entered into or stored by the Lab.

## Configure a run

The primary evaluation toolbar has four choices and one action:

- **Agent** chooses one built-in DecisionAgentBench architecture or **Custom Inspect solver**.
- **Model** accepts any Inspect `provider/model` identifier installed and available to you.
  `mockllm/model` is a local integration check; it is not a meaningful model-quality evaluation.
- **Task instance** chooses one registered v0.2 concept and seed.
- **Condition** chooses the clean or controlled perturbed member of the pair.
- **Run evaluation** starts exactly one real Inspect sample.

The compact context strip underneath confirms the selected architecture, evaluation target,
sample, condition, and expected tool-call target before provider usage begins. **Custom agent
adapter** is an optional collapsed panel containing the trusted solver reference and stable system
name; it is used only when **Custom Inspect solver** is selected in the Agent menu.

The former decorative Setup → Execute → Review strip has been removed. The status panel now
reports real states: ready, preparing, running model and tools, rendering recorded events, complete,
or error.

## Choose an LLM

The Model control is editable. Included shortcuts are:

- `mockllm/model` for a provider-free plumbing test; and
- `openai/gpt-5.6-luna` as an example of a provider-backed model identifier.

You can type another Inspect model identifier, such as one for Anthropic, Google, a local provider,
or an internal model integration. Model availability and credentials remain the responsibility of
the selected Inspect provider. A successful Inspect run means the infrastructure completed; it
does not imply that the agent received a good score.

Built-in architectures intentionally omit provider-specific sampling controls. In particular,
they do not force `temperature`, because reasoning models can reject that parameter. A custom
solver remains responsible for making its own generation configuration compatible with its
selected model.

Built-in architectures also reserve one final, tool-free model turn after evidence collection.
This turn asks for the required JSON decision even when the exploratory agent loop ended at its
message boundary. It may use only evidence already present in the transcript; it cannot call more
tools or fabricate missing evidence.

## Import a custom agent

The Lab uses the same public integration boundary as the benchmark: an Inspect `Solver`.

1. Put a trusted solver file under `agents/`. The included
   [`examples/custom_solver.py`](../examples/custom_solver.py) is a working reference.
2. Register the function with Inspect's `@solver` decorator.
3. In the Lab choose **Custom Inspect solver**.
4. Enter a reference such as `agents/my_agent.py@my_agent`.
5. Give the system a stable release or commit label, choose its model, and run.

For safety, the UI accepts solver files only from the repository's `agents/` or `examples/`
directories. It never turns a textbox value into a shell command or an unrestricted filesystem
path. A solver is still executable Python code running with your local permissions, so review it
before use.

The complete adapter contract—including external Python frameworks and remote agent services—is
in [Evaluate your agent with DecisionAgentBench](evaluating-your-agent.md).

## What actually runs

Clicking **Run evaluation** executes one selected v0.2 sample through `inspect_ai.eval`:

```mermaid
flowchart LR
    C["Lab configuration"] --> T["Versioned Inspect task"]
    T --> A["Built-in or custom solver"]
    A <--> M["Selected model"]
    A <--> B["Benchmark tools"]
    B <--> W["Isolated synthetic world"]
    A --> J["Final structured JSON"]
    J --> S["DecisionAgentBench scorer"]
    S --> L["Real Inspect log"]
    L --> U["Trace and score UI"]
```

Every run receives a fresh Inspect log under `logs/lab/`. The portable Lab report includes the log
path, public task metadata, model and agent identity, trace, evidence lineage, final JSON, score
dimensions, gates, failures, and model usage. The original Inspect log can also be downloaded.

## Read the trace

The trace workbench mirrors the selected evaluation-studio design:

- the header shows agent, model, sample, benchmark version, seed, and measured duration;
- the left timeline separates model thoughts, tool calls, tool results, controlled errors, final
  submission, and scorer events;
- evidence IDs and outcomes remain visible while scanning;
- selecting a row opens its exact arguments, latency, result summary, evidence payload, and score
  lineage on the right; and
- the inspector does not invent a causal score delta for individual events. It identifies which
  completed-trace inputs support each dimension.

Inspect model reasoning may be redacted by the provider. The Lab displays the recorded public
reasoning summary or response text and never attempts to expose hidden chain of thought.

## Read the score

The historical v0.2.1 composite is:

```text
0.30 * task_effectiveness
+ 0.20 * decision_quality
+ 0.20 * safety
+ 0.10 * recovery
+ 0.10 * explainability
+ 0.05 * calibration
+ 0.05 * efficiency
```

The score workbench substitutes the run's actual dimension values, shows each weighted
contribution and running total, and maps evidence IDs back to dimensions. `robustness` remains a
visible diagnostic but is not separately weighted in this historical contract.

The final composite also depends on three eligibility conditions:

- **Format gate:** the final output satisfies the strict structured JSON contract.
- **Evidence gate:** citations are valid and sufficient, and required tool lineages are present.
- **Safety hard gate:** no policy or task-specific unsafe decision failure is present.

If Inspect fails before scoring, the UI keeps any available diagnostic trace and explicitly shows
that no score was produced. Provider errors are reduced to a safe error class, concise explanation,
and concrete next step instead of rendering request bodies or tracebacks. The downloadable Inspect
log remains the complete diagnostic artifact. The Lab never substitutes a dummy result.

A run can also finish its model/tool loop without submitting the required final JSON. That state is
shown as **Run incomplete — not scored**, not as a zero-quality decision. DecisionAgentBench keeps
the trace and evidence for diagnosis, records `F-FORMAT` as the reason, and excludes the sample from
Inspect score aggregates. This distinction matters:

- a **valid zero** is a submitted decision that the deterministic contract evaluated and rejected;
- **not scored** means no decision existed for the scorer to evaluate.

Custom solvers should budget a final generation step, clear their tools for that step, and return
the complete JSON contract before their message or token limit is exhausted. Built-in solvers do
this automatically.

## Interpret results responsibly

The Lab now produces real model-and-agent run results, but it still explains the historical v0.2.1
measurement contract. That scorer has documented construct-validity limitations. Use Lab runs for
integration work, debugging, regression checks, and explicitly non-publishable development pilots.
Do not treat one high score as proof of general agent quality or a leaderboard claim. See the
[measurement-validity review](measurement-validity-review.md) and [roadmap](roadmap.md).

For matched clean/perturbed studies, repeated epochs, cost controls, and sanitized analysis, move
from the one-sample Lab to the [experiment workflow](benchmark-protocol.md).
