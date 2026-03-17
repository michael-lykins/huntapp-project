from __future__ import annotations
from fastapi import APIRouter

router = APIRouter()

# TODO: replace with your real store (DB or ES query)
FAKE_WAYPOINTS = [
    {"id": "wp_1", "name": "North Ridge", "lat": 41.12345, "lon": -96.45678},
    {"id": "wp_2", "name": "Creek Bottom", "lat": 41.11890, "lon": -96.46123},
]

@router.get("/waypoints")
def list_waypoints():
    return FAKE_WAYPOINTS
