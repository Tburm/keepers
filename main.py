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
load_dotenv()

ADDRESS = os.environ.get("ADDRESS")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")

# constants
DELAY_SECONDS = 10
SWAP_THRESHOLD = 200
ODOS_ROUTER_ADDRESS = "0x19cEeAd7105607Cd444F5ad10dd51356436095a1"


# approvals
def approvals(snx):
    # contracts
    usdc_contract = snx.contracts["USDC"]["contract"]

    # check allowances
    usdc_allowance = (
        usdc_contract.functions.allowance(snx.address, ODOS_ROUTER_ADDRESS).call()
        / 1e18
    )
    susd_allowance = snx.spot.get_allowance(
        snx.spot.market_proxy.address, market_name="sUSD"
    )
    susdc_allowance = snx.spot.get_allowance(
        snx.spot.market_proxy.address, market_name="sUSDC"
    )

    # approve sUSD to spot market
    if susd_allowance == 0:
        tx_approve_susd = snx.approve(
            snx.contracts["USDProxy"]["address"],
            snx.spot.market_proxy.address,
            submit=True,
        )
        receipt_approve_susd = snx.wait(tx_approve_susd)

    # approve sUSDC to spot market
    if susdc_allowance == 0:
        tx_approve_susdc = snx.approve(
            snx.spot.markets_by_name["sUSDC"]["contract"].address,
            snx.spot.market_proxy.address,
            submit=True,
        )
        receipt_approve_susdc = snx.wait(tx_approve_susdc)

    if usdc_allowance == 0:
        approve_tx = snx.approve(
            usdc_contract.address, ODOS_ROUTER_ADDRESS, submit=True
        )
        approve_receipt = snx.wait(approve_tx)


# init snx
snx = Synthetix(
    provider_rpc=chain.provider.uri,
    private_key=PRIVATE_KEY,
    address=ADDRESS,
    is_fork=chain.provider.name == "foundry",
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
    # every 100 blocks, refresh the account ids
    snx.logger.info(f"Block number: {block.number}")
    if block.number % 25 == 0:
        # check approvals
        approvals(snx)

        # contracts
        usdc_contract = snx.contracts["USDC"]["contract"]
        susdc_contract = snx.spot.markets_by_name["sUSDC"]["contract"]
        susd_contract = snx.contracts["USDProxy"]["contract"]

        # get sUSD balance
        susd_balance = snx.get_susd_balance()
        usdc_balance = usdc_contract.functions.balanceOf(snx.address).call() / 1e6
        susdc_balance = susdc_contract.functions.balanceOf(snx.address).call() / 1e18
        eth_balance = snx.get_eth_balance()

        snx.logger.info(f"sUSD balance: {susd_balance}")
        snx.logger.info(f"USDC balance: {usdc_balance}")
        snx.logger.info(f"sUSDC balance: {susdc_balance}")
        snx.logger.info(f"ETH balance: {eth_balance['eth']}")
        snx.logger.info(f"WETH balance: {eth_balance['weth']}")

        # figure out the amounts for each transaction
        spot_swap_amount = round(susd_balance["balance"] * 1e8, 8) / 1e8
        spot_unwrap_amount = spot_swap_amount + susdc_balance
        odos_swap_amount = round(usdc_balance * 1e8, 8) / 1e8 + spot_unwrap_amount
        odos_swap_amount_wei = int(odos_swap_amount * 1e6)

        snx.logger.info(
            f"Trade route: {spot_swap_amount} sUSD -> {spot_unwrap_amount} sUSDC -> {odos_swap_amount} USDC"
        )

        if odos_swap_amount > SWAP_THRESHOLD:
            tx_swap_susd = snx.spot.atomic_order(
                "buy", spot_swap_amount, market_name="sUSDC", submit=True
            )
            receipt_swap_susd = snx.wait(tx_swap_susd)

            # unwrap the sUSDC
            tx_unwrap_susdc = snx.spot.wrap(
                -spot_unwrap_amount, market_name="sUSDC", submit=True
            )
            receipt_unwrap_susdc = snx.wait(tx_unwrap_susdc)

            # prepare the swap tx
            odos_tx_info = assemble_transaction(snx, odos_swap_amount_wei)
            tx_params = odos_tx_info["transaction"]

            # fix swap params
            tx_params["value"] = 0
            tx_params["nonce"] = snx.nonce

            # remove the gas parameter
            del tx_params["gas"]
            snx.logger.info(f"Swap tx: {tx_params}")
            swap_tx = snx.execute_transaction(tx_params)

            swap_receipt = snx.wait(swap_tx)
            snx.logger.info(f"Swap receipt: {swap_receipt['status']}")

        # if balance is above threshold, swap
        eth_balance = snx.get_eth_balance()
        if eth_balance["weth"] > 0.01:
            tx_unwrap_eth = snx.wrap_eth(-eth_balance["weth"], submit=True)
            receipt_unwrap_eth = snx.wait(tx_unwrap_eth)
            snx.logger.info(f"Unwrap ETH receipt: {receipt_unwrap_eth['status']}")
