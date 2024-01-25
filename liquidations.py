# silverback run liquidations:app --network base:goerli:alchemy --runner silverback.runner:WebsocketRunner
import os
from dotenv import load_dotenv
from ape import chain, project, Contract
from ape.api import BlockAPI
from gql import gql
from synthetix import Synthetix
from synthetix.utils import wei_to_ether
from synthetix.utils.multicall import multicall_erc7412

from silverback import SilverbackApp

# load the environment variables
load_dotenv()

PROVIDER_RPC_URL = os.environ.get('PROVIDER_RPC')
ADDRESS = os.environ.get('ADDRESS')
PRIVATE_KEY = os.environ.get('PRIVATE_KEY')
NETWORK_ID = os.environ.get('NETWORK_ID')
SATSUMA_API_KEY = os.environ.get('SATSUMA_API_KEY')

# init snx
snx = Synthetix(
    provider_rpc=PROVIDER_RPC_URL,
    private_key=PRIVATE_KEY,
    address=ADDRESS,
    network_id=NETWORK_ID,
)

# function to get account ids
def get_account_ids(snx):
    """Fetch a list of accounts that have some collateral and have open positions"""
    account_proxy = snx.perps.account_proxy
    market_proxy = snx.perps.market_proxy

    # get the total number of accounts
    total_supply = account_proxy.functions.totalSupply().call()

    # fetch the account ids
    account_ids = []
    supply_chunks = [range(x, min(x+500, total_supply)) for x in range(0, total_supply, 500)]
    for supply_chunk in supply_chunks:
        accounts = multicall_erc7412(
            snx, account_proxy, 'tokenByIndex', supply_chunk
        )
        account_ids.extend(accounts)

    # check those accounts margin requirements
    require_margins = []
    values = []
    margin_chunks = [account_ids[x:min(x+500, total_supply)] for x in range(0, total_supply, 500)]
    for margin_chunk in margin_chunks:
        margins = multicall_erc7412(
            snx, market_proxy, 'getRequiredMargins', margin_chunk
        )
        collateral_values = multicall_erc7412(
            snx, market_proxy, 'totalCollateralValue', margin_chunk
        )
        
        values.extend(collateral_values)
        require_margins.extend(margins)

    # filter accounts without a margin requirement
    # filter accounts with less than 100 USD in collateral
    # this eliminates accounts that have no open positions or small amounts of collateral
    account_infos = zip(account_ids, require_margins, values)
    accounts_to_check = [
        account[0]
        for account in account_infos
        if wei_to_ether(account[1][1]) >= 0 and wei_to_ether(account[2]) >= 100
    ]
    return accounts_to_check

# Set up the app state
app_state = {
    "account_ids": [],
}

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
    app_state['account_ids'] = get_account_ids(snx)
    return {"message": "Starting..."}


# Log new blocks
@app.on_(chain.blocks)
def exec_block(block: BlockAPI):
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
            snx.logger.info(f"Found {len(liquidatable_accounts)} liquidatable accounts")
            for account in liquidatable_accounts:
                snx.logger.info(f"Liquidating account {account}")
                try:
                    tx = snx.perps.liquidate(account, submit=True)
                except Exception as e:
                    snx.logger.error(f"Error liquidating account {account}: {e}")

    return {"message": f"Received block number {block.number}"}
