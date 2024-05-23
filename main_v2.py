# silverback run main:app --network optimism:sepolia:alchemy --runner silverback.runner:WebsocketRunner
import os
import time
from dotenv import load_dotenv
from ape import chain, Contract
from ape.api import BlockAPI
from kwenta import Kwenta
from utils.swap import assemble_transaction

from silverback import SilverbackApp

# load the environment variables
load_dotenv()

ADDRESS = os.environ.get("ADDRESS")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")

# init snx
kwenta = Kwenta(
    provider_rpc=chain.provider.uri,
    wallet_address=ADDRESS,
    private_key=PRIVATE_KEY,
    network_id=chain.provider.chain_id,
)

# Do this to initialize your app
app = SilverbackApp()

# Get the perps proxy contract
PerpsMarkets = [
    Contract(
        address=kwenta.market_contracts[contract].address,
        abi=kwenta.market_contracts[contract].abi,
    )
    for contract in kwenta.market_contracts
]


# Perps orders
# settle perps order function
def settle_perps_order(event):
    print(event)
    # account_id = event["accountId"]
    # market_id = event["marketId"]
    # market_name = snx.perps.markets_by_id[market_id]["market_name"]

    # # add a delay
    # snx.logger.info(f"{market_name} Order committed by {account_id}")
    # time.sleep(DELAY_SECONDS)

    # order = snx.perps.get_order(account_id)
    # if order["size_delta"] != 0:
    #     snx.logger.info(f"Settling {market_name} order committed by {account_id}")
    #     order_settlement_tx = snx.perps.settle_order(account_id, submit=False)

    #     # double the base fee
    #     order_settlement_tx["maxFeePerGas"] = order_settlement_tx["maxFeePerGas"] * 2
    #     tx_hash = snx.execute_transaction(order_settlement_tx)
    #     tx_receipt = snx.wait(tx_hash)

    #     if tx_receipt["status"] == 1:
    #         snx.logger.info(
    #             f"Keeper settled {market_name} order committed by {account_id}"
    #         )
    #     else:
    #         snx.logger.error(
    #             f"Keeper failed to settle {market_name} order committed by {account_id}"
    #         )
    # else:
    #     snx.logger.info(f"Keeper settled {market_name} order committed by {account_id}")


for PerpsMarket in PerpsMarkets:

    @app.on_(PerpsMarket.DelayedOrderSubmitted, new_block_timeout=60)
    def perps_order_committed(event):
        settle_perps_order(event)
        return {"message": f"Perps order committed: {event}"}


# check balance and swap
# Log new blocks
@app.on_(chain.blocks, new_block_timeout=60)
def exec_block(block: BlockAPI):
    # log the block
    print(f"New block: {block.number}")
