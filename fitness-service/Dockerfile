FROM python:3.11-slim

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install curl for the Docker healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8001

# Single worker process per container — we scale by adding CONTAINERS,
# not threads. That is the whole point of the pool architecture.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
