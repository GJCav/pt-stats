import os
import peewee
from peewee import (
    Model, SqliteDatabase, CompositeKey, DatabaseProxy,
    Check
)

DB_PATH = os.getenv("DB_PATH") or "data/pt-stats.db"

conn = SqliteDatabase(DB_PATH, pragmas={
    'journal_mode': 'wal',
})


def connect():
    if conn.is_closed():
        conn.connect()


def close():
    if not conn.is_closed():
        conn.close()
