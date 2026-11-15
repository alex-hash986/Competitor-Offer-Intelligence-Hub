import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.schema import CreateSchema, DropSchema

from app.database import make_engine
from app.main import create_app


@pytest.fixture
def database_url():
    if url := os.getenv("TEST_DATABASE_URL"):
        engine = make_engine(url)
        schema = f"test_{uuid4().hex}"
        try:
            with engine.begin() as connection:
                connection.execute(CreateSchema(schema))
            yield engine.url.update_query_dict(
                {"options": f"-csearch_path={schema}"}
            ).render_as_string(hide_password=False)
        finally:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True, if_exists=True))
            engine.dispose()
    else:
        with TemporaryDirectory(prefix="competitor-intel-") as temp:
            yield f"sqlite:///{(Path(temp) / 'test.db').as_posix()}"


@pytest.fixture
def client(database_url):
    with TestClient(create_app(database_url)) as client:
        yield client
