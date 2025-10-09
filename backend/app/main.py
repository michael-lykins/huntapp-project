# backend/app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import events
from lib.search.events_bootstrap import bootstrap_events, EVENTS_DATA_STREAM
from lib.models.event import Event
from lib.services.search import get_elasticsearch_client

import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3030"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount event routes under /api/events
app.include_router(events.router, prefix="/api")

es = get_elasticsearch_client(
    host=os.environ["ELASTIC_SEARCH_HOST"],
    api_key=os.environ["ELASTIC_SEARCH_API_KEY"]
)

@app.on_event("startup")
def on_startup():
    bootstrap_events()
