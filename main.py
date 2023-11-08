# silverback run main:app --network base:goerli:alchemy --runner silverback.runner:WebsocketRunner
import os
import asyncio
import concurrent.futures
from dotenv import load_dotenv
from ape import chain
from ape import project
from ape.api import BlockAPI
from synthetix import Synthetix

from silverback import SilverbackApp

# load the environment variables
load_dotenv()

PROVIDER_RPC_URL = os.environ.get('TESTNET_RPC')
ADDRESS = os.environ.get('ADDRESS')
PRIVATE_KEY = os.environ.get('PRIVATE_KEY')
NETWORK_ID = os.environ.get('NETWORK_ID')

# init snx
snx = Synthetix(
    provider_rpc=PROVIDER_RPC_URL,
    private_key=PRIVATE_KEY,
    address=ADDRESS,
    network_id=NETWORK_ID,
    price_service_endpoint='https://hermes-beta.pyth.network'
)

# Do this to initialize your app
app = SilverbackApp()

# Get the perps proxy contract
PerpsMarket = project.PerpsMarketProxy.at(snx.perps.market_proxy.address)
SpotMarket = project.SpotMarketProxy.at(snx.spot.market_proxy.address)

# Can handle some stuff on startup, like loading a heavy model or something
@app.on_startup()
def startup(state):
    return {"message": "Starting..."}


# Log new blocks
@app.on_(chain.blocks)
def exec_block(block: BlockAPI):
    print("NEW BLOCK: ", block.number)
    return {"message": f"Received block number {block.number}"}

# Perps orders
# settle perps order function
def settle_perps_order(event):
    account_id = event['accountId']
    market_id = event['marketId']
    market_name = snx.perps.markets_by_id[market_id]["market_name"]

    snx.logger.info(f'Settling order for {account_id} for market {market_name}')
    snx.perps.settle_pyth_order(account_id, submit=True)

@app.on_(PerpsMarket.OrderCommitted, new_block_timeout=5)
def perps_order_committed(event):
    print(f"Perps order committed: {event}")
    settle_perps_order(event)
    return {"message": f"Perps order committed: {event}"}

# Spot orders
# settle spot order function
def settle_spot_order(event):
    market_id = event['marketId']
    market_id, market_name = snx.spot._resolve_market(market_id=market_id, market_name=None)

    async_order_id = event['asyncOrderId']
    
    snx.logger.info(f'Settling order {async_order_id} for market {market_name}')
    snx.spot.settle_pyth_order(async_order_id, market_id=market_id, submit=True)

@app.on_(SpotMarket.OrderCommitted, new_block_timeout=5)
def order_committed(event):
    print(f"Spot order committed: {event}")
    settle_spot_order(event)
    return {"message": f"Spot order committed: {event}"}


# Just in case you need to release some resources or something
@app.on_shutdown()
def shutdown(state):
    return {"message": "Stopping..."}
