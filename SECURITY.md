# Security policy

DecisionAgentBench intentionally contains adversarial documents and prompt-injection scenarios. These are benchmark fixtures, not instructions for operators.

Please report vulnerabilities that could execute host commands, expose credentials, escape the benchmark sandbox, or leak hidden evaluation state privately to the maintainers. Do not include secrets in issues, logs, fixtures, or evaluation artifacts.

Until a dedicated private reporting channel is published, open a GitHub security advisory in the repository. Synthetic prompt-injection strings that remain confined to the simulator are normal benchmark content and are not security vulnerabilities.
