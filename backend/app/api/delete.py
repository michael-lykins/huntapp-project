from typing import List, Literal, Tuple
from fastapi import APIRouter, HTTPException, Request, Depends
from elasticsearch import Elasticsearch, NotFoundError

router = APIRouter()

# Use app-state ES (same as geo/images)
def es_dep(request: Request) -> Elasticsearch:
    es = getattr(request.app.state, "es", None)
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch not initialized")
    return es

PRIMARY_INDEX = {
    "waypoint": "waypoints-v1",
    "track": "tracks-v1",
    "image": "images-v1",
    "trailcam": "trailcams-v1",
}
Entity = Literal["waypoint", "track", "image", "trailcam"]


def _delete_primary(es: Elasticsearch, entity: Entity, entity_id: str) -> None:
    idx = PRIMARY_INDEX[entity]
    try:
        es.delete(index=idx, id=entity_id, refresh=True)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"{entity} {entity_id} not found")


def _delete_related_docs(es: Elasticsearch, index: str, field: str, value: str) -> None:
    q = {"query": {"term": {field: value}}}
    es.delete_by_query(index=index, body=q, refresh=True, conflicts="proceed")


def _cascade_delete(es: Elasticsearch, entity: Entity, entity_id: str) -> None:
    relations: List[Tuple[str, str]] = []
    if entity == "waypoint":
        # Image docs store waypoint_id (and optionally nested waypoint) for cascade
        relations.extend([("images-v1", "waypoint_id"), ("events", "entity_id")])
    elif entity == "trailcam":
        relations.extend([("images-v1", "trailcam.id"), ("events", "entity_id")])
    elif entity == "image":
        relations.extend([("events", "entity_id")])
    for idx, fld in relations:
        _delete_related_docs(es, idx, fld, entity_id)


@router.delete("/delete/{entity}/{entity_id}")
def hard_delete(
    entity: Entity,
    entity_id: str,
    es: Elasticsearch = Depends(es_dep),
):
    if entity not in PRIMARY_INDEX:
        raise HTTPException(status_code=400, detail="Unsupported entity")
    _cascade_delete(es, entity, entity_id)
    _delete_primary(es, entity, entity_id)
    return {"ok": True, "entity": entity, "id": entity_id, "mode": "hard"}
