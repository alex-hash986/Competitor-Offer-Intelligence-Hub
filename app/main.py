from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import VERSION, settings
from app.database import Base, make_engine
from app.routers import analytics, competitors, exports, health, snapshots
from app.seed import seed_demo_data


def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        engine = make_engine(database_url or settings.database_url)
        application.state.engine = engine
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as db, db.begin():
                seed_demo_data(db)
            yield
        finally:
            engine.dispose()

    application = FastAPI(title="Competitor & Offer Intelligence Hub", version=VERSION, lifespan=lifespan)
    for router in (health.router, competitors.router, snapshots.router, analytics.router, exports.router):
        application.include_router(router, prefix="/api")
    application.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[1] / "static",
                                       html=True), name="static")
    return application


app = create_app()
