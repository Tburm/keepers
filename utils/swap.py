import requests
from synthetix import Synthetix

quote_url = "https://api.odos.xyz/sor/quote/v2"
assemble_url = "https://api.odos.xyz/sor/assemble"


def get_quote(snx, amount):
    quote_request_body = {
        "chainId": snx.network_id,
        "inputTokens": [
            {
                "tokenAddress": snx.contracts["USDC"]["address"],
                "amount": f"{amount}",
            }
        ],
        "outputTokens": [
            {
                "tokenAddress": snx.contracts["WETH"]["address"],
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


def assemble_transaction(snx, amount):
    quote = get_quote(snx, amount)

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
