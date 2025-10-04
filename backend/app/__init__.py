import os
import logging
from typing import Any, Dict, Iterable, Optional

try:
    from elasticsearch import Elasticsearch, helpers  # type: ignore
except Exception:
    Elasticsearch = None  # allow import without the library
    helpers = None

log = logging.getLogger("huntapp.services")


class SearchService:
    def index(self, index: str, document: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def index_document(self, index: str, document: Dict[str, Any]) -> Dict[str, Any]:
        return self.index(index, document)

    def bulk(self, actions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        raise NotImplementedError


class NoopSearchService(SearchService):
    def index(self, index: str, document: Dict[str, Any]) -> Dict[str, Any]:
        log.warning("No search backend configured; dropping doc for index=%s", index)
        return {"result": "noop", "_index": index, "_id": None}

    def bulk(self, actions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        log.warning("No search backend configured; dropping bulk actions")
        return {"errors": False, "items": []}


class ElasticSearchService(SearchService):
    def __init__(self) -> None:
        host = os.environ.get("ELASTIC_SEARCH_HOST")
        api_key = os.environ.get("ELASTIC_SEARCH_API_KEY")
        if not host or not api_key:
            raise RuntimeError("ELASTIC_SEARCH_HOST and ELASTIC_SEARCH_API_KEY are required")
        if Elasticsearch is None:
            raise RuntimeError("elasticsearch client library not available")

        self.client = Elasticsearch(hosts=[host], api_key=api_key, request_timeout=30)
        log.info("Initialized ElasticSearchService for %s", host)

    def index(self, index: str, document: Dict[str, Any]) -> Dict[str, Any]:
        return self.client.index(index=index, document=document)

    def index_document(self, index: str, document: Dict[str, Any]) -> Dict[str, Any]:
        return self.index(index, document)

    def bulk(self, actions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        if helpers is None:
            raise RuntimeError("elasticsearch.helpers is not available")
        return helpers.bulk(self.client, actions)


_SERVICE: Optional[SearchService] = None

def get_search() -> SearchService:
    global _SERVICE
    if _SERVICE is not None:
        return _SERVICE

    host = os.environ.get("ELASTIC_SEARCH_HOST")
    api_key = os.environ.get("ELASTIC_SEARCH_API_KEY")
    if host and api_key:
        try:
            _SERVICE = ElasticSearchService()
            return _SERVICE
        except Exception as e:
            log.exception("Failed to init ElasticSearchService: %s", e)

    _SERVICE = NoopSearchService()
    return _SERVICE


def get_search_client() -> "Elasticsearch":
    svc = get_search()
    if isinstance(svc, ElasticSearchService):
        return svc.client
    raise RuntimeError("Elasticsearch client not available (NoopSearchService is active)")
