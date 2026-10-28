from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  loads the table classes so create_all sees them
from app.database import create_db_and_tables
from app.routers import alerts, events, settings, stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="lock-in-twin", lifespan=lifespan)

app.include_router(events.router)
app.include_router(stats.router)
app.include_router(settings.router)
app.include_router(alerts.router)
