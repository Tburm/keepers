import time
from synthetix.utils.multicall import multicall_erc7412
from synthetix.utils import wei_to_ether

MARKET_ID = 3


def settle_perps_order(snx, order_committed_event, settle_delay=0):
    account_id = order_committed_event["accountId"]
    market_id = order_committed_event["marketId"]
    market_name = snx.perps.markets_by_id[market_id]["market_name"]

    # add a delay
    snx.logger.info(f"{market_name} Order committed by {account_id}")

    if settle_delay > 0:
        time.sleep(settle_delay)

    order = snx.perps.get_order(account_id)
    if order["size_delta"] > 0 and order["is_stale"] == False:
        snx.logger.info(f"Settling {market_name} order committed by {account_id}")
        order_settlement_tx = snx.perps.settle_order(
            account_id, market_id=MARKET_ID, submit=False
        )

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


def get_active_accounts(snx):
    """Fetch a list of accounts that have some collateral and have open positions"""
    account_proxy = snx.perps.account_proxy
    market_proxy = snx.perps.market_proxy

    # get the total number of accounts
    total_supply = account_proxy.functions.totalSupply().call()

    # fetch the account ids
    account_ids = []
    supply_chunks = [
        range(x, min(x + 500, total_supply)) for x in range(0, total_supply, 500)
    ]
    for supply_chunk in supply_chunks:
        accounts = multicall_erc7412(snx, account_proxy, "tokenByIndex", supply_chunk)
        account_ids.extend(accounts)

    # check those accounts margin requirements
    digests = []
    margin_chunks = [
        account_ids[x : min(x + 500, total_supply)] for x in range(0, total_supply, 500)
    ]
    for margin_chunk in margin_chunks:
        fn_inputs = [(account_id, MARKET_ID) for account_id in margin_chunk]
        chunk_digests = multicall_erc7412(
            snx, market_proxy, "getAccountDigest", fn_inputs
        )

        digests.extend(chunk_digests)

    # filter accounts without a margin requirement
    # this eliminates accounts that have no open positions or small amounts of collateral
    account_infos = zip(account_ids, digests)
    active_accounts = [
        account[0] for account in account_infos if wei_to_ether(account[1][1]) >= 1
    ]
    snx.logger.info(
        f"Updating active accounts list with {len(active_accounts)} accounts"
    )
    return active_accounts


def get_liquidatable_accounts(snx, account_ids):
    # break it into chunks
    chunks = [account_ids[x : x + 500] for x in range(0, len(account_ids), 500)]

    all_liq_accounts = []
    for chunk in chunks:
        fn_inputs = [(account_id, MARKET_ID) for account_id in chunk]
        # check if the account can be liquidated
        # TODO: check margin liquidation as well
        is_position_liquidatables = multicall_erc7412(
            snx, snx.perps.market_proxy, "isPositionLiquidatable", fn_inputs
        )
        can_liquidates = zip(chunk, is_position_liquidatables)

        liq_accounts = [
            can_liquidate[0] for can_liquidate in can_liquidates if can_liquidate[1]
        ]
        all_liq_accounts.extend(liq_accounts)

    snx.logger.info(f"Found {len(all_liq_accounts)} liquidatable accounts")
    return all_liq_accounts


def liquidate_accounts(snx, liquidatable_accounts):
    for account_id in liquidatable_accounts:
        snx.logger.info(f"Liquidating account {account_id}")
        try:
            # TODO: Check if the account is already flagged
            flag_tx = snx.perps.flag(
                account_id=account_id, market_id=MARKET_ID, submit=True
            )
            flag_receipt = snx.wait(flag_tx)
            assert flag_receipt["status"] == 1

            # TODO: choose the type of liquidation
            liquidate_tx_params = snx.perps.liquidate(
                account_id=account_id, market_id=MARKET_ID, submit=False
            )

            liquidate_tx_params = snx.perps.liquidate(account, submit=False)

            # double the base fee
            liquidate_tx_params["maxFeePerGas"] = (
                liquidate_tx_params["maxFeePerGas"] * 2
            )

            liquidate_tx = snx.execute_transaction(liquidate_tx_params)
            liquidate_receipt = snx.wait(liquidate_tx)
            assert liquidate_receipt["status"] == 1
        except Exception as e:
            snx.logger.error(f"Error liquidating account {account_id}: {e}")
