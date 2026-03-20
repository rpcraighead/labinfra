# Scribe - Documentation & Audit Logging Agent
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 agent
WORKDIR /app

COPY scribe/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY base.py /app/base.py
COPY scribe/ /app/
USER agent

EXPOSE 8006
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8006/health || exit 1

CMD ["python", "main.py"]
