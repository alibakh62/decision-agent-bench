# Synthetic company data card

## Dataset summary

DecisionAgentBench's first environment is a generated convenience-retail company. It exists solely to evaluate agent behavior under controlled business, reliability, and safety conditions. It is not a statistical replica of a named company or a representative sample of the retail sector.

The reference configuration contains three regions, twelve stores, twenty-four products, four vendors, 240 synthetic customer identifiers, 56 days of item-level transactions, store-product prices and lot-level inventory, promotions, refunds, payment events, competitor observations, feed status, recall fixtures, policies, an untrusted vendor attachment, approvals, and an action ledger.

The expanded v0.2 task set contains **25 concepts, 100 seeded instances, and 200 paired samples**.
The 200 samples form 100 clean/perturbed pairs under four published seeds per concept. Seed-level
validation preserves fixed causal, safety, and answer-key fixtures while varying non-critical
transaction noise; these are not 200 independent evaluation concepts. All 53 named perturbations
are deterministically scheduled across the 100 perturbed samples.

The v0.6 registration reuses those generated worlds and paired instance identities under a new
typed scoring contract. It does not create more independent task concepts or a new empirical data
source. Every task has world-derived or reviewed expected fields, semantic evidence rules, and an
explicit decision-quality applicability declaration.

v0.7 adds a separate closed-loop world, not additional task samples. Its default episode contains
four heterogeneous stores, eight products, four vendors, store-specific prices, inventory lots,
shelf allocations, and 28 daily transition opportunities. Actions alter later receipts, demand,
sales, lost sales, substitution, spoilage, returns, operational events, cash, and store-day metrics.
Episodes are configurable from 14 through 180 days and support normal plus four held-out or stress
regimes. This is simulator infrastructure for v0.8 tasks, not an increase in the independent task
concept count.

The additional v0.3 workflow preview contains **3 workflow concepts, 12 seeded instances, and 24
paired samples**. Each sample uses the generated retail world plus private workflow state. Twenty
transitions persist across at least 15 simulated days; stressed pairs introduce a delayed event
that requires rollback. These samples are not additional independent v0.2 concepts.

## Generation

`decision-agent-bench generate-world OUTPUT --seed SEED` creates a SQLite database and manifest. The Python pseudorandom generator is isolated to a local seeded instance. Dates, iteration order, identifiers, and generated timestamps are fixed by the configuration. A logical SHA-256 digest hashes canonical table contents instead of SQLite file bytes.

The demand process combines store format, product category, weekday, smooth seasonality, seeded noise, promotion discounts, and one deliberately seeded regional decline. It is a benchmark mechanism, not a fitted demand model.

`decision-agent-bench generate-closed-loop OUTPUT --seed SEED --days DAYS --regime REGIME` creates
the v0.7 `episode.sqlite` and manifest. Keyed SHA-256 draws are indexed by causal event identity, so
an action does not shift unrelated later random draws. The manifest separates public and private
tables and hashes canonical initial state. `verify-closed-loop-reference` independently regenerates
the published default manifest.

## Tables and agent visibility

| Table | Purpose | Agent-visible |
| --- | --- | --- |
| `regions`, `stores` | Operating structure | Yes |
| `vendors`, `products`, `prices` | Assortment and unit economics | Yes |
| `customers` | Synthetic segment-linked identifiers | Yes, when a task permits |
| `promotions`, `inventory`, `transactions` | Operating history and state | Yes |
| `refunds`, `payment_events` | Synthetic investigation fixtures | Yes |
| `inventory_lots`, `recall_notices` | Lot traceability and recall state | Yes |
| `competitor_prices`, `data_feed_status` | External observations and freshness | Yes |
| `documents` | Policies, procedures, and adversarial fixtures | Through retrieval with provenance |
| `approvals`, `action_ledger` | Authorization and action audit | Yes |
| `oracle_parameters` | Counterfactual price-response grading | No |
| `dab_workflow_*` | v0.3 state, events, mutations, and execution trace | No |

The v0.7 public tables use the `cl_` prefix and include stores, products, vendors, prices,
inventory and lots, shelves, orders, promotions, sales, substitutions, spoilage, returns, events,
cash, approvals, actions, and daily metrics. `cl_demand_parameters`, `cl_random_draws`, and
`cl_metadata` are evaluator-only. See the [v0.7 world contract](v0.7-closed-loop-world.md) for the
full transition and authorization surface.

The SQL tool is read-only, single-statement, and row-bounded. State changes use typed policy-gated
methods and are recorded even when denied. v0.3 workflow tools expose only typed transition state;
their private tables cannot be queried through retail SQL.

## Privacy and provenance

All entities and events are created by project code. Names are fictional. Customer IDs contain no names, contact information, precise locations, payment credentials, or inferred protected attributes. No proprietary retailer data, internal policy, or employer material is used.

## Known limitations

- Transaction rows represent item purchase events rather than realistic multi-line baskets.
- Demand and substitution behavior are simplified and initially cover one retail domain.
- The principal regional-diagnosis signal is a uniform `0.74` units multiplier across the final
  region's last 14 days. It lacks composed causes, store heterogeneity, countervailing effects, and
  red-herring series, so diagnostic discrimination has not been established.
- Many v0.2 seed variants preserve the same key entity answers. They test repeatability under
  nuisance variation more than breadth of distinct decisions.
- Customer segments are operational fixtures, not demographic profiles.
- Generator parameters can encode benchmark assumptions that advantage matching heuristics.
- Synthetic validity does not imply external business validity.

The v0.7 closed-loop world is structurally grounded and sensitivity-tested but not calibrated to a
named retailer or target population. v0.8 must demonstrate task discrimination and policy ordering
before model comparisons; v0.9 must establish branching and human-time evidence before any general
long-horizon claim.

## Validation and appropriate use

Validation checks required tables, schema version, foreign keys, accounting identities, non-empty core data, and document checksums. Tests compare identical and different seeds. Appropriate uses include agent evaluation, tool-use research, and reproducibility studies. The data should not be used to make claims about real consumers, fraud prevalence, workforce behavior, or retailer performance.
