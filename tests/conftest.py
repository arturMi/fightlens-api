"""The tests need PostgreSQL and Redis: `docker compose up -d db redis`.

They use their own database (fightlens_test), Redis database 1 and the small made-up
dataset in tests/data.
"""

import json
import os
from pathlib import Path

import psycopg
import pytest
import redis

os.environ.setdefault(
    "DATABASE_URL", "postgresql://fightlens:fightlens@localhost:5432/fightlens_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("DATASET_URL", str(Path(__file__).parent / "data"))
os.environ.setdefault("IMPORT_TOKEN", "test-token")


@pytest.fixture(scope="session")
def client():
    """An API client. The test data is imported once into an empty database."""
    from fastapi.testclient import TestClient

    from fightlens import config, importer
    from fightlens.main import app

    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS fights, fighters, events CASCADE")
    redis.Redis.from_url(config.REDIS_URL).flushdb()
    importer.run()

    with TestClient(app) as client:
        yield client


@pytest.fixture
def sent_fights():
    """Returns a function that reads the fights from the Redis Stream."""
    from fightlens import config

    stream = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    return lambda: [json.loads(entry["fight"]) for _, entry in stream.xrange(config.STREAM)]
