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
metadata are packaged in the wheel rather than downloaded at runtime, satisfying the fourth without
an external mutable asset. The registration issue must point to the final public 40-character
commit SHA.

The standard submission path does not require this repository to author `eval.yaml`. The official
issue form collects one versioned arXiv URL, one pinned source blob URL, and optional additional
maintainers. Its bot derives the register metadata and opens a pull request. Each task requires a
separate issue; the planned primary entry is `decision_agent_bench_v0_2`.

## Machine-checkable preflight

Run the offline audit at any time:

```bash
decision-agent-bench audit-inspect-registration
```

It verifies the `[project]` table, `inspect-ai` dependency, selected `@task`, packaged assets,
40-character commit, clean worktree, GitHub URL, versioned arXiv URL, and maintainer syntax. Missing
publication inputs are `pending`; malformed inputs or local implementation problems are `fail`.
The report also lists checks that remain authoritative in the upstream automation, including public
repository access and runnable/security review.

After the paper and public repository exist, prepare copy-ready form values from the clean pinned
commit:

```bash
decision-agent-bench prepare-inspect-registration build/inspect-registration \
  --repository-url https://github.com/<owner>/decision-agent-bench \
  --arxiv-url https://arxiv.org/abs/<versioned-id> \
  --maintainer <additional-github-user>
```

This command refuses incomplete or malformed inputs and writes `submission.json` plus
`issue-form-values.md`. It never opens an issue or claims acceptance.

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

## Issue-form fields

1. **arXiv URL:** `https://arxiv.org/abs/<versioned-id>`
2. **Source URL:** a generated URL of the form
   `https://github.com/<owner>/decision-agent-bench/blob/<40-char-sha>/src/decision_agent_bench/evals/task.py#L<decorator-line>`
3. **Maintainers:** additional GitHub usernames only; the submitter is included automatically.

After submission, the Inspect Evals bot validates the public repository, pinned commit, task
decorator, runnable construction, description, and security properties, then opens the register PR.
Record the issue and generated PR in the release notes. Do not describe registration as an
"accepted contribution" until that PR is merged.
