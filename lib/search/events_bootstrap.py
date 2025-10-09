from __future__ import annotations
from typing import Final, Optional, Any
from elasticsearch import Elasticsearch

EVENTS_DATA_STREAM: Final = "events"

def bootstrap_events(es_client: Any) -> None:
    # TODO: add index template / data stream creation if you want
    pass


