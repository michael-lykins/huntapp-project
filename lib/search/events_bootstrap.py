from __future__ import annotations
from typing import Optional
from elasticsearch import Elasticsearch

EVENTS_DATA_STREAM = "events"

def bootstrap_events(es: Optional[Elasticsearch] = None) -> None:
    # TODO: add index template / data stream creation if you want
    return

def events_bootstrap(es: Optional[Elasticsearch] = None, redis=None) -> None:
    # TODO: worker-side processing
    return
