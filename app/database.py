from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str):
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.get_backend_name() != "sqlite":
        return create_engine(url, pool_pre_ping=True)

    options = {"connect_args": {"check_same_thread": False, "autocommit": False}}
    if url.database in {None, "", ":memory:"}:
        options["poolclass"] = StaticPool
    engine = create_engine(url, **options)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.autocommit = True
        try:
            connection.execute("PRAGMA foreign_keys=ON").close()
        finally:
            connection.autocommit = False

    return engine


def get_db(request: Request):
    with Session(request.app.state.engine) as db:
        yield db


DB = Annotated[Session, Depends(get_db)]


def as_dict(row):
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}
