# Base image
FROM python:3.10

# Create app directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .
COPY ape-config.yaml .

# Install dependencies
RUN python -m venv /env
ENV PATH="/env/bin:$PATH"

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN ape plugins install .

# Copy app source code
COPY . .

# Command to run the service
CMD ["silverback", "run", "main:app", "--network", "optimism:goerli:alchemy", "--runner", "silverback.runner:WebsocketRunner"]
