# HuntApp

Local dev:
```bash
cp .env.example .env   # fill in Elastic creds
docker compose up -d --build
curl http://localhost:8000/health
# Collector metrics:
curl -s localhost:8888/metrics | head
