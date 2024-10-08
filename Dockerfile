# Base image
FROM ghcr.io/astral-sh/uv:0.4.18-debian

RUN apt-get update && apt-get install -y curl clang gcc python3-dev && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements file
COPY uv.lock .
COPY pyproject.toml .
COPY ape-config.yaml .

# Install dependencies
RUN uv python install
RUN uv sync --frozen
ENV PATH="/app/.venv/bin:$PATH"

# Install ape plugins
RUN uv run ape plugins install .

# Copy app source code
COPY . .

# Command to run the service
CMD ["uv", "run", "silverback", "run", "main:app", "--network", "base:sepolia:alchemy", "--runner", "silverback.runner:WebsocketRunner"]
