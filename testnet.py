# silverback run main:app --network base:mainnet:alchemy --runner silverback.runner:WebsocketRunner
import os
import time
from dotenv import load_dotenv
from ape import chain, Contract
from ape.api import BlockAPI
from synthetix import Synthetix
from utils.swap import assemble_transaction

from silverback import SilverbackApp

# load the environment variables
load_dotenv('.env')

ADDRESS = os.environ.get("ADDRESS")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
CANNON_PRESET = os.environ.get("CANNON_PRESET")

# constants
DELAY_SECONDS = 0


# init snx
snx = Synthetix(
    provider_rpc=chain.provider.uri,
    private_key=PRIVATE_KEY,
    address=ADDRESS,
    is_fork=chain.provider.name == "foundry",
    cannon_config={
        'package': "synthetix-omnibus",
        "version": "latest",
        "preset": CANNON_PRESET,
    }
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
        tx_hash = snx.execute_transaction(order_settlement_tx)
        tx_receipt = snx.wait(tx_hash)

        if tx_receipt["status"] == 1:
            snx.logger.info(
                f"Keeper settled {market_name} order committed by {account_id}"
            )
        else:
            snx.logger.error(
                f"Keeper failed to settle {market_name} order committed by {account_id}"
            )
    else:
        snx.logger.info(f"Keeper settled {market_name} order committed by {account_id}")


@app.on_(PerpsMarket.OrderCommitted, new_block_timeout=60)
def perps_order_committed(event):
    settle_perps_order(event)
    return {"message": f"Perps order committed: {event}"}


# check balance and swap
# Log new blocks
@app.on_(chain.blocks, new_block_timeout=60)
def exec_block(block: BlockAPI):
    snx.logger.info(f"Block number: {block.number}")
