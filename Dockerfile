FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements file
COPY uv.lock .
COPY pyproject.toml .
COPY ape-config.yaml .

# Install dependencies
RUN uv sync --frozen
RUN uv run ape plugins install .

# Copy app source code
COPY . .

# Command to run the service
CMD ["uv", "run", "silverback", "run", "main:app", "--network", "base:sepolia:alchemy", "--runner", "silverback.runner:WebsocketRunner"]
