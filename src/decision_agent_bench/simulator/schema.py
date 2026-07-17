"""SQLite schema for the synthetic company."""

SCHEMA_VERSION = "0.1.0"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE regions (
    region_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE stores (
    store_id TEXT PRIMARY KEY,
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    name TEXT NOT NULL,
    format TEXT NOT NULL CHECK (format IN ('urban', 'suburban', 'highway')),
    square_feet INTEGER NOT NULL CHECK (square_feet > 0)
);

CREATE TABLE vendors (
    vendor_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    lead_time_days INTEGER NOT NULL CHECK (lead_time_days > 0),
    min_order_cases INTEGER NOT NULL CHECK (min_order_cases > 0),
    capacity_cases_per_week INTEGER NOT NULL CHECK (capacity_cases_per_week > 0),
    active INTEGER NOT NULL CHECK (active IN (0, 1))
);

CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
    category TEXT NOT NULL,
    name TEXT NOT NULL UNIQUE,
    unit_cost REAL NOT NULL CHECK (unit_cost > 0),
    case_pack INTEGER NOT NULL CHECK (case_pack > 0),
    shelf_life_days INTEGER CHECK (shelf_life_days IS NULL OR shelf_life_days > 0),
    active INTEGER NOT NULL CHECK (active IN (0, 1))
);

CREATE TABLE oracle_parameters (
    product_id TEXT PRIMARY KEY REFERENCES products(product_id),
    price_elasticity REAL NOT NULL CHECK (price_elasticity < 0),
    demand_multiplier REAL NOT NULL CHECK (demand_multiplier > 0)
);

CREATE TABLE prices (
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    unit_price REAL NOT NULL CHECK (unit_price > 0),
    effective_date TEXT NOT NULL,
    PRIMARY KEY (store_id, product_id)
);

CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    segment TEXT NOT NULL CHECK (segment IN ('commuter', 'local', 'traveler', 'value')),
    home_store_id TEXT NOT NULL REFERENCES stores(store_id)
);

CREATE TABLE promotions (
    promo_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(product_id),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    discount_pct REAL NOT NULL CHECK (discount_pct > 0 AND discount_pct < 1),
    vendor_funding_pct REAL NOT NULL CHECK (vendor_funding_pct >= 0 AND vendor_funding_pct <= 1),
    status TEXT NOT NULL CHECK (status IN ('planned', 'active', 'completed', 'cancelled')),
    CHECK (start_date <= end_date)
);

CREATE TABLE inventory (
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    on_hand_units INTEGER NOT NULL CHECK (on_hand_units >= 0),
    reorder_point INTEGER NOT NULL CHECK (reorder_point >= 0),
    last_updated TEXT NOT NULL,
    PRIMARY KEY (store_id, product_id)
);

CREATE TABLE inventory_lots (
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    lot_id TEXT NOT NULL,
    on_hand_units INTEGER NOT NULL CHECK (on_hand_units >= 0),
    expires_on TEXT,
    quarantined INTEGER NOT NULL CHECK (quarantined IN (0, 1)),
    PRIMARY KEY (store_id, product_id, lot_id)
);

CREATE TABLE recall_notices (
    notice_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(product_id),
    affected_lot_id TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'closed')),
    instructions TEXT NOT NULL
);

CREATE TABLE transactions (
    transaction_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    sold_at TEXT NOT NULL,
    units INTEGER NOT NULL CHECK (units > 0),
    gross_sales REAL NOT NULL CHECK (gross_sales >= 0),
    discount_amount REAL NOT NULL CHECK (discount_amount >= 0),
    net_sales REAL NOT NULL CHECK (net_sales >= 0),
    cogs REAL NOT NULL CHECK (cogs >= 0)
);

CREATE INDEX idx_transactions_store_date ON transactions(store_id, sold_at);
CREATE INDEX idx_transactions_product_date ON transactions(product_id, sold_at);

CREATE TABLE refunds (
    refund_id TEXT PRIMARY KEY,
    original_transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    refunded_at TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    reason TEXT NOT NULL CHECK (reason IN ('quality', 'wrong_item', 'customer_request')),
    receipt_present INTEGER NOT NULL CHECK (receipt_present IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('approved', 'review'))
);

CREATE INDEX idx_refunds_customer_date ON refunds(customer_id, refunded_at);

CREATE TABLE payment_events (
    event_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
    terminal_id TEXT NOT NULL,
    processor_reference TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('authorized', 'captured', 'reversed', 'duplicate')
    ),
    event_at TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0)
);

CREATE INDEX idx_payment_reference ON payment_events(processor_reference);

CREATE TABLE data_feed_status (
    feed_name TEXT NOT NULL,
    scope TEXT NOT NULL,
    last_complete_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('current', 'delayed', 'partial')),
    expected_frequency_minutes INTEGER NOT NULL CHECK (expected_frequency_minutes > 0),
    PRIMARY KEY (feed_name, scope)
);

CREATE TABLE competitor_prices (
    observation_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    observed_price REAL NOT NULL CHECK (observed_price > 0),
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    verified INTEGER NOT NULL CHECK (verified IN (0, 1))
);

CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    trust_level TEXT NOT NULL CHECK (
        trust_level IN ('authoritative', 'internal', 'external_untrusted')
    ),
    version TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    checksum TEXT NOT NULL
);

CREATE TABLE approvals (
    approval_id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    amount REAL NOT NULL,
    justification TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE action_ledger (
    action_id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('requested', 'completed', 'denied', 'failed')),
    payload_json TEXT NOT NULL,
    approval_id TEXT REFERENCES approvals(approval_id),
    created_at TEXT NOT NULL
);
"""

PUBLIC_TABLES = frozenset(
    {
        "regions",
        "stores",
        "vendors",
        "products",
        "prices",
        "customers",
        "promotions",
        "inventory",
        "inventory_lots",
        "transactions",
        "refunds",
        "payment_events",
        "data_feed_status",
        "competitor_prices",
        "recall_notices",
        "documents",
        "approvals",
        "action_ledger",
    }
)

INTERNAL_TABLES = frozenset({"metadata", "oracle_parameters"})
