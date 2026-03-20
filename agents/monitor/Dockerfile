# Monitor - Observability & Anomaly Detection Agent
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 agent
WORKDIR /app

COPY monitor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY base.py /app/base.py
COPY monitor/ /app/
USER agent

EXPOSE 8005
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8005/health || exit 1

CMD ["python", "main.py"]
