from prometheus_client import Counter, Gauge, Histogram

# general
eth_balance = Gauge("eth_balance", "ETH balance of the keeper")

# prices
prices_pushed = Histogram("prices_pushed", "Number of prices pushed to Pyth")
price_pushes_failed = Counter("price_pushes_failed", "Number of price pushes failed")
price_pushes_skipped = Counter(
    "price_pushes_skipped",
    "Number of price pushes skipped because they were above the max cost",
)

# orders
order_committed = Counter(
    "order_committed", "Number of orders committed to the perps markets"
)
orders_settled = Counter("orders_settled", "Number of orders settled by this keeper")
orders_failed = Counter(
    "orders_failed", "Number of orders failed to settle by this keeper"
)
orders_settled_by_others = Counter(
    "orders_settled_by_others", "Number of orders settled by other keepers"
)

# liquidations
active_accounts = Gauge("active_accounts", "Number of active perps accounts")
liquidatable_accounts = Gauge(
    "liquidatable_accounts", "Number of accounts eligible for liquidation"
)
liquidations_submitted = Counter(
    "liquidations_submitted", "Number of account liquidations transactions"
)
liquidations_failed = Counter(
    "liquidations_failed", "Number of account liquidations transactions that failed"
)
