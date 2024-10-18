"""A keeper for V3 perps, including orders and liquidations"""

import os
import time
from dotenv import load_dotenv
from ape import chain, Contract
from ape.api import BlockAPI
from synthetix import Synthetix
from utils.swap import execute_base_swap, execute_arbitrum_swap
from utils.perps_l1 import (
    settle_perps_order,
    get_active_accounts,
    get_liquidatable_accounts,
    liquidate_accounts,
)

from silverback import SilverbackApp

# load the environment variables
load_dotenv()

ADDRESS = os.environ.get("ADDRESS")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
CANNON_PRESET = os.environ.get("CANNON_PRESET")
PRICE_SERVICE_ENDPOINT = os.environ.get("PRICE_SERVICE_ENDPOINT")
NETWORK_10_RPC = os.environ.get("NETWORK_10_RPC")

# constants
ORDER_DELAY_SECONDS = os.getenv("ORDER_DELAY_SECONDS")
BLOCKS_LIQUIDATE = os.getenv("BLOCKS_LIQUIDATE")
BLOCKS_ACCOUNT_REFRESH = os.getenv("BLOCKS_ACCOUNT_REFRESH")

ORDER_DELAY_SECONDS = 0 if ORDER_DELAY_SECONDS is None else int(ORDER_DELAY_SECONDS)
BLOCKS_LIQUIDATE = 10 if BLOCKS_LIQUIDATE is None else int(BLOCKS_LIQUIDATE)
BLOCKS_ACCOUNT_REFRESH = (
    100 if BLOCKS_ACCOUNT_REFRESH is None else int(BLOCKS_ACCOUNT_REFRESH)
)

# set up an initial state
app_state = {
    "account_ids": [],
}


# init snx
snx = Synthetix(
    provider_rpc=chain.provider.uri,
    private_key=PRIVATE_KEY,
    address=ADDRESS,
    request_kwargs={"timeout": 120},
    cannon_config={
        "package": "synthetix-omnibus",
        "version": "latest",
        "preset": CANNON_PRESET,
    },
    price_service_endpoint=PRICE_SERVICE_ENDPOINT,
    pyth_cache_ttl=0,
    op_mainnet_rpc=NETWORK_10_RPC,
)

# Do this to initialize your app
app = SilverbackApp()

# Get the perps proxy contract
PerpsMarket = Contract(
    address=snx.perps.market_proxy.address, abi=snx.perps.market_proxy.abi
)


@app.on_startup()
def startup(state):
    """On startup, initialize the state"""
    app_state["account_ids"] = get_active_accounts(snx)
    return {"message": "Starting..."}


@app.on_(PerpsMarket.OrderCommitted, new_block_timeout=60)
def perps_order_committed(event):
    """Settle orders on the perps markets"""
    settle_perps_order(snx, event, settle_delay=ORDER_DELAY_SECONDS)
    return {"message": f"Perps order committed: {event}"}


@app.on_(chain.blocks, new_block_timeout=60)
def exec_block(block: BlockAPI):
    """Actions to take on every block"""
    if block.number % BLOCKS_LIQUIDATE == 0:
        # check liquidations
        liquidatable_accounts = get_liquidatable_accounts(snx, app_state["account_ids"])

        if len(liquidatable_accounts) > 0:
            liquidate_accounts(snx, liquidatable_accounts)

    if block.number % BLOCKS_ACCOUNT_REFRESH == 0:
        # update account ids
        app_state["account_ids"] = get_active_accounts(snx)

    pass
