# Contributing to DecisionAgentBench

Thank you for helping make agent evaluation more rigorous.

## Before contributing

- Open an issue for changes that affect task semantics, grading, simulator behavior, or published results.
- Keep benchmark tasks independent of confidential or proprietary business information.
- Disclose generated or adapted data and verify that its license permits redistribution.
- Treat a change as result-affecting if it changes prompts, tools, task state, policies, graders, metrics, or simulator outputs.

## Development workflow

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m decision_agent_bench validate-specs
```

Pull requests should include:

- a focused problem statement;
- tests for non-trivial logic;
- task-version or changelog updates for result-affecting changes;
- a statement about data provenance;
- reproducible commands and, when relevant, a small evaluation transcript.

## Evaluation integrity

Do not tune a baseline on hidden test-state values. Keep oracle-only state outside agent-visible tools and documents. Report unsuccessful runs, exclusions, retries, and manual interventions. Model-based graders may supplement but may not silently replace deterministic outcomes.

## AI-assisted contributions

AI-assisted work is welcome, but the human contributor is responsible for reviewing, testing, and understanding submitted code and prose. Label material AI assistance in the pull request when required by a target upstream project.

## Code of conduct

Be constructive, evidence-oriented, and respectful. Harassment, discrimination, doxxing, and disclosure of confidential information are not tolerated. Maintainers may remove harmful content or participation.
