# lib/services/search.py
import os
from elasticsearch import Elasticsearch
from .elastic_client import get_elasticsearch_client

def _build_client() -> Elasticsearch:
    host = os.environ["ELASTIC_SEARCH_HOST"]
    api_key = os.environ["ELASTIC_SEARCH_API_KEY"]
    return get_elasticsearch_client(host=host, api_key=api_key)

def get_search() -> Elasticsearch:
    """Return an ES client (used anywhere we just call .search())."""
    return _build_client()

def get_search_client() -> Elasticsearch:
    """Return the raw ES client (used for .index(), etc.)."""
    return _build_client()
