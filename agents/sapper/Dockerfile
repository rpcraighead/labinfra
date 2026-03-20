# Sapper - Network/Firewall Agent
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    openssh-client \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 agent
WORKDIR /app

COPY sapper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY base.py /app/base.py
COPY sapper/ /app/
USER agent

EXPOSE 8004
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

CMD ["python", "main.py"]
