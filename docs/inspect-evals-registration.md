# Inspect Evals registration package

DecisionAgentBench is structured for the current Inspect Evals Register, but it has **not** been
submitted or accepted. As of 8 May 2026, new evaluation implementations remain in their upstream
repositories and are registered through an issue-driven workflow rather than merged into
`inspect_evals/src`.

The official requirements are documented in the [Inspect Evals Register submission
guide](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/register/README.md):

1. an installable `pyproject.toml` with a `[project]` table;
2. `inspect_ai` declared as a dependency;
3. discoverable `@task`-decorated task functions; and
4. external assets pinned in version-controlled storage.

This repository satisfies the first three requirements. Benchmark contracts and reference-world
metadata are packaged with tagged source releases; the registration issue must point to the final
public 40-character commit SHA.

## Submission gate

Do not submit until all boxes are checked:

- [ ] Public GitHub repository and immutable release tag exist.
- [ ] Versioned arXiv abstract URL exists; the register form requires it.
- [ ] Empirical report includes non-mock results and limitations.
- [ ] Source blob URL points to `decision_agent_bench_v0_1` or `decision_agent_bench_v0_2` at a
      40-character commit SHA, with a line anchor if needed.
- [ ] A clean clone installs and runs the exact task command in the report.
- [ ] External assets resolve from the pinned release.
- [ ] Repository URL, maintainer usernames, and security contact are final.

## Proposed issue content

```text
Evaluation: DecisionAgentBench
Paper: https://arxiv.org/abs/<versioned-id>
Source: https://github.com/<owner>/decision-agent-bench/blob/<40-char-sha>/src/decision_agent_bench/evals/task.py#L<line>
Maintainers: @<owner>
```

After submission, the Inspect Evals bot validates the public repository, pinned commit, task
decorator, runnable construction, description, and security properties, then opens the register PR.
Record the issue and generated PR in the release notes. Do not describe registration as an
"accepted contribution" until that PR is merged.
