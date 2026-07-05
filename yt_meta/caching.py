import json
import logging
import sqlite3
import threading
import time
from collections.abc import MutableMapping
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Pickle protocol marker byte (PROTO opcode = 0x80, present in pickle
# protocols 2+, which covers all output from Python's default pickling
# since 2.x). Used to detect pre-0.5.0 cache files written by the prior
# pickle-based SQLiteCache and refuse to deserialize them — closing the
# RCE vector that pickle.loads on a tampered cache file would open.
_LEGACY_PICKLE_MARKER = b"\x80"


def _json_default(obj):
    """M-a: explicit, revivable encoding for the non-JSON types the
    cache actually holds (datetime/date, e.g. publish_date). The
    previous ``default=str`` fallback silently changed value types on
    the read side — a cache HIT returned publish_date as a string while
    a MISS returned datetime. Anything else raises at WRITE time (R7:
    no silent serialization fallbacks). datetime is checked before date
    (it's a date subclass)."""
    if isinstance(obj, datetime):
        return {"__yt_meta_type__": "datetime", "value": obj.isoformat()}
    if isinstance(obj, date):
        return {"__yt_meta_type__": "date", "value": obj.isoformat()}
    raise TypeError(
        f"Object of type {type(obj).__name__} is not cacheable by "
        f"SQLiteCache (JSON + datetime/date only)"
    )


def _json_object_hook(d):
    """Revive values encoded by ``_json_default``."""
    tag = d.get("__yt_meta_type__")
    if tag == "datetime":
        return datetime.fromisoformat(d["value"])
    if tag == "date":
        return date.fromisoformat(d["value"])
    return d


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

    def close(self) -> None:
        """No-op — there's nothing to release. Present so callers can
        treat any cache the same way (YtMeta.close() calls cache.close()
        unconditionally).
        """
        pass


class SQLiteCache(MutableMapping):
    """
    A cache that uses SQLite as a backend.
    """

    def __init__(self, path=".my_yt_meta_cache/cache.db", ttl_seconds=86400):
        self.path = path
        self.ttl_seconds = ttl_seconds
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False lets a single SQLiteCache be shared
        # across threads (ThreadPoolExecutor, FastAPI handlers, off-thread
        # generator consumption). All DB operations are serialized through
        # self._lock to make that safe.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        # WAL gives concurrent readers + a single writer without each
        # commit blocking readers (the default 'delete' mode does).
        # synchronous=NORMAL is the standard pairing with WAL — durable
        # across crashes, faster than FULL.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value BLOB, timestamp REAL)"
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self) -> None:
        """Close the underlying SQLite connection. Idempotent —
        sqlite3.Connection.close() on an already-closed connection is
        a no-op.
        """
        with self._lock:
            self._conn.close()

    def __getitem__(self, key):
        with self._lock:
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
        if value[:1] == _LEGACY_PICKLE_MARKER:
            raise ValueError(
                f"yt-meta 0.5 changed the on-disk cache format from "
                f"pickle to json (CVE-class fix). The cache file at "
                f"{self.path!r} was written by an older version. Delete "
                f"the file (or its containing directory) to let yt-meta "
                f"rebuild the cache, or downgrade to yt-meta<0.5 if you "
                f"need to keep using the existing data."
            )
        return json.loads(value.decode("utf-8"), object_hook=_json_object_hook)

    def __setitem__(self, key, value):
        encoded = json.dumps(value, default=_json_default).encode("utf-8")
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, ?)",
                (key, encoded, time.time()),
            )
            self._conn.commit()

    def __delitem__(self, key):
        with self._lock:
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()

    def __iter__(self):
        with self._lock:
            cursor = self._conn.execute("SELECT key FROM cache")
            return (row[0] for row in cursor.fetchall())

    def __len__(self):
        with self._lock:
            cursor = self._conn.execute("SELECT COUNT(*) FROM cache")
            return cursor.fetchone()[0]
