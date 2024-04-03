# silverback run main:app --network base:mainnet:alchemy --runner silverback.runner:WebsocketRunner
import os
import time
from dotenv import load_dotenv
from ape import chain, Contract
from ape.api import BlockAPI
from synthetix import Synthetix

from silverback import SilverbackApp

# load the environment variables
load_dotenv()

PROVIDER_RPC_URL = os.environ.get("PROVIDER_RPC")
ADDRESS = os.environ.get("ADDRESS")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
NETWORK_ID = os.environ.get("NETWORK_ID")

# constants
DELAY_SECONDS = 10

# init snx
snx = Synthetix(
    provider_rpc=PROVIDER_RPC_URL,
    private_key=PRIVATE_KEY,
    address=ADDRESS,
    network_id=NETWORK_ID,
    cannon_config={
        "package": "synthetix-omnibus",
        "version": "7",
        "preset": "andromeda",
    },
)

# Do this to initialize your app
app = SilverbackApp()

# Get the perps proxy contract
PerpsMarket = Contract(
    address=snx.perps.market_proxy.address, abi=snx.perps.market_proxy.abi
)


# Perps orders
# settle perps order function
def settle_perps_order(event):
    account_id = event["accountId"]
    market_id = event["marketId"]
    market_name = snx.perps.markets_by_id[market_id]["market_name"]

    # add a delay
    snx.logger.info(f"{market_name} Order committed by {account_id}")
    time.sleep(DELAY_SECONDS)

    order = snx.perps.get_order(account_id)
    if order["size_delta"] != 0:
        snx.logger.info(f"Settling {market_name} order committed by {account_id}")
        order_settlement_tx = snx.perps.settle_order(account_id, submit=False)

        # double the base fee
        order_settlement_tx["maxFeePerGas"] = order_settlement_tx["maxFeePerGas"] * 2
        snx.execute_transaction(order_settlement_tx)
    else:
        snx.logger.info(f"Keeper settled {market_name} order committed by {account_id}")


@app.on_(PerpsMarket.OrderCommitted, new_block_timeout=5)
def perps_order_committed(event):
    settle_perps_order(event)
    return {"message": f"Perps order committed: {event}"}
