# Local Lab agents

Put trusted, project-specific Inspect solver adapters in this directory when you want to run them
from DecisionAgentBench Lab. Register the solver with Inspect's `@solver` decorator, then enter a
reference such as `agents/my_agent.py@my_agent` in the Lab.

Files in this directory are executable Python code. Review them before running the Lab and never
accept solver files from an untrusted user. The complete integration contract and an included
example are documented in [`docs/evaluating-your-agent.md`](../docs/evaluating-your-agent.md).
