# to run: silverback run liquidations:app --network optimism:goerli:alchemy --runner silverback.runner:WebsocketRunner
import os
import asyncio
import concurrent.futures
from dotenv import load_dotenv
from ape import chain
from ape import project
from ape.api import BlockAPI
from gql import gql
from synthetix import Synthetix

from silverback import SilverBackApp

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
)

# function to get account ids
def get_account_ids(snx):
    query = gql("""
        query(
            $last_id: ID!
        ) {
            orders (
                where: {
                    id_gt: $last_id
                }
                first: 1000
            ) {
                id
                accountId
            }
        }
    """)

    params = {
        'last_id': '',
    }

    url = 'https://api.thegraph.com/subgraphs/name/tburm/perps-market-optimism-goerli'

    result = snx.queries._run_query_sync(query, params, 'orders', url)
    account_ids = [int(account_id) for account_id in result['accountId'].unique().tolist()]
    return account_ids

# Set up the app state
app_state = {
    "account_ids": [],
}

# Do this to initialize your app
app = SilverBackApp()

# Get the perps proxy contract
PerpsMarket = project.PerpsMarketProxy.at(snx.perps.market_proxy.address)

# Can handle some stuff on startup, like loading a heavy model or something
@app.on_startup()
def startup(state):
    app_state['account_ids'] = get_account_ids(snx)
    return {"message": "Starting..."}


# Log new blocks
@app.on_(chain.blocks)
def exec_block(block: BlockAPI):
    print("NEW BLOCK: ", block.number)
    # every 100 blocks, refresh the account ids
    if block.number % 100 == 0:
        app_state['account_ids'] = get_account_ids(snx)
    
    # every 10 blocks check for liquidations
    if block.number % 10 == 0:
        # split into 500 account chunks and check liquidations
        chunks = [app_state['account_ids'][x:x+500] for x in range(0, len(app_state['account_ids']), 500)]

        for chunk in chunks:
            can_liquidates = snx.perps.get_can_liquidates(chunk)

            liquidatable_accounts = [can_liquidate[0] for can_liquidate in can_liquidates if can_liquidate[1]]
            for account in liquidatable_accounts:
                print(f'Liquidating account {account}')
                try:
                    tx = snx.perps.liquidate(account, submit=True)
                    print(tx)
                except Exception as e:
                    print(f'Error liquidating account {account}: {e}')

    return {"message": f"Received block number {block.number}"}
