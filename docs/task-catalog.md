# v0.1 task catalog

The catalog defines 25 task **families**. Each family will generate multiple seeded instances; task IDs and versions remain stable across instances. Horizons are expected meaningful tool or action steps, not forced chain-of-thought length.

| ID | Task | Category | Difficulty | Horizon | Core evaluation |
| --- | --- | --- | --- | ---: | --- |
| DAB-SAL-001 | Diagnose regional sales decline | Sales diagnosis | Medium | 8 | Root cause, evidence, calibration |
| DAB-SAL-002 | Explain margin collapse despite sales growth | Sales diagnosis | Hard | 10 | Profit decomposition, confounding |
| DAB-SAL-003 | Estimate incremental promotion lift | Sales diagnosis | Hard | 11 | Causal caution, uncertainty |
| DAB-SAL-004 | Find a daypart-specific traffic slump | Sales diagnosis | Medium | 7 | Segmentation, data completeness |
| DAB-SAL-005 | Detect cross-category cannibalization | Sales diagnosis | Expert | 13 | Counterfactual decision quality |
| DAB-ASS-001 | Select a vendor-constrained replacement | Assortment | Hard | 12 | Regret, feasibility, approval |
| DAB-ASS-002 | Allocate scarce inventory across stores | Assortment | Hard | 14 | Service level, fairness, regret |
| DAB-ASS-003 | Build a cold-start store assortment | Assortment | Expert | 15 | Analog selection, constraints |
| DAB-ASS-004 | Replace a recalled product safely | Assortment | Hard | 13 | Recall containment, substitution |
| DAB-PRO-001 | Design a margin-safe promotion | Promotion | Hard | 12 | Incremental profit, guardrails |
| DAB-PRO-002 | Mark down expiring inventory | Promotion | Medium | 9 | Waste versus margin trade-off |
| DAB-PRO-003 | Respond to competitor pricing | Promotion | Hard | 11 | Authorization, local elasticity |
| DAB-PRO-004 | Reconcile vendor-funded promotion terms | Promotion | Expert | 14 | Contradictory documents, evidence |
| DAB-FRD-001 | Investigate a refund-abuse cluster | Fraud and anomaly | Hard | 12 | Precision, escalation, privacy |
| DAB-FRD-002 | Diagnose a payment anomaly | Fraud and anomaly | Expert | 15 | Competing causes, evidence |
| DAB-FRD-003 | Avoid a seasonal false positive | Fraud and anomaly | Hard | 10 | Calibration, non-accusatory action |
| DAB-REC-001 | Recover from a missing sales partition | Data recovery | Medium | 8 | Detection, fallback, correction |
| DAB-REC-002 | Act with a delayed inventory feed | Data recovery | Hard | 11 | Staleness, safe degradation |
| DAB-REC-003 | Resolve contradictory performance reports | Data recovery | Hard | 12 | Source hierarchy, escalation |
| DAB-SAF-001 | Resist instructions in a vendor document | Safety | Hard | 9 | Prompt injection, least privilege |
| DAB-SAF-002 | Handle an unauthorized price request | Safety | Medium | 7 | Authorization boundary |
| DAB-SAF-003 | Detect poisoned retained context | Safety | Expert | 13 | Memory provenance, recovery |
| DAB-WRK-001 | Execute a regional turnaround workflow | Long-horizon workflow | Expert | 20 | End-to-end limits and recovery |
| DAB-WRK-002 | Launch a new vendor and product set | Long-horizon workflow | Expert | 22 | Dependencies, approvals, rollback |
| DAB-WRK-003 | Contain and recover from a product recall | Long-horizon workflow | Expert | 24 | Safety, completeness, communication |

The machine-readable source of truth is [`data/task_specs/v0.1.json`](../data/task_specs/v0.1.json). Each contract includes:

- the decision objective and expected interaction horizon;
- capabilities the task actually exercises;
- clean and perturbed variants;
- deterministic success criteria;
- hard business or authorization constraints;
- the evidence an explanation must cite.

## Coverage rationale

The mix deliberately avoids 25 variations of SQL question answering. Diagnostic tasks test evidence and uncertainty; assortment and promotion tasks create measurable economic regret; fraud tasks make precision and safe escalation consequential; recovery tasks distinguish graceful degradation from blind persistence; safety tasks test instruction hierarchy and authorization; workflows combine these capabilities over 20 or more steps.

Task implementation will be rejected if the nominal answer can be obtained without exercising the stated capability, if a perturbation makes the task unknowably impossible without allowing abstention, or if a grader rewards an outcome forbidden by policy.
