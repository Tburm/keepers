"""A keeper for V3 perps, including orders and liquidations"""

import os
import time
from dotenv import load_dotenv
from ape import chain, Contract
from ape.api import BlockAPI
from synthetix import Synthetix
from utils.swap import execute_base_swap, execute_arbitrum_swap
from utils.perps_v3 import (
    settle_perps_order,
    get_active_accounts,
    get_liquidatable_accounts,
    liquidate_accounts,
)

from silverback import SilverbackBot

# load the environment variables
load_dotenv()

ADDRESS = os.getenv("ADDRESS")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
CANNON_PRESET = os.getenv("CANNON_PRESET")
PRICE_SERVICE_ENDPOINT = os.getenv("PRICE_SERVICE_ENDPOINT")
NETWORK_10_RPC = os.environ.get("NETWORK_10_RPC")

# constants
ORDER_DELAY_SECONDS = os.getenv("ORDER_DELAY_SECONDS")
SWAP_THRESHOLD = os.getenv("SWAP_THRESHOLD_USD")
BLOCKS_LIQUIDATE = os.getenv("BLOCKS_LIQUIDATE")
BLOCKS_ACCOUNT_REFRESH = os.getenv("BLOCKS_ACCOUNT_REFRESH")
BLOCKS_SWAP = os.getenv("BLOCKS_SWAP")

ORDER_DELAY_SECONDS = 0 if ORDER_DELAY_SECONDS is None else int(ORDER_DELAY_SECONDS)
SWAP_THRESHOLD = 200 if SWAP_THRESHOLD is None else int(SWAP_THRESHOLD)
BLOCKS_LIQUIDATE = 10 if BLOCKS_LIQUIDATE is None else int(BLOCKS_LIQUIDATE)
BLOCKS_ACCOUNT_REFRESH = (
    100 if BLOCKS_ACCOUNT_REFRESH is None else int(BLOCKS_ACCOUNT_REFRESH)
)
BLOCKS_SWAP = 100 if BLOCKS_SWAP is None else int(BLOCKS_SWAP)

# Do this to initialize your bot
bot = SilverbackBot()

# init snx
snx = Synthetix(
    provider_rpc=bot.provider.uri,
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

# Get the perps proxy contract
PerpsMarket = Contract(
    address=snx.perps.market_proxy.address, abi=snx.perps.market_proxy.abi
)


@bot.on_startup()
def startup(state):
    """On startup, initialize the state"""
    bot.state["account_ids"] = get_active_accounts(snx)
    return {"message": "Starting..."}


@bot.on_(PerpsMarket.OrderCommitted, new_block_timeout=60)
def perps_order_committed(event):
    """Settle orders on the perps markets"""
    settle_perps_order(snx, event, settle_delay=ORDER_DELAY_SECONDS)
    return {"message": f"Perps order committed: {event}"}


@bot.on_(chain.blocks, new_block_timeout=60)
def exec_block(block: BlockAPI):
    """Actions to take on every block"""
    # every 10 blocks run these
    if block.number % BLOCKS_LIQUIDATE == 0:
        # check liquidations
        liquidatable_accounts = get_liquidatable_accounts(snx, bot.state["account_ids"])

        if len(liquidatable_accounts) > 0:
            liquidate_accounts(snx, liquidatable_accounts)

    # every 100 blocks update accounts
    if block.number % BLOCKS_ACCOUNT_REFRESH == 0:
        # update account ids
        bot.state["account_ids"] = get_active_accounts(snx)

    # every 100 blocks run the swap
    if block.number % BLOCKS_SWAP == 0:
        # execute swap according to the network
        if snx.network_id == 8453:
            execute_base_swap(snx, SWAP_THRESHOLD)
        elif snx.network_id == 42161:
            execute_arbitrum_swap(snx, SWAP_THRESHOLD)
