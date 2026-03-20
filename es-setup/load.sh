#!/usr/bin/env bash
set -euo pipefail

: "${ELASTIC_SEARCH_HOST:?Set ELASTIC_SEARCH_HOST}"
: "${ELASTIC_SEARCH_API_KEY:?Set ELASTIC_SEARCH_API_KEY}"

hdr=( -H "Authorization: ApiKey ${ELASTIC_SEARCH_API_KEY}" -H "Content-Type: application/json" )
script_dir="$(cd -- "$(dirname "$0")" >/dev/null 2>&1 && pwd)"

# ---- 1. ELSER inference endpoint -------------------------------------------
echo "Creating ELSER inference endpoint (ridgeline-elser)..."
curl -sS -o /dev/null -w "  -> ridgeline-elser: %{http_code}\n" \
  -X PUT "${ELASTIC_SEARCH_HOST}/_inference/sparse_embedding/ridgeline-elser" \
  "${hdr[@]}" \
  -d '{"service":"elser","service_settings":{"num_allocations":1,"num_threads":1}}'

# ---- 2. Index templates -----------------------------------------------------
echo "Installing index templates..."
for f in "${script_dir}/templates"/*.json; do
  [ -e "$f" ] || continue
  name=$(basename "$f" .json)
  echo "  -> $name"
  curl -sS -o /dev/null -w "     status: %{http_code}\n" \
    -X PUT "${ELASTIC_SEARCH_HOST}/_index_template/${name}" "${hdr[@]}" --data-binary @"$f"
done

# ---- 3. Live mapping update for existing tactacam-images index --------------
echo "Patching live tactacam-images mapping (semantic + embedding fields)..."
curl -sS -o /dev/null -w "  -> tactacam-images mapping: %{http_code}\n" \
  -X PUT "${ELASTIC_SEARCH_HOST}/tactacam-images/_mapping" \
  "${hdr[@]}" \
  -d '{
    "properties": {
      "ai_notes_semantic":   { "type": "semantic_text", "inference_id": "ridgeline-elser" },
      "ai_antlers_semantic": { "type": "semantic_text", "inference_id": "ridgeline-elser" },
      "embedding": { "type": "dense_vector", "dims": 512, "index": true, "similarity": "cosine" }
    }
  }'

# ---- 4. Ingest pipelines ----------------------------------------------------
echo "Installing ingest pipelines..."
for f in "${script_dir}/pipelines"/*.json; do
  [ -e "$f" ] || continue
  name=$(basename "$f" .json)
  echo "  -> $name"
  curl -sS -o /dev/null -w "     status: %{http_code}\n" \
    -X PUT "${ELASTIC_SEARCH_HOST}/_ingest/pipeline/${name}" "${hdr[@]}" --data-binary @"$f"
done

# ---- 5. Enrich policy -------------------------------------------------------
echo "Creating camera-metadata enrich policy..."
curl -sS -o /dev/null -w "  -> camera-metadata-enrich: %{http_code}\n" \
  -X PUT "${ELASTIC_SEARCH_HOST}/_enrich/policy/camera-metadata-enrich" \
  "${hdr[@]}" --data-binary @"${script_dir}/enrich/camera-metadata-policy.json"

echo "Executing camera-metadata enrich policy (builds lookup index)..."
curl -sS -o /dev/null -w "  -> execute: %{http_code}\n" \
  -X POST "${ELASTIC_SEARCH_HOST}/_enrich/policy/camera-metadata-enrich/_execute" \
  "${hdr[@]}"

# ---- 6. Transforms ----------------------------------------------------------
echo "Installing transforms..."
for f in "${script_dir}/transforms"/*.json; do
  [ -e "$f" ] || continue
  name=$(basename "$f" .json)
  echo "  -> $name"
  # PUT is idempotent if transform already exists at same config; ignore 409
  http_code=$(curl -sS -o /tmp/transform_resp.json -w "%{http_code}" \
    -X PUT "${ELASTIC_SEARCH_HOST}/_transform/${name}" "${hdr[@]}" --data-binary @"$f")
  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    echo "     created (${http_code}), starting..."
    curl -sS -o /dev/null -w "     start: %{http_code}\n" \
      -X POST "${ELASTIC_SEARCH_HOST}/_transform/${name}/_start" "${hdr[@]}"
  elif [ "$http_code" = "400" ]; then
    # Transform already exists — just ensure it's running
    echo "     already exists, ensuring started..."
    curl -sS -o /dev/null -w "     start: %{http_code}\n" \
      -X POST "${ELASTIC_SEARCH_HOST}/_transform/${name}/_start" "${hdr[@]}" || true
  else
    echo "     status: ${http_code}"
    cat /tmp/transform_resp.json
  fi
done

# ---- 7. Data streams --------------------------------------------------------
echo "Ensuring data stream exists: metrics-weather-default"
curl -sS -o /dev/null -w "  -> metrics-weather-default: %{http_code}\n" \
  -X PUT "${ELASTIC_SEARCH_HOST}/_data_stream/metrics-weather-default" \
  -H "Authorization: ApiKey ${ELASTIC_SEARCH_API_KEY}" || true

echo ""
echo "Done. Next steps:"
echo "  - Re-run the enrich policy execute after cameras sync to keep lookup index fresh:"
echo "    POST ${ELASTIC_SEARCH_HOST}/_enrich/policy/camera-metadata-enrich/_execute"
echo "  - Backfill CLIP embeddings: docker compose exec worker python -m worker_app.jobs.embed_tactacam"
