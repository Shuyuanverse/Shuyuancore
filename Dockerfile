FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY . .

RUN useradd -m -u 1000 shuyuancore
USER shuyuancore

EXPOSE 8005

CMD ["uvicorn", "src.gateway.api_server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8005"]