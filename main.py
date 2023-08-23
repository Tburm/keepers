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




class Keeper:
    def __init__(self):
        self.snx = Synthetix(
            provider_rpc=PROVIDER_RPC_URL,
            private_key=PRIVATE_KEY,
            address=ADDRESS,
            network_id=420,
        )

    def process_event(self, event):
        # extract the required information from the event
        account_id = event["args"]["accountId"]
        market_id = event["args"]["marketId"]
        market_name = self.snx.perps.markets_by_id[market_id]["market_name"]

        self.snx.logger.info(f'Settling order for {account_id} for market {market_name}')
        self.snx.perps.settle_pyth_order(account_id, submit=True)

    async def monitor_events(self):
        event_filter = self.snx.perps.market_proxy.events.OrderCommitted.create_filter(fromBlock="latest")

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:

            while True:
                self.snx.logger.info('Checking for new orders')
                try:
                    events = event_filter.get_new_entries()

                    for event in events:
                        loop.run_in_executor(executor, self.process_event, event)
                except Exception as e:
                    print(e)

                self.snx.logger.info(f'{len(events)} orders processed, waiting for new orders')
                await asyncio.sleep(15)  # Adjust the sleep time as needed


async def main():
    keeper = Keeper()
    await keeper.monitor_events()

if __name__ == "__main__":
    asyncio.run(main())

