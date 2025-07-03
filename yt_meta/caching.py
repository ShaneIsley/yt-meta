import logging
import pickle
import sqlite3
import time
from collections.abc import MutableMapping
from pathlib import Path

logger = logging.getLogger(__name__)


class DummyCache(MutableMapping):
    """A dummy cache that stores nothing. Used when caching is disabled."""

    def __getitem__(self, key):
        raise KeyError(key)

    def __setitem__(self, key, value):
        pass

    def __delitem__(self, key):
        pass

    def __iter__(self):
        return iter([])

    def __len__(self):
        return 0


class SQLiteCache(MutableMapping):
    """
    A cache that uses SQLite as a backend.
    """

    def __init__(self, path=".my_yt_meta_cache/cache.db", ttl_seconds=86400):
        self.path = path
        self.ttl_seconds = ttl_seconds
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value BLOB, timestamp REAL)"
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._conn.close()

    def __getitem__(self, key):
        cursor = self._conn.execute(
            "SELECT value, timestamp FROM cache WHERE key = ?", (key,)
        )
        result = cursor.fetchone()
        if result is None:
            raise KeyError(key)
        value, timestamp = result
        if timestamp < time.time() - self.ttl_seconds:
            self.__delitem__(key)
            raise KeyError(key)
        return pickle.loads(value)

    def __setitem__(self, key, value):
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, ?)",
            (key, pickle.dumps(value), time.time()),
        )
        self._conn.commit()

    def __delitem__(self, key):
        self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        self._conn.commit()

    def __iter__(self):
        cursor = self._conn.execute("SELECT key FROM cache")
        return (row[0] for row in cursor)

    def __len__(self):
        cursor = self._conn.execute("SELECT COUNT(*) FROM cache")
        return cursor.fetchone()[0]
