"""Versioned schema for the v0.7 closed-loop retail world."""

CLOSED_LOOP_SCHEMA_VERSION = "0.7.0"

CLOSED_LOOP_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE cl_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE cl_stores (
    store_id TEXT PRIMARY KEY,
    format TEXT NOT NULL CHECK (format IN ('urban', 'suburban', 'highway', 'campus')),
    demand_multiplier REAL NOT NULL CHECK (demand_multiplier > 0),
    shelf_capacity_units INTEGER NOT NULL CHECK (shelf_capacity_units > 0),
    storage_capacity_units INTEGER NOT NULL CHECK (storage_capacity_units > 0),
    opening_cash REAL NOT NULL,
    current_cash REAL NOT NULL
);

CREATE TABLE cl_vendors (
    vendor_id TEXT PRIMARY KEY,
    lead_time_days INTEGER NOT NULL CHECK (lead_time_days > 0),
    case_pack INTEGER NOT NULL CHECK (case_pack > 0),
    minimum_cases INTEGER NOT NULL CHECK (minimum_cases > 0),
    weekly_capacity_cases INTEGER NOT NULL CHECK (weekly_capacity_cases > 0),
    base_fill_rate REAL NOT NULL CHECK (base_fill_rate > 0 AND base_fill_rate <= 1)
);

CREATE TABLE cl_products (
    product_id TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL REFERENCES cl_vendors(vendor_id),
    category TEXT NOT NULL CHECK (category IN ('beverage', 'snack', 'fresh', 'household')),
    unit_cost REAL NOT NULL CHECK (unit_cost > 0),
    base_price REAL NOT NULL CHECK (base_price > unit_cost),
    shelf_life_days INTEGER NOT NULL CHECK (shelf_life_days > 0),
    space_units INTEGER NOT NULL CHECK (space_units > 0),
    active INTEGER NOT NULL CHECK (active IN (0, 1))
);

CREATE TABLE cl_prices (
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    unit_price REAL NOT NULL CHECK (unit_price > 0),
    effective_date TEXT NOT NULL,
    PRIMARY KEY (store_id, product_id)
);

CREATE TABLE cl_inventory (
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    on_hand_units INTEGER NOT NULL CHECK (on_hand_units >= 0),
    on_shelf_units INTEGER NOT NULL CHECK (on_shelf_units >= 0),
    reorder_point INTEGER NOT NULL CHECK (reorder_point >= 0),
    last_updated TEXT NOT NULL,
    PRIMARY KEY (store_id, product_id),
    CHECK (on_shelf_units <= on_hand_units)
);

CREATE TABLE cl_inventory_lots (
    lot_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    received_date TEXT NOT NULL,
    expires_date TEXT NOT NULL,
    original_units INTEGER NOT NULL CHECK (original_units > 0),
    remaining_units INTEGER NOT NULL CHECK (remaining_units >= 0),
    unit_cost REAL NOT NULL CHECK (unit_cost > 0)
);

CREATE TABLE cl_shelf_allocations (
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    allocated_units INTEGER NOT NULL CHECK (allocated_units >= 0),
    updated_date TEXT NOT NULL,
    PRIMARY KEY (store_id, product_id)
);

CREATE TABLE cl_purchase_orders (
    order_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    vendor_id TEXT NOT NULL REFERENCES cl_vendors(vendor_id),
    ordered_date TEXT NOT NULL,
    expected_date TEXT NOT NULL,
    cases_ordered INTEGER NOT NULL CHECK (cases_ordered > 0),
    cases_delivered INTEGER NOT NULL DEFAULT 0 CHECK (cases_delivered >= 0),
    status TEXT NOT NULL CHECK (
        status IN ('placed', 'in_transit', 'delivered', 'partially_delivered', 'cancelled')
    ),
    actor TEXT NOT NULL
);

CREATE TABLE cl_promotions (
    promotion_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    discount_pct REAL NOT NULL CHECK (discount_pct > 0 AND discount_pct <= 0.30),
    status TEXT NOT NULL CHECK (status IN ('planned', 'active', 'completed', 'cancelled')),
    approval_id TEXT,
    CHECK (start_date <= end_date)
);

CREATE TABLE cl_sales (
    sale_id TEXT PRIMARY KEY,
    business_date TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    latent_demand_units INTEGER NOT NULL CHECK (latent_demand_units >= 0),
    sold_units INTEGER NOT NULL CHECK (sold_units >= 0),
    substituted_units INTEGER NOT NULL CHECK (substituted_units >= 0),
    lost_sales_units INTEGER NOT NULL CHECK (lost_sales_units >= 0),
    unit_price REAL NOT NULL CHECK (unit_price > 0),
    revenue REAL NOT NULL CHECK (revenue >= 0),
    cogs REAL NOT NULL CHECK (cogs >= 0),
    CHECK (sold_units + substituted_units + lost_sales_units = latent_demand_units)
);

CREATE TABLE cl_substitutions (
    substitution_id TEXT PRIMARY KEY,
    business_date TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    source_product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    substitute_product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    units INTEGER NOT NULL CHECK (units > 0),
    revenue REAL NOT NULL CHECK (revenue >= 0),
    cogs REAL NOT NULL CHECK (cogs >= 0),
    CHECK (source_product_id != substitute_product_id)
);

CREATE TABLE cl_spoilage (
    spoilage_id TEXT PRIMARY KEY,
    business_date TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    lot_id TEXT NOT NULL REFERENCES cl_inventory_lots(lot_id),
    units INTEGER NOT NULL CHECK (units > 0),
    writeoff_cost REAL NOT NULL CHECK (writeoff_cost >= 0),
    reason TEXT NOT NULL CHECK (reason IN ('expired', 'cold_chain', 'damage'))
);

CREATE TABLE cl_returns_feedback (
    feedback_id TEXT PRIMARY KEY,
    business_date TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    return_units INTEGER NOT NULL CHECK (return_units >= 0),
    refund_amount REAL NOT NULL CHECK (refund_amount >= 0),
    sentiment REAL NOT NULL CHECK (sentiment >= -1 AND sentiment <= 1),
    reason TEXT NOT NULL CHECK (reason IN ('quality', 'price', 'availability', 'none'))
);

CREATE TABLE cl_operational_events (
    event_id TEXT PRIMARY KEY,
    business_date TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'supply_delay', 'demand_surge', 'cold_chain_failure', 'capacity_constraint',
            'normal_operation'
        )
    ),
    store_id TEXT REFERENCES cl_stores(store_id),
    product_id TEXT REFERENCES cl_products(product_id),
    severity REAL NOT NULL CHECK (severity >= 0 AND severity <= 1),
    public_message TEXT NOT NULL,
    resolved INTEGER NOT NULL CHECK (resolved IN (0, 1))
);

CREATE TABLE cl_cash_ledger (
    cash_id TEXT PRIMARY KEY,
    business_date TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    kind TEXT NOT NULL CHECK (
        kind IN ('opening', 'sale', 'inventory_payment', 'refund', 'spoilage', 'promotion_cost')
    ),
    amount REAL NOT NULL,
    reference_id TEXT NOT NULL,
    balance_after REAL NOT NULL
);

CREATE TABLE cl_approval_events (
    event_id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN (
            'approval_required', 'approval_requested', 'approved', 'rejected',
            'resumed', 'aborted'
        )
    ),
    business_date TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE cl_action_ledger (
    action_id TEXT PRIMARY KEY,
    business_date TEXT NOT NULL,
    actor TEXT NOT NULL,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('proposed', 'completed', 'denied', 'failed', 'aborted')
    ),
    payload_json TEXT NOT NULL,
    approval_id TEXT
);

CREATE TABLE cl_daily_metrics (
    business_date TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    revenue REAL NOT NULL,
    cogs REAL NOT NULL,
    gross_profit REAL NOT NULL,
    lost_sales_units INTEGER NOT NULL,
    spoiled_units INTEGER NOT NULL,
    returned_units INTEGER NOT NULL,
    service_level REAL NOT NULL CHECK (service_level >= 0 AND service_level <= 1),
    ending_inventory_units INTEGER NOT NULL CHECK (ending_inventory_units >= 0),
    ending_cash REAL NOT NULL,
    PRIMARY KEY (business_date, store_id)
);

CREATE TABLE cl_demand_parameters (
    store_id TEXT NOT NULL REFERENCES cl_stores(store_id),
    product_id TEXT NOT NULL REFERENCES cl_products(product_id),
    base_daily_demand REAL NOT NULL CHECK (base_daily_demand > 0),
    price_elasticity REAL NOT NULL CHECK (price_elasticity < 0),
    promotion_uplift REAL NOT NULL CHECK (promotion_uplift >= 0),
    substitution_rate REAL NOT NULL CHECK (substitution_rate >= 0 AND substitution_rate <= 1),
    quality_return_rate REAL NOT NULL CHECK (
        quality_return_rate >= 0 AND quality_return_rate <= 1
    ),
    PRIMARY KEY (store_id, product_id)
);

CREATE TABLE cl_random_draws (
    draw_key TEXT PRIMARY KEY,
    value REAL NOT NULL CHECK (value >= 0 AND value < 1)
);

CREATE INDEX idx_cl_sales_day_store ON cl_sales(business_date, store_id);
CREATE INDEX idx_cl_substitutions_day_store
    ON cl_substitutions(business_date, store_id);
CREATE INDEX idx_cl_lots_pair_expiry
    ON cl_inventory_lots(store_id, product_id, expires_date);
CREATE INDEX idx_cl_orders_status_date ON cl_purchase_orders(status, expected_date);
CREATE INDEX idx_cl_cash_store_date ON cl_cash_ledger(store_id, business_date);
"""

CLOSED_LOOP_PUBLIC_TABLES = frozenset(
    {
        "cl_stores",
        "cl_vendors",
        "cl_products",
        "cl_prices",
        "cl_inventory",
        "cl_inventory_lots",
        "cl_shelf_allocations",
        "cl_purchase_orders",
        "cl_promotions",
        "cl_sales",
        "cl_substitutions",
        "cl_spoilage",
        "cl_returns_feedback",
        "cl_operational_events",
        "cl_cash_ledger",
        "cl_approval_events",
        "cl_action_ledger",
        "cl_daily_metrics",
    }
)

CLOSED_LOOP_INTERNAL_TABLES = frozenset(
    {"cl_metadata", "cl_demand_parameters", "cl_random_draws"}
)

CLOSED_LOOP_TABLES = CLOSED_LOOP_PUBLIC_TABLES | CLOSED_LOOP_INTERNAL_TABLES
