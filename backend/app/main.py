"""FairClick FastAPI application.

Serves:
  /api/*    - FairClick REST API
  /sites/*  - the five locally hosted simulated websites (+ their form backend)
  /*        - the built React dashboard (frontend/dist), if present
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import BACKEND_DIR, PROJECT_DIR
from .database import init_db
from .routers import api, sim_sites

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="FairClick API", version="1.0.0",
              description="Consumer-rights agent that navigates manipulative interfaces under human control.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api") or not request.url.path.startswith("/sites"):
        response.headers.setdefault("X-Frame-Options", "DENY")
    return response


@app.on_event("startup")
def _startup() -> None:
    init_db()


app.include_router(api.router)
app.include_router(sim_sites.router)
app.mount("/sites", StaticFiles(directory=BACKEND_DIR / "sim_sites", html=True), name="sites")

FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "sites/")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and FRONTEND_DIST.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
