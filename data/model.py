"""Ridgeline Outfitters — the mock data, straight from the data model doc.

Everything here is plain data. Dates are *offsets in days* from AS_OF (today by
default), never fixed dates, so the demo gives the same answers whatever day it
runs. Money is in integer cents; the generator and the pricing service convert.
"""

# --- Sales users (Salesforce User) -----------------------------------------

USERS = [
    {"name": "Dana Ruiz", "role": "Sales rep", "region": "Mountain West"},
    {"name": "Marcus Chen", "role": "Sales rep", "region": "Southeast"},
    {"name": "Priya Natarajan", "role": "Sales rep", "region": "Pacific Northwest"},
    {"name": "Tom Kowalski", "role": "Sales rep", "region": "Midwest"},
    {"name": "Laura Bennett", "role": "Sales manager", "region": "National"},
]

SALES_MANAGER = "Laura Bennett"
CREDIT_MANAGER = "Greg Whitfield"

# --- Products (Product2 + standard pricebook) ------------------------------
# list_price in cents. FRT-STD is the freight line; its price varies per order.

PRODUCTS = [
    {
        "sku": "TENT-TL2",
        "name": "TrailLite 2P Tent",
        "category": "Tent",
        "list_price": 24900,
        "description": (
            "Two-person, three-season backpacking tent. 3 lb 8 oz packed, "
            "freestanding aluminum frame, two doors and vestibules. "
            "Ridgeline's best-selling wholesale tent."
        ),
    },
    {
        "sku": "TENT-BC4",
        "name": "Basecamp 4P Tent",
        "category": "Tent",
        "list_price": 42900,
        "description": (
            "Four-person car-camping and basecamp tent with 6 ft peak height, "
            "full-coverage rainfly, and gear loft. Popular with guide outfitters "
            "for group trips."
        ),
    },
    {
        "sku": "PACK-RDG45",
        "name": "Ridge 45L Pack",
        "category": "Pack",
        "list_price": 17900,
        "description": (
            "45-liter internal-frame pack for weekend trips. Adjustable torso, "
            "hip-belt pockets, hydration sleeve, and integrated rain cover."
        ),
    },
    {
        "sku": "STOVE-EMB",
        "name": "Ember Canister Stove",
        "category": "Stove",
        "list_price": 6900,
        "description": (
            "Ultralight canister stove with piezo igniter; boils 1 L in about "
            "3.5 minutes. Fuel sold separately."
        ),
    },
    {
        "sku": "BAG-DN20",
        "name": "Downline 20° Sleeping Bag",
        "category": "Sleeping bag",
        "list_price": 29900,
        "description": (
            "20°F-rated mummy bag with 650-fill responsibly sourced down, "
            "water-resistant shell, and draft collar. Regular and long sizes."
        ),
    },
    {
        "sku": "JKT-SHL",
        "name": "Stormline Shell Jacket",
        "category": "Apparel",
        "list_price": 21900,
        "description": (
            "Waterproof, breathable 2.5-layer rain shell with pit zips and "
            "adjustable hood. Packs into its own pocket. Men's and women's "
            "cuts, XS–XXL."
        ),
    },
    {
        "sku": "FRT-STD",
        "name": "Freight",
        "category": "Service",
        "list_price": 0,
        "description": "Shipping charge on an order.",
    },
]

FREIGHT_SKU = "FRT-STD"
SELLABLE_SKUS = [p["sku"] for p in PRODUCTS if p["sku"] != FREIGHT_SKU]

# --- The five named accounts (each has a story) ----------------------------
# credit_limit in cents. Trend target = order dollars, last 90 days vs the 90
# before, pending orders included.

ACCOUNTS = [
    {
        "account_id": "ACC-SUMMIT",
        "name": "Summit Trail Co.",
        "tier": "Gold",
        "region": "Mountain West",
        "owner": "Dana Ruiz",
        "erp_customer_id": "C-10231",
        "legal_name": "Summit Trail Company LLC",
        "credit_limit": 15000000,
        "trend_target_pct": 8.0,
        # Order dollars to lay down in each 90-day window, in cents.
        "window_last_90": 9720000,
        "window_prior_90": 9000000,
        "seasonality": "spring_preseason",
    },
    {
        "account_id": "ACC-BLUERIDGE",
        "name": "Blue Ridge Guides",
        "tier": "Silver",
        "region": "Southeast",
        "owner": "Marcus Chen",
        "erp_customer_id": "C-10388",
        "legal_name": "Blue Ridge Guide Services Inc.",
        "credit_limit": 4000000,
        "trend_target_pct": -10.0,
        "window_last_90": 4500000,
        "window_prior_90": 5000000,
        "seasonality": "summer_heavy",
    },
    {
        "account_id": "ACC-CASCADE",
        "name": "Cascade Outdoor Supply",
        "tier": "Gold",
        "region": "Pacific Northwest",
        "owner": "Priya Natarajan",
        "erp_customer_id": "C-10412",
        "legal_name": "Cascade Outdoor Supply Co.",
        "credit_limit": 8000000,
        "trend_target_pct": -10.0,
        "window_last_90": 3600000,
        "window_prior_90": 4000000,
        "seasonality": "steady",
    },
    {
        "account_id": "ACC-PINECREST",
        "name": "Pinecrest Mercantile",
        "tier": "Bronze",
        "region": "Midwest",
        "owner": "Tom Kowalski",
        "erp_customer_id": "C-10507",
        "legal_name": "Pinecrest Mercantile LLC",
        "credit_limit": 1500000,
        "trend_target_pct": 0.0,
        "window_last_90": 1200000,
        "window_prior_90": 1200000,
        "seasonality": "small_frequent",
    },
    {
        "account_id": "ACC-NORTHFORK",
        "name": "Northfork Paddle & Pack",
        "tier": "Silver",
        "region": "Southeast",
        "owner": "Marcus Chen",
        "erp_customer_id": "C-10619",
        "legal_name": "Northfork Paddle and Pack Inc.",
        "credit_limit": 5000000,
        "trend_target_pct": -30.0,
        "window_last_90": 3500000,
        "window_prior_90": 5000000,
        "seasonality": "slowdown",
    },
]

# --- Filler accounts -------------------------------------------------------
# Plausible background noise so find_account has more than five rows to search.
# No open invoices, so all Good standing. Not used in any test.

FILLER_ACCOUNTS = [
    ("ACC-ALPINE", "Alpine Trading Post", "Silver", "Mountain West", "Dana Ruiz", "C-10702", 3500000),
    ("ACC-BOULDER", "Boulder Creek Gear", "Bronze", "Mountain West", "Dana Ruiz", "C-10715", 1200000),
    ("ACC-HARBOR", "Harbor Point Outfitters", "Silver", "Southeast", "Marcus Chen", "C-10728", 2800000),
    ("ACC-LAUREL", "Laurel Ridge Supply", "Bronze", "Southeast", "Marcus Chen", "C-10733", 900000),
    ("ACC-OLYMPIC", "Olympic Trail Supply", "Gold", "Pacific Northwest", "Priya Natarajan", "C-10741", 6000000),
    ("ACC-RAINIER", "Rainier Base Camp", "Silver", "Pacific Northwest", "Priya Natarajan", "C-10756", 3000000),
    ("ACC-GREATLAKES", "Great Lakes Outdoor", "Silver", "Midwest", "Tom Kowalski", "C-10764", 2500000),
    ("ACC-PRAIRIE", "Prairie Wind Sports", "Bronze", "Midwest", "Tom Kowalski", "C-10779", 800000),
    ("ACC-TIMBER", "Timberline Retail Group", "Gold", "Mountain West", "Dana Ruiz", "C-10788", 7000000),
    ("ACC-WILLOW", "Willow Bend Adventure", "Bronze", "Midwest", "Tom Kowalski", "C-10791", 600000),
]

DEFAULT_TERMS = "Net 30"

# --- Open invoices (relative to AS_OF) -------------------------------------
# issued_days_ago; due = issue + 30. amount in cents. Every one matches an
# order total exactly.

OPEN_INVOICES = [
    {"invoice_number": "INV-5001", "erp_customer_id": "C-10231", "issued_days_ago": 20, "amount": 1420000},
    {"invoice_number": "INV-5002", "erp_customer_id": "C-10231", "issued_days_ago": 12, "amount": 2380000},
    {"invoice_number": "INV-5101", "erp_customer_id": "C-10388", "issued_days_ago": 25, "amount": 1800000},
    {"invoice_number": "INV-5102", "erp_customer_id": "C-10388", "issued_days_ago": 8, "amount": 1300000},
    {"invoice_number": "INV-5201", "erp_customer_id": "C-10412", "issued_days_ago": 105, "amount": 940000},
    {"invoice_number": "INV-5202", "erp_customer_id": "C-10412", "issued_days_ago": 15, "amount": 1260000},
    {"invoice_number": "INV-5301", "erp_customer_id": "C-10507", "issued_days_ago": 10, "amount": 200000},
    {"invoice_number": "INV-5401", "erp_customer_id": "C-10619", "issued_days_ago": 75, "amount": 420000},
    {"invoice_number": "INV-5402", "erp_customer_id": "C-10619", "issued_days_ago": 5, "amount": 780000},
]

INVOICE_TERM_DAYS = 30

# --- Pending orders (booked, not yet invoiced) -----------------------------

PENDING_ORDERS = [
    {"order_id": "ORD-9001", "account_id": "ACC-SUMMIT", "ordered_days_ago": 3, "total": 4000000},
    {"order_id": "ORD-9002", "account_id": "ACC-NORTHFORK", "ordered_days_ago": 2, "total": 900000},
]

# --- Business-rule constants (the service enforces these) ------------------

TIER_DISCOUNT_PCT = {"Gold": 10, "Silver": 5, "Bronze": 0}

SERVICE_AUTO_APPROVE_PCT = 10        # a rep's own ceiling
MANAGER_APPROVE_CEILING_PCT = 20     # above this, refused outright

STANDING_GOOD = "Good"
STANDING_WATCH = "Watch"
STANDING_CREDIT_HOLD = "Credit hold"

WATCH_DAYS = 30        # more than this past due -> Watch
CREDIT_HOLD_DAYS = 60  # more than this past due -> Credit hold

# --- Generator shape -------------------------------------------------------

HISTORY_DAYS = 540          # ~18 months of order history
WINDOW_DAYS = 90            # rolling trend window
MAX_FREIGHT_PCT = 3         # freight is at most 3% of an order


def account_by_id(account_id):
    for a in ACCOUNTS:
        if a["account_id"] == account_id:
            return a
    return None


def product_by_sku(sku):
    for p in PRODUCTS:
        if p["sku"] == sku:
            return p
    return None
