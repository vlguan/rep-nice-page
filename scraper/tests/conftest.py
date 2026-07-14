import os
import pathlib

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")

requires_db = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn():
    import psycopg

    connection = psycopg.connect(TEST_DB, autocommit=True)
    connection.execute("DROP SCHEMA public CASCADE")
    connection.execute("CREATE SCHEMA public")
    root = pathlib.Path(__file__).resolve().parents[2]
    for sql_file in sorted((root / "web" / "drizzle").glob("*.sql")):
        for stmt in sql_file.read_text().split("--> statement-breakpoint"):
            if stmt.strip():
                connection.execute(stmt)
    yield connection
    connection.close()
