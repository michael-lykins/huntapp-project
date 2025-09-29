#!/usr/bin/env bash
set -euo pipefail
: "${ELASTIC_SEARCH_HOST:?Set ELASTIC_SEARCH_HOST}"
: "${ELASTIC_SEARCH_API_KEY:?Set ELASTIC_SEARCH_API_KEY}"
hdr=( -H "Authorization: ApiKey ${ELASTIC_SEARCH_API_KEY}" -H "Content-Type: application/json" )
echo "Installing index templates..."
for f in templates/*.json; do
  name=$(basename "$f" .json)
  echo "  -> $name"
  curl -sS -X PUT "$ELASTIC_SEARCH_HOST/_index_template/$name" "${hdr[@]}" --data-binary @"$f" >/dev/null
done
echo "Installing pipelines..."
for f in pipelines/*.json; do
  name=$(basename "$f" .json)
  echo "  -> $name"
  curl -sS -X PUT "$ELASTIC_SEARCH_HOST/_ingest/pipeline/$name" "${hdr[@]}" --data-binary @"$f" >/dev/null
done
echo "Done."
