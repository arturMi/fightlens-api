"""Small helpers for the PostgreSQL database."""

from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from fightlens import config

SCHEMA = (Path(__file__).parent / "schema.sql").read_text()


def connect():
    """Open a connection. Rows come back as dicts. Each statement is saved right away,
    unless it runs inside `with conn.transaction():`."""
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row, autocommit=True)


def create_tables(conn):
    conn.execute(SCHEMA)


def query(sql, params=None):
    """Run a query and return all rows."""
    with connect() as conn:
        return conn.execute(sql, params).fetchall()
