# to run: silverback run "test_silverback:app" --network optimism:goerli:alchemy
import os
import asyncio
import concurrent.futures
from dotenv import load_dotenv
from ape import chain
from ape import project
from ape.api import BlockAPI
from synthetix import Synthetix

from silverback import SilverBackApp

# load the environment variables
load_dotenv()

PROVIDER_RPC_URL = os.environ.get('TESTNET_RPC')
ADDRESS = os.environ.get('ADDRESS')
PRIVATE_KEY = os.environ.get('PRIVATE_KEY')

# init snx
snx = Synthetix(
    provider_rpc=PROVIDER_RPC_URL,
    private_key=PRIVATE_KEY,
    address=ADDRESS,
    network_id=420,
)

# Do this to initialize your app
app = SilverBackApp()

# Get the perps proxy contract
PerpsMarket = project.PerpsMarketProxy.at('0xf272382cB3BE898A8CdB1A23BE056fA2Fcf4513b')

# Can handle some stuff on startup, like loading a heavy model or something
@app.on_startup()
def startup(state):
    return {"message": "Starting..."}


# Log new blocks
@app.on_(chain.blocks)
def exec_block(block: BlockAPI):
    print("NEW BLOCK: ", block.number)
    return {"message": f"Received block number {block.number}"}

# Order keeper
# settle function
def settle_order(event):
    account_id = event['accountId']
    market_id = event['marketId']
    market_name = snx.perps.markets_by_id[market_id]["market_name"]

    snx.logger.info(f'Settling order for {account_id} for market {market_name}')
    snx.perps.settle_pyth_order(account_id, submit=True)

@app.on_(PerpsMarket.OrderCommitted, new_block_timeout=5)
def order_committed(event):
    print(f"Order committed: {event}")
    settle_order(event)
    return {"message": f"Order committed: {event}"}


# Just in case you need to release some resources or something
@app.on_shutdown()
def shutdown(state):
    return {"message": "Stopping..."}
