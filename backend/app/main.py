from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.upload import router as upload_router
from app.routes.geo import router as geo_router
from app.routes.images import router as images_router
from app.routes.events import router as events_router
from app.observability import setup_logging
import os

setup_logging()

app = FastAPI(title="HuntApp API")

allow_origins = os.getenv("API_CORS_ALLOW_ORIGINS", "http://localhost:3001").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(geo_router)
app.include_router(images_router)
app.include_router(events_router)

@app.get("/health")
def health():
    return {"status": "ok"}
