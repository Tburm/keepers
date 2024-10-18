"""A keeper to push prices for stale prices"""

import os
from dotenv import load_dotenv
from ape import chain
from ape.api import BlockAPI
from synthetix import Synthetix
from synthetix.utils.multicall import write_erc7412, multicall_erc7412
from eth_utils import decode_hex

from utils.metrics import (
    eth_balance,
    prices_pushed,
    price_pushes_failed,
    price_pushes_skipped,
)
from prometheus_client import start_http_server

from silverback import SilverbackApp

# load the environment variables
load_dotenv()

ADDRESS = os.getenv("ADDRESS")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
CANNON_PRESET = os.getenv("CANNON_PRESET")
PRICE_SERVICE_ENDPOINT = os.getenv("PRICE_SERVICE_ENDPOINT")
NETWORK_10_RPC = os.environ.get("NETWORK_10_RPC")

# constant
STALENESS_TOLERANCE = 3300
MAX_ETH_COST = 0.05

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


def check_prices(snx, feed_ids):
    """For a list of feed ids, check if the prices are stale"""
    # get the contract
    contract = snx.contracts["pyth_erc7412_wrapper"]["PythERC7412Wrapper"]["contract"]
    function_name = "getLatestPrice"

    # encode the inputs
    args_list = [(decode_hex(feed_id), STALENESS_TOLERANCE) for feed_id in feed_ids]

    # prepare the initial calls
    calls = [
        (
            contract.address,
            False,
            0,
            contract.encodeABI(fn_name=function_name, args=args),
        )
        for args in args_list
    ]

    # call it
    results = snx.multicall.functions.aggregate3Value(calls).call()
    stale_feeds = [
        feed_ids[ind] for ind, result in enumerate(results) if result[0] == False
    ]

    if len(stale_feeds) > 0:
        # get pyth price update data
        pyth_result = snx.pyth.get_price_from_ids(stale_feeds)
        price_update_data = pyth_result["price_update_data"]

        # prepare a pyth call
        pyth_contract = snx.contracts["Pyth"]["contract"]
        tx_params = snx._get_tx_params(value=len(stale_feeds))
        tx_params = pyth_contract.functions.updatePriceFeeds(
            price_update_data
        ).build_transaction(tx_params)
        snx.logger.info(f"Tx: {tx_params}")

        # send the transaction
        eth_cost = (tx_params["gas"] * tx_params["maxFeePerGas"]) / 1e18
        snx.logger.info(f"Estimated ETH cost: {eth_cost} ETH")

        if eth_cost < MAX_ETH_COST:
            tx_hash = snx.execute_transaction(tx_params)
            tx_receipt = snx.wait(tx_hash)

            # log the result
            if tx_receipt["status"] == 1:
                snx.logger.info(f"Price feeds updated successfully")
                prices_pushed.observe(len(stale_feeds))
            else:
                snx.logger.error(f"Price feeds update failed")
                price_pushes_failed.inc()
        else:
            snx.logger.info("Too rich for my blood, brother")
            price_pushes_skipped.inc()
    else:
        snx.logger.info(f"No stale prices found")


@app.on_startup()
def startup(state):
    # log the available markets
    snx.logger.info(f"Available markets: {snx.perps.markets_by_name.keys()}")

    # check the prices
    price_feed_ids = list(snx.pyth.price_feed_ids.values())
    check_prices(snx, price_feed_ids)

    # update the eth balance
    eth_balance_dict = snx.get_eth_balance()
    eth_balance.set(eth_balance_dict["eth"])
    pass


# Log new blocks
@app.on_(chain.blocks)
def exec_block(block: BlockAPI):
    if block.number % 30 == 0:
        price_feed_ids = list(snx.pyth.price_feed_ids.values())
        check_prices(snx, price_feed_ids)

        # update the eth balance
        eth_balance_dict = snx.get_eth_balance()
        eth_balance.set(eth_balance_dict["eth"])
