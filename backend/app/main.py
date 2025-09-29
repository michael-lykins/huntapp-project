from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import upload, geo
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

app.include_router(upload.router)
app.include_router(geo.router)

@app.get("/health")
def health():
    return {"status": "ok"}
