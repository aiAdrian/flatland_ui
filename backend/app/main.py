from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import sessions, websockets, overrides, hmi, policies

app = FastAPI(
    title="Flatland Dispatcher API",
    description="Human-in-the-Loop Dispatcher fuer Flatland Bahnsimulation",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/session", tags=["sessions"])
app.include_router(overrides.router, prefix="/session", tags=["overrides"])
app.include_router(websockets.router, tags=["realtime"])
app.include_router(hmi.router, prefix="/session", tags=["hmi"])
app.include_router(policies.router, tags=["policies"])


@app.get("/")
def root():
    return {
        "name": "Flatland Dispatcher API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
