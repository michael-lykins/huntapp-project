from .config import SearchConfig, BlobConfig
from .search_base import Search
from .search_elastic import ElasticSearchService
from .blob_base import Blob
from .blob_s3 import S3Blob

_search_singleton: Search | None = None
_blob_singleton: Blob | None = None

def get_search() -> Search:
    global _search_singleton
    if _search_singleton is None:
        sc = SearchConfig()
        if sc.provider == "elastic":
            _search_singleton = ElasticSearchService(sc)
        else:
            raise NotImplementedError(f"Unknown SEARCH_PROVIDER: {sc.provider}")
    return _search_singleton

def get_blob() -> Blob:
    global _blob_singleton
    if _blob_singleton is None:
        bc = BlobConfig()
        if bc.provider == "s3":
            _blob_singleton = S3Blob(bc)
        else:
            raise NotImplementedError(f"Unknown BLOB_PROVIDER: {bc.provider}")
    return _blob_singleton
