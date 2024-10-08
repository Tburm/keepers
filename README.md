# Synthetix keepers

This repository contains keeper scripts for the Synthetix system. These keepers are designed to perform various automated tasks such as order settlement, liquidations, and balance management.

## Features

- Flexible deployment across multiple networks (Ethereum, Base, Optimism, Arbitrum)
- Support logic for V3 perps and BFP contracts
- Order settlement for perps markets
- Account flagging and liquidations
- Balance checks and automated swaps using Odos

## Components

1. `main.py`: Main keeper script for V3 systems
1. `main_l1.py`: Main keeper script for BFP system

## Configuration

Create a `.env.{network}` file in the root directory for each of the networks listed in the `docker-compose.yml` file. Adjust the values as needed for your specific setup.

## Run Using Docker

You can run the keepers using docker, by configuring the docker compose figuration as you want and running it:

```bash
# mainnet
docker compose build
docker compose up

# testnet
docker compose -f docker-compose.sepolia.yml build
docker compose -f docker-compose.sepolia.yml up
```

## Run Locally

You can also run the keepers locally using Silverback, a framework for running bots. Use the following command structure:

```bash
# V3 on base sepolia
uv run silverback run main:app --network base:sepolia:alchemy --runner silverback.runner:WebsocketRunner
```

Note that you must have the [uv](https://github.com/astral-sh/uv) package manager installed in order to run this, otherwise you can install the `pyproject.toml` file using your preferred environment and package manager
