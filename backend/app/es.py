import os
from elasticsearch import Elasticsearch
def get_search_client() -> Elasticsearch:
    host = os.getenv("ELASTIC_SEARCH_HOST")
    api_key = os.getenv("ELASTIC_SEARCH_API_KEY")
    if not host or not api_key:
        raise RuntimeError("Set ELASTIC_SEARCH_HOST and ELASTIC_SEARCH_API_KEY")
    return Elasticsearch(hosts=[host], api_key=api_key, request_timeout=30)
