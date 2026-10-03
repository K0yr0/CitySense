"""CityEcho HTTP API: `uvicorn backend.main:app --reload`.

Routers live in backend/api/; JSON shapes are fixed by docs/ARCHITECTURE.md §6.
Pipelines and fusion are imported lazily by the routers, so importing this
module stays fast and works before the database is reachable.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api import incidents, reports, rides, segments, stats, vehicles
from backend.config import settings

log = logging.getLogger("cityecho")

PHOTOS_DIR = settings.cache_dir / "photos"
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    try:  # release pooled DB connections on shutdown (only if the pool was ever opened)
        from backend import db

        getattr(db, "close_pool", lambda: None)()
    except Exception:
        pass


app = FastAPI(title="CityEcho", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def json_errors(request: Request, call_next):
    """Unhandled errors -> JSON 500 *inside* the CORS middleware, so the browser can read them."""
    try:
        return await call_next(request)
    except Exception as exc:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": f"internal error: {type(exc).__name__}: {exc}"}, status_code=500)


# Added last = outermost, so every response (errors included) gets CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"ok": True}


for module in (rides, reports, segments, incidents, stats, vehicles):
    app.include_router(module.router)

app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")
