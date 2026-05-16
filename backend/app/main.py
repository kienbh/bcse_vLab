"""FastAPI application entrypoint."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app import __version__
from app.api.routes import (
    admin,
    auth,
    bookings,
    classes,
    devices,
    events,
    gateway,
    health,
    reset,
    reset_requests,
    sessions,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.gateway_janitor import periodic_sweep


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    logger.info(
        "starting vju-lab-portal-api",
        version=__version__,
        env=settings.ENV,
        debug=settings.DEBUG,
    )
    sweeper_task = asyncio.create_task(periodic_sweep())
    try:
        yield
    finally:
        sweeper_task.cancel()
        try:
            await sweeper_task
        except (asyncio.CancelledError, Exception):
            pass
        logger.info("shutting down vju-lab-portal-api")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="VJU Hardware Lab Portal API",
        version=__version__,
        docs_url="/api/docs" if not settings.is_prod else None,
        redoc_url="/api/redoc" if not settings.is_prod else None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(devices.router, prefix="/api")
    app.include_router(classes.router, prefix="/api")
    app.include_router(classes.teacher_router, prefix="/api")
    app.include_router(bookings.router, prefix="/api")
    app.include_router(gateway.bookings_router, prefix="/api")
    app.include_router(gateway.gateway_router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(reset.router, prefix="/api")
    app.include_router(reset_requests.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "name": "VJU Hardware Lab Portal API",
            "version": __version__,
            "docs": "/api/docs",
        }

    return app


app = create_app()
