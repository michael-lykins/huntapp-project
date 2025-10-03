from __future__ import annotations
import os
from functools import lru_cache
from elasticsearch import Elasticsearch

@lru_cache(maxsize=1)
def get_search_client() -> Elasticsearch:
    host = os.getenv("ELASTIC_SEARCH_HOST")
    api_key = os.getenv("ELASTIC_SEARCH_API_KEY")
    if not host or not api_key:
        raise RuntimeError("Missing ELASTIC_SEARCH_HOST or ELASTIC_SEARCH_API_KEY")
    # 'hosts' accepts either a string or list of strings
    es = Elasticsearch(hosts=[host], api_key=api_key)
    return es

def ensure_index(es: Elasticsearch, index: str, mappings: dict | None = None) -> None:
    if es.indices.exists(index=index):
        return
    es.indices.create(index=index, mappings=mappings or {})
