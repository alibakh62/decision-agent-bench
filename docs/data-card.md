# Synthetic company data card

## Dataset summary

DecisionAgentBench's first environment is a generated convenience-retail company. It exists solely to evaluate agent behavior under controlled business, reliability, and safety conditions. It is not a statistical replica of a named company or a representative sample of the retail sector.

The reference configuration contains three regions, twelve stores, twenty-four products, four vendors, 240 synthetic customer identifiers, 56 days of item-level transactions, store-product prices and lot-level inventory, promotions, refunds, payment events, competitor observations, feed status, recall fixtures, policies, an untrusted vendor attachment, approvals, and an action ledger.

The expanded v0.2 task set contains **25 concepts, 100 seeded instances, and 200 paired samples**.
The 200 samples form 100 clean/perturbed pairs under four published seeds per concept. Seed-level
validation preserves fixed causal, safety, and answer-key fixtures while varying non-critical
transaction noise; these are not 200 independent evaluation concepts. All 53 named perturbations
are deterministically scheduled across the 100 perturbed samples.

## Generation

`decision-agent-bench generate-world OUTPUT --seed SEED` creates a SQLite database and manifest. The Python pseudorandom generator is isolated to a local seeded instance. Dates, iteration order, identifiers, and generated timestamps are fixed by the configuration. A logical SHA-256 digest hashes canonical table contents instead of SQLite file bytes.

The demand process combines store format, product category, weekday, smooth seasonality, seeded noise, promotion discounts, and one deliberately seeded regional decline. It is a benchmark mechanism, not a fitted demand model.

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

The SQL tool is read-only, single-statement, and row-bounded. State changes use typed policy-gated methods and are recorded even when denied.

## Privacy and provenance

All entities and events are created by project code. Names are fictional. Customer IDs contain no names, contact information, precise locations, payment credentials, or inferred protected attributes. No proprietary retailer data, internal policy, or employer material is used.

## Known limitations

- Transaction rows represent item purchase events rather than realistic multi-line baskets.
- Demand and substitution behavior are simplified and initially cover one retail domain.
- Customer segments are operational fixtures, not demographic profiles.
- Generator parameters can encode benchmark assumptions that advantage matching heuristics.
- Synthetic validity does not imply external business validity.

## Validation and appropriate use

Validation checks required tables, schema version, foreign keys, accounting identities, non-empty core data, and document checksums. Tests compare identical and different seeds. Appropriate uses include agent evaluation, tool-use research, and reproducibility studies. The data should not be used to make claims about real consumers, fraud prevalence, workforce behavior, or retailer performance.
