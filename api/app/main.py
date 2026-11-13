import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.db import init_db
from app.core.security import add_cors
from app.domains.audio.console_router import router as console_router
from app.domains.audio.router import router as audio_router
from app.domains.audio.ws import router as audio_ws_router
from app.domains.auth.router import router as auth_router
from app.domains.connectors.router import router as connectors_router
from app.domains.graph.elements import router as graph_elements_router
from app.domains.graph.lists import router as graph_lists_router
from app.domains.graph.lists import venue_router as graph_lists_venue_router
from app.domains.graph.rigging import router as graph_rigging_router
from app.domains.graph.rigging import venue_router as graph_rigging_venue_router
from app.domains.graph.router import router as graph_router
from app.domains.graph.router import venue_router as graph_router_venue_router
from app.domains.graph.venue_graph import router as graph_venue_router
from app.domains.history.middleware import HistoryMiddleware
from app.domains.history.router import router as history_router
from app.domains.lighting.router import router as lighting_router
from app.domains.netbox.router import public_router as netbox_public_router
from app.domains.netbox.router import router as netbox_router
from app.domains.reports.router import router as reports_router
from app.domains.rigging.router import router as rigging_router
from app.domains.rigging.router import venue_router as rigging_venue_router
from app.domains.settings.router import router as settings_router
from app.domains.share.router import router as share_router
from app.domains.stockwire.router import public_router as stockwire_public_router
from app.domains.stockwire.router import router as stockwire_router
from app.domains.uploads.router import router as uploads_router
from app.domains.venues.router import router as venues_router
from app.domains.video.router import router as video_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    add_cors(app)
    # Records every write request's row changes so it can be undone (see domains/history).
    app.add_middleware(HistoryMiddleware)

    app.include_router(audio_router, prefix="/api/v1")
    app.include_router(console_router, prefix="/api/v1")
    app.include_router(history_router, prefix="/api/v1")
    app.include_router(audio_ws_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(connectors_router, prefix="/api/v1")
    app.include_router(graph_router, prefix="/api/v1")
    app.include_router(graph_router_venue_router, prefix="/api/v1")
    app.include_router(graph_lists_router, prefix="/api/v1")
    app.include_router(graph_venue_router, prefix="/api/v1")
    app.include_router(graph_rigging_venue_router, prefix="/api/v1")
    app.include_router(graph_lists_venue_router, prefix="/api/v1")
    app.include_router(graph_elements_router, prefix="/api/v1")
    app.include_router(graph_rigging_router, prefix="/api/v1")
    app.include_router(lighting_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
    app.include_router(rigging_router, prefix="/api/v1")
    app.include_router(rigging_venue_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")
    app.include_router(share_router, prefix="/api/v1")
    app.include_router(stockwire_router, prefix="/api/v1")
    app.include_router(stockwire_public_router, prefix="/api/v1")
    app.include_router(netbox_router, prefix="/api/v1")
    app.include_router(netbox_public_router, prefix="/api/v1")
    app.include_router(uploads_router, prefix="/api/v1")
    app.include_router(venues_router, prefix="/api/v1")
    app.include_router(video_router, prefix="/api/v1")

    settings = get_settings()
    try:
        os.makedirs(settings.upload_dir, exist_ok=True)
        app.mount("/static", StaticFiles(directory=settings.upload_dir), name="static")
    except OSError:
        # Non-fatal: the upload directory is not writable (e.g. a read-only
        # filesystem in some environments). The upload endpoint still validates
        # and writes, and will report the error if it is actually used.
        pass

    @app.get("/api/v1/health/live")
    async def health_live() -> dict:
        return {"status": "ok"}

    @app.get("/api/v1/health/ready")
    async def health_ready() -> dict:
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=get_settings().app_host,
        port=get_settings().app_port,
        reload=not get_settings().is_production,
    )
