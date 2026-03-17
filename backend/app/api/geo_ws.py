# backend/app/api/geo_ws.py
from __future__ import annotations
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set
import asyncio
import logging

router = APIRouter()
log = logging.getLogger("geo_ws")

_connections: Set[WebSocket] = set()

def ws_connection_count() -> int:
    return len(_connections)

async def _broadcast(payload: Dict):
    dead = []
    for ws in list(_connections):
        try:
            await ws.send_json(payload)
        except Exception as e:
            log.warning("WS send failed: %s", e)
            dead.append(ws)
    for ws in dead:
        _connections.discard(ws)

@router.websocket("/ws")
async def geo_ws(ws: WebSocket):
    await ws.accept()
    _connections.add(ws)
    log.info("WS connected. total=%d", len(_connections))

    # greet & keepalive
    try:
        await ws.send_json({"type": "hello", "ok": True})
    except Exception:
        pass

    async def keepalive():
        try:
            while True:
                await asyncio.sleep(20)
                await ws.send_json({"type": "ping"})
        except Exception:
            pass

    ka = asyncio.create_task(keepalive())

    try:
        while True:
            # optional: read to detect client liveness
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ka.cancel()
        _connections.discard(ws)
        log.info("WS disconnected. total=%d", len(_connections))

async def broadcast_geo_refresh():
    await _broadcast({"type": "geo_refresh"})
