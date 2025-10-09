#!/usr/bin/env bash
set -euo pipefail

: "${ELASTIC_SEARCH_HOST:?Set ELASTIC_SEARCH_HOST}"
: "${ELASTIC_SEARCH_API_KEY:?Set ELASTIC_SEARCH_API_KEY}"

hdr=( -H "Authorization: ApiKey ${ELASTIC_SEARCH_API_KEY}" -H "Content-Type: application/json" )
script_dir="$(cd -- "$(dirname "$0")" >/dev/null 2>&1 && pwd)"

echo "Installing index templates..."
for f in "${script_dir}/templates"/*.json; do
  [ -e "$f" ] || continue
  name=$(basename "$f" .json)
  echo "  -> $name"
  curl -sS -X PUT "${ELASTIC_SEARCH_HOST}/_index_template/${name}" "${hdr[@]}" --data-binary @"$f" >/dev/null
done

echo "Installing pipelines..."
for f in "${script_dir}/pipelines"/*.json; do
  [ -e "$f" ] || continue
  name=$(basename "$f" .json)
  echo "  -> $name"
  curl -sS -X PUT "${ELASTIC_SEARCH_HOST}/_ingest/pipeline/${name}" "${hdr[@]}" --data-binary @"$f" >/dev/null
done

# Optional: Pre-create the data stream (else it will auto-create on first write)
echo "Ensuring data stream exists: metrics-weather-default"
curl -sS -X PUT "${ELASTIC_SEARCH_HOST}/_data_stream/metrics-weather-default" \
  -H "Authorization: ApiKey ${ELASTIC_SEARCH_API_KEY}" || true

echo "Done."
