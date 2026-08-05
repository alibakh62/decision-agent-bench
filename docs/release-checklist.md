# Public release checklist

## Identity and metadata

- [x] Replace `OWNER` placeholders in `CITATION.cff` and documentation.
- [ ] Replace the collective creator with the maintainer's publication name and ORCID if desired.
- [ ] Confirm repository description, topics, support contact, and security contact; upload the
      audited `docs/assets/social-preview.png` through repository settings.
- [ ] Enable Zenodo, archive the GitHub release, and add the minted DOI to citation metadata.

## Evidence gates

- [x] Publish and independently verify the v0.5 candidate power/MDE design, effective family count,
      multiplicity plan, confirmatory/exploratory labels, and study-cost ceiling.
- [ ] Replace the v0.5 planning assumptions with pilot variance where materially different and
      generate the empirical metric-dependence report from valid typed-score samples.
- [x] Implement the v0.6 typed scoring, semantic evidence, portable causal trace, structured
      safety, metric-applicability, and adversarial scorer-validity gates.
- [x] Complete the v0.7 closed-loop-world gate: deterministic action-sensitive state, bounded
      observability, structured approvals, causal intervention tests, public baselines, stress
      regimes, reproducible manifests, and calibration/sensitivity evidence.
- [ ] Complete every v0.8-v0.10 validity-first roadmap gate: task discrimination, branching
      workflows, portable observability, horizon validation, blinded
      human and model-judge validation, a governed regression workflow, red team, and leakage audit.
- [ ] Freeze the preregistered model/baseline grid, archive its preflight, and authorize the exact
      configured exposure under a whole-study cost ceiling.
- [ ] Run at least three current model families with three or more repetitions.
- [ ] Complete the blinded human agreement study and adjudication.
- [ ] Regenerate every report table and figure from immutable manifests.
- [ ] Obtain one independent clean-machine reproduction.
- [ ] Review claims against the evidence ledger; remove all placeholders and prospective language.
- [ ] Publish the adversarial grader fixtures, metric-applicability map, human disagreement strata,
      metric-dependence report, effective family count, and MDE beside the empirical results.

## Engineering and security

- [ ] `make check` passes on Python 3.11 and 3.12 in CI.
- [ ] Wheel and source distribution install outside the checkout.
- [ ] Container builds by digest and passes its default verification command.
- [ ] CycloneDX SBOM, dependency audit, container provenance, release manifest, and `SHA256SUMS`
      pass `verify-release` from the clean tagged commit.
- [ ] Secret scan, dependency audit, oracle-leakage audit, and license/provenance review pass.
  Local checks are available through `make audit`; GitHub security automation must also be green.
- [ ] Interactive demo exposes no arbitrary SQL, state-changing actions, oracle inputs, or sharing
      tunnel by default.

## Publication and community

- [ ] Tag the release without rewriting history and publish the verified archival bundle and its
      checksum as immutable GitHub release assets.
- [ ] Publish the technical report and three articles with versioned result links.
- [ ] Publish the research talk deck and recording/license information.
- [ ] Open the Inspect Evals Register issue only after the arXiv and public-commit gates pass.
- [ ] Label good-first issues, publish contributor governance, and invite external reproductions.

Every unchecked evidence gate is a disclosed release blocker, not a documentation task to wave
through.
