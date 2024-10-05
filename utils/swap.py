import requests
from synthetix import Synthetix

address_url = "https://api.odos.xyz/info/router/v2"
quote_url = "https://api.odos.xyz/sor/quote/v2"
assemble_url = "https://api.odos.xyz/sor/assemble"


# approvals
def base_approvals(snx):
    # get odos address
    address_response = requests.get(f"{address_url}/{snx.network_id}")
    address_json = address_response.json()
    odos_address = address_json["address"]

    # contracts
    usdc_contract = snx.contracts["USDC"]["contract"]

    # check allowances
    usdc_allowance = (
        usdc_contract.functions.allowance(snx.address, odos_address).call() / 1e18
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
            snx.contracts["system"]["USDProxy"]["address"],
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
        approve_tx = snx.approve(usdc_contract.address, odos_address, submit=True)
        approve_receipt = snx.wait(approve_tx)


def arbitrum_approvals(snx):
    # get odos address
    address_response = requests.get(f"{address_url}/{snx.network_id}")
    address_json = address_response.json()
    odos_address = address_json["address"]

    # contracts
    susd_contract = snx.contracts["system"]["USDProxy"]["contract"]
    weth_contract = snx.contracts["WETH"]["contract"]

    # check allowances
    susd_allowance = (
        susd_contract.functions.allowance(snx.address, odos_address).call() / 1e18
    )

    # approve sUSD to odos
    if susd_allowance == 0:
        tx_approve_susd = snx.approve(
            snx.contracts["system"]["USDProxy"]["address"],
            odos_address,
            submit=True,
        )
        receipt_approve_susd = snx.wait(tx_approve_susd)


def get_quote(snx, amount, token_in, token_out):
    quote_request_body = {
        "chainId": snx.network_id,
        "inputTokens": [
            {
                "tokenAddress": token_in,
                "amount": f"{amount}",
            }
        ],
        "outputTokens": [
            {
                "tokenAddress": token_out,
                "proportion": 1,
            }
        ],
        "slippageLimitPercent": 0.3,
        "userAddr": snx.address,
        "disableRFQs": True,
        "compact": True,
    }

    response = requests.post(
        quote_url, headers={"Content-Type": "application/json"}, json=quote_request_body
    )

    if response.status_code == 200:
        quote = response.json()
        return quote
    else:
        print(f"Error in Quote: {response.json()}")
        raise Exception("Error in Quote")


def build_swap(snx, amount_in, token_in, token_out):
    """
    Build a swap transaction.

    :param amount_in: amount of token in, in wei
    :param token_in: token in address
    :param token_out: token out address

    :return: transaction
    :rtype: dict
    """
    quote = get_quote(snx, amount_in, token_in, token_out)
    assemble_request_body = {
        "userAddr": snx.address,
        "pathId": quote["pathId"],
        "simulate": True,
    }

    response = requests.post(
        assemble_url,
        headers={"Content-Type": "application/json"},
        json=assemble_request_body,
    )

    if response.status_code == 200:
        assembled_transaction = response.json()
        return assembled_transaction
    else:
        print(f"Error in Transaction Assembly: {response.json()}")
        raise Exception("Error in Transaction Assembly")


def execute_base_swap(snx, swap_threshold):
    """Swaps sUSD -> sUSDC -> USDC -> WETH -> ETH"""
    # contracts
    weth_contract = snx.contracts["WETH"]["contract"]
    usdc_contract = snx.contracts["USDC"]["contract"]
    susdc_contract = snx.spot.markets_by_name["sUSDC"]["contract"]
    susd_contract = snx.contracts["system"]["USDProxy"]["contract"]

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

    if odos_swap_amount > swap_threshold:
        # check approvals
        base_approvals(snx)

        if spot_swap_amount > 0:
            tx_swap_susd = snx.spot.atomic_order(
                "buy", spot_swap_amount, market_name="sUSDC", submit=True
            )
            receipt_swap_susd = snx.wait(tx_swap_susd)
            assert receipt_swap_susd["status"] == 1

        # unwrap the sUSDC
        if spot_unwrap_amount > 0:
            tx_unwrap_susdc = snx.spot.wrap(
                -spot_unwrap_amount, market_name="sUSDC", submit=True
            )
            receipt_unwrap_susdc = snx.wait(tx_unwrap_susdc)
            assert receipt_unwrap_susdc["status"] == 1

        # prepare the swap tx
        odos_tx_info = build_swap(
            snx,
            odos_swap_amount_wei,
            usdc_contract.address,
            weth_contract.address,
        )
        tx_params = odos_tx_info["transaction"]

        # fix swap params
        tx_params["value"] = 0
        tx_params["nonce"] = snx.nonce

        # remove the gas parameter
        del tx_params["gas"]
        swap_tx = snx.execute_transaction(tx_params)

        swap_receipt = snx.wait(swap_tx)
        snx.logger.info(f"Swap receipt: {swap_receipt['status']}")

    # if balance is above threshold, swap
    eth_balance = snx.get_eth_balance()
    if eth_balance["weth"] > 0.01:
        unwrap_amount = -int(eth_balance["weth"] * 1e8) / 1e8

        tx_unwrap_eth = snx.wrap_eth(unwrap_amount, submit=True)
        receipt_unwrap_eth = snx.wait(tx_unwrap_eth)
        snx.logger.info(f"Unwrap ETH receipt: {receipt_unwrap_eth['status']}")


def execute_arbitrum_swap(snx, swap_threshold):
    """Swaps sUSD -> WETH -> ETH"""
    # contracts
    weth_contract = snx.contracts["WETH"]["contract"]
    susd_contract = snx.contracts["system"]["USDProxy"]["contract"]

    # get sUSD balance
    susd_balance = snx.get_susd_balance()
    eth_balance = snx.get_eth_balance()

    snx.logger.info(f"sUSD balance: {susd_balance}")
    snx.logger.info(f"ETH balance: {eth_balance['eth']}")
    snx.logger.info(f"WETH balance: {eth_balance['weth']}")

    # figure out the amounts for each transaction
    swap_amount = round(susd_balance["balance"] * 1e8, 8) / 1e8
    swap_amount_wei = int(swap_amount * 1e18)

    snx.logger.info(f"Trade route: {swap_amount} sUSD -> WETH")
    if swap_amount > swap_threshold:
        # do approvals
        arbitrum_approvals(snx)

        # prepare the swap tx
        odos_tx_info = build_swap(
            snx,
            swap_amount_wei,
            susd_contract.address,
            weth_contract.address,
        )
        tx_params = odos_tx_info["transaction"]

        # fix swap params
        tx_params["value"] = 0
        tx_params["nonce"] = snx.nonce

        # remove the gas parameter
        del tx_params["gas"]
        swap_tx = snx.execute_transaction(tx_params)

        swap_receipt = snx.wait(swap_tx)
        snx.logger.info(f"Swap receipt: {swap_receipt['status']}")

    # if balance is above threshold, swap
    eth_balance = snx.get_eth_balance()
    if eth_balance["weth"] > 0.01:
        unwrap_amount = -int(eth_balance["weth"] * 1e8) / 1e8

        tx_unwrap_eth = snx.wrap_eth(unwrap_amount, submit=True)
        receipt_unwrap_eth = snx.wait(tx_unwrap_eth)
        snx.logger.info(f"Unwrap ETH receipt: {receipt_unwrap_eth['status']}")
