# silverback run main:app --network base:goerli:alchemy --runner silverback.runner:WebsocketRunner
import os
from dotenv import load_dotenv
from ape import chain, project, Contract
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
    price_service_endpoint='https://hermes.pyth.network'
)

# Do this to initialize your app
app = SilverbackApp()

# Get the perps proxy contract
PerpsMarket = Contract(
    address=snx.perps.market_proxy.address,
    abi=snx.perps.market_proxy.abi
)

# Can handle some stuff on startup, like loading a heavy model or something
@app.on_startup()
def startup(state):
    return {"message": "Starting..."}


# Log new blocks
@app.on_(chain.blocks)
def exec_block(block: BlockAPI):
    return {"message": f"Received block number {block.number}"}

# Perps orders
# settle perps order function
def settle_perps_order(event):
    account_id = event['accountId']
    market_id = event['marketId']
    market_name = snx.perps.markets_by_id[market_id]["market_name"]

    snx.logger.info(f'Settling order for {account_id} for market {market_name}')
    snx.perps.settle_order(account_id, submit=True)

@app.on_(PerpsMarket.OrderCommitted, new_block_timeout=5)
def perps_order_committed(event):
    print(f"Perps order committed: {event}")
    settle_perps_order(event)
    return {"message": f"Perps order committed: {event}"}

# Just in case you need to release some resources or something
@app.on_shutdown()
def shutdown(state):
    return {"message": "Stopping..."}
