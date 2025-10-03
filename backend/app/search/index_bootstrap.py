# app/search/index_bootstrap.py
import os
from elasticsearch import Elasticsearch

INDEX = os.getenv("ES_INDEX", "photos")

MAPPING = {
    "mappings": {
        "dynamic": "false",
        "properties": {
            "bucket":        {"type": "keyword"},
            "key":           {"type": "keyword"},
            "thumb_key":     {"type": "keyword"},
            "capture_time":  {"type": "date"},
            "location":      {"type": "geo_point"},
            "camera_model":  {"type": "keyword"},
            "labels":        {"type": "keyword"},
            "size_bytes":    {"type": "long"}
        }
    }
}

def ensure_index(es: Elasticsearch):
    if not es.indices.exists(index=INDEX):
        es.indices.create(index=INDEX, **MAPPING)
