# Archival release artifacts

DecisionAgentBench releases are exact evidence bundles rather than loose attachments. Each bundle
contains the Python wheel and source distribution, both task catalogs, reference-world provenance,
technical report, articles, presentation, social-preview image, citation and archive metadata,
dependency lock, OpenVEX record, CycloneDX SBOM, vulnerability scan, container identity, and
admitted sanitized results.

`release-manifest.json` records every asset's portable path, role, media type, byte size, and
SHA-256. It also binds the software version, Git commit and commit timestamp, benchmark counts,
reference-world digest, prerelease state, and presence of publishable results. `SHA256SUMS` covers
every asset plus the manifest. Extra, missing, or modified files fail `verify-release`.

Release assembly parses `requirements.lock` and rejects an SBOM that does not contain every locked
name/version entry. It also rejects a `pip-audit` report with missing, unexpected, duplicate, or
out-of-lock packages. Python-version alternatives in the universal lock are treated as allowed
variants, while every unconditional or Python-version-selected package must be audited. A valid JSON
shape or an empty scanner report is not evidence of dependency coverage.

## Local release-candidate rehearsal

Install the release-only tools outside the runtime dependency lock, then build their evidence:

```bash
python -m pip install build==1.3.0 cyclonedx-bom==7.3.0 pip-audit==2.10.0
python -m build
cyclonedx-py requirements requirements.lock \
  --pyproject pyproject.toml --mc-type application \
  --spec-version 1.6 --output-reproducible --output-format JSON \
  --output-file build/sbom.cdx.json --validate
pip-audit --require-hashes --disable-pip -r requirements.lock \
  --format json --output build/pip-audit.json
docker build --tag decision-agent-bench:release .
```

`pip-audit` exits with status 1 when it writes known findings. Review every finding against
`security/openvex.json`; never hide an unreviewed advisory merely to continue packaging.

After committing the exact source being packaged, assemble the current development release:

```bash
decision-agent-bench prepare-release \
  build/release/decision-agent-bench-0.2.0.dev0 \
  --sbom build/sbom.cdx.json \
  --dependency-report build/pip-audit.json \
  --container-image decision-agent-bench:release \
  --allow-prerelease
decision-agent-bench verify-release \
  build/release/decision-agent-bench-0.2.0.dev0
```

Prerelease mode permits a development version and absence of empirical results, but still requires
a clean Git tree and verifies every supplied artifact. It cannot be used by the tag workflow.

## Final release gate

A final bundle additionally requires:

- a non-development project version and matching `v<version>` tag at `HEAD`;
- a clean Git tree;
- validated CycloneDX, `pip-audit`, and passing container evidence; and
- at least one standalone-verifiable analysis bundle containing manifest-complete, non-mock
  publishable results.

The tag-triggered release workflow repeats tests, package and container builds, the strict release
audit, SBOM generation, assembly, and verification. It creates a timestamp-normalized archive and
publishes the archive, checksum, wheel, source distribution, SBOM, and audit report through the
GitHub CLI. It intentionally does not publish to PyPI or create a tag.
