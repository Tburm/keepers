# silverback run price_pusher:app --network base:sepolia:alchemy --runner silverback.runner:WebsocketRunner
import os
from dotenv import load_dotenv
from ape import chain
from ape.api import BlockAPI
from synthetix import Synthetix
from synthetix.utils.multicall import write_erc7412

from silverback import SilverbackApp

# load the environment variables
load_dotenv()

ADDRESS = os.environ.get("ADDRESS")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
STALENESS_TOLERANCE = 3300

# init snx
snx = Synthetix(
    provider_rpc=chain.provider.uri,
    private_key=PRIVATE_KEY,
    address=ADDRESS,
    is_fork=chain.provider.name == "foundry",
)

# Do this to initialize your app
app = SilverbackApp()


@app.on_startup()
def startup(state):
    # log the available markets
    snx.logger.info(f"Available markets: {snx.perps.markets_by_name.keys()}")
    pass


# Log new blocks
@app.on_(chain.blocks)
def exec_block(block: BlockAPI):
    if block.number % 30 == 0:
        write_prices_tx = write_erc7412(
            snx,
            snx.core.core_proxy,
            "getVaultDebt",
            (1, "0xC74eA762cF06c9151cE074E6a569a5945b6302E7"),
        )
        snx.logger.info(f"Write prices tx: {write_prices_tx}")

        # decode to get tx length
        multicall_contract = snx.contracts["TrustedMulticallForwarder"]["contract"]
        _, input = multicall_contract.decode_function_input(write_prices_tx["data"])

        if len(input["calls"]) > 1:
            snx.logger.info(f"Price update required, writing prices")
            write_prices_tx_hash = snx.execute_transaction(write_prices_tx)
            write_prices_receipt = snx.wait(write_prices_tx_hash)
            snx.logger.info(f"Write prices receipt: {write_prices_receipt.status}")
        else:
            snx.logger.info("No price update required")
