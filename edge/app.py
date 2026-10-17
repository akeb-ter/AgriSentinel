"""
AgriSentinel Main Application Initialization

Mounts static asset directories, registers Web & REST API routes,
and manages server lifespan events for the Smart Crop Probe Stick.
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from edge.database import init_db
from edge.web_app import router as web_router
from edge.probe_controller import probe

logger = logging.getLogger("AgriSentinel-App")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes DBMS schema on startup and closes probe threads on shutdown."""
    logger.info("[Lifespan] Initializing database and probe subsystems...")
    init_db()
    yield
    logger.info("[Lifespan] Shutting down probe hardware and background tasks...")
    probe.shutdown()


app = FastAPI(
    title="AgriSentinel Smart Crop Probe",
    description="AI-Powered Crop Protection System for Smart Pest Detection, Plant Health Assessment, and Pest-Specific Pesticide Recommendation",
    version="2.0.0",
    lifespan=lifespan,
)

# Mount application routes and static assets
app.include_router(web_router)
app.mount("/static", StaticFiles(directory="web/static"), name="static")

