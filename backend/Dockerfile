FROM python:3.11-slim

# System deps (curl for health, CA certs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# IMPORTANT: paths are relative to the build context (./backend)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN edot-bootstrap --action=install --component=python --non-interactive || true

COPY app /app/app

EXPOSE 8000
