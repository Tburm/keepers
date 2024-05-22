import os
import asyncio
from dotenv import load_dotenv
from kwenta import Kwenta

# load the environment variables
load_dotenv()

ADDRESS = os.environ.get("ADDRESS")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
OP_TESTNET_RPC = os.environ.get("OP_TESTNET_RPC")


class Keeper:
    def __init__(self):
        self.kwenta = Kwenta(
            provider_rpc=OP_TESTNET_RPC,
            wallet_address=ADDRESS,
            private_key=PRIVATE_KEY,
            network_id=11155420,
            fast_marketload=False,
        )

    async def process_event(self, event, token_symbol):
        # Extract the required information from the event
        account = event["args"]["account"]

        # Call get_delayed_order and wait for the executable time
        print(f"executing for {account} for token {token_symbol} ")
        await self.kwenta.execute_for_address(token_symbol, account)

    async def monitor_events(self):
        PerpsMarkets = [
            self.kwenta.get_market_contract(token) for token in self.kwenta.token_list
        ]

        event_filters = [
            PerpsMarket.events.DelayedOrderSubmitted.create_filter(fromBlock="latest")
            for PerpsMarket in PerpsMarkets
        ]

        while True:
            print("getting new events")
            for ind, event_filter in enumerate(event_filters):
                events = event_filter.get_new_entries()

                for event in events:
                    asyncio.create_task(
                        self.process_event(event, self.kwenta.token_list[ind])
                    )

            await asyncio.sleep(10)  # Adjust the sleep time as needed

    async def monitor_event_subscription(self):
        topic = self.kwenta.web3.keccak(
            text=f"DelayedOrderSubmitted(address,bool,int256,uint256,uint256,uint256,uint256,uint256,bytes32)"
        ).hex()

        def handle_event(log):
            log_data = self.kwenta.web3.codec.decode_abi(log["topics"], log["data"])
            event = dict(zip(log_data["names"], log_data["args"]))
            token_symbol = self.kwenta.token_list[topic.index(log["topics"][0])]
            asyncio.create_task(self.process_event(event, token_symbol))

        subscription = self.kwenta.web3.eth.subscribe(
            "logs",
            {
                "fromBlock": "latest",
                "topics": [topic],
            },
        )
        while True:
            log_entry = await subscription.__aiter__().__anext__()
            handle_event(log_entry)


async def main():
    keeper = Keeper()
    await keeper.monitor_events()


if __name__ == "__main__":
    asyncio.run(main())
