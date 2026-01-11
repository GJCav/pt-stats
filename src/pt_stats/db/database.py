import os
import peewee
from peewee import SqliteDatabase, DatabaseProxy

conn = DatabaseProxy()


def initialize(db_path: str | None = None):
    if db_path is None:
        db_path = ":memory:"

    if conn.obj is None:
        conn.initialize(
            SqliteDatabase(
                db_path,
                pragmas={
                    "journal_mode": "wal",
                },
                timeout=30.0,
            )
        )
    else:
        raise RuntimeError("Database connection is already initialized.")


def close():
    if not conn.is_closed():
        conn.close()


class DatabaseModel(peewee.Model):
    class Meta:
        database = conn
