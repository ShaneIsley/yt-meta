import json
import sqlite3
import time
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_mock_html
from yt_meta import YtMeta
from yt_meta.caching import SQLiteCache


def test_h7_sqlitecache_stores_json_blobs_not_pickle(tmp_path):
    """REGRESSION (H7): SQLiteCache previously used pickle.{dumps,loads},
    creating an RCE vector on tampered cache files
    (.my_yt_meta_cache/cache.db). Switching to json closes the vector
    because json.loads cannot execute arbitrary code. Verify the on-disk
    blob is valid UTF-8 JSON and does not start with the pickle protocol
    marker byte (0x80).
    """
    cache_file = tmp_path / "cache.db"
    cache = SQLiteCache(path=str(cache_file))
    cache["k"] = {"hello": "world", "n": 42}

    conn = sqlite3.connect(str(cache_file))
    raw = conn.execute("SELECT value FROM cache WHERE key='k'").fetchone()[0]
    conn.close()

    assert raw[:1] != b"\x80", "cache value still looks like pickle (H7 RCE)"
    assert json.loads(raw.decode("utf-8")) == {"hello": "world", "n": 42}


def test_h7_caching_module_does_not_import_pickle():
    """REGRESSION (H7): defense in depth — ensure pickle is no longer
    imported in caching.py so it cannot accidentally creep back in.
    """
    import yt_meta.caching as caching_mod

    assert "pickle" not in vars(caching_mod), (
        "caching.py should not import pickle (H7 RCE vector)"
    )


def test_h7_legacy_pickle_format_raises_migration_error(tmp_path):
    """REGRESSION (H7): on first read of a v0.4-era cache file (pickle
    blobs), raise a clean ValueError that tells the user to delete the
    file. Detect-and-refuse migration — no silent rebuild that might
    hide a schema problem.
    """
    import pickle  # only in the test, to construct the legacy blob

    cache_file = tmp_path / "cache.db"
    conn = sqlite3.connect(str(cache_file))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache "
        "(key TEXT PRIMARY KEY, value BLOB, timestamp REAL)"
    )
    legacy_value = pickle.dumps({"hello": "world"})
    conn.execute(
        "INSERT INTO cache VALUES (?, ?, ?)", ("k", legacy_value, time.time())
    )
    conn.commit()
    conn.close()

    cache = SQLiteCache(path=str(cache_file))
    with pytest.raises(ValueError, match=r"[Dd]elete the file"):
        cache["k"]


def test_h7_tuple_roundtrips_as_list(tmp_path):
    """REGRESSION (H7): JSON has no tuple type. Tuples round-trip as
    lists. All current callers either unpack (works on lists) or index
    (works on lists), so this is the right trade-off vs a custom
    type-marker encoder. Documented behavior of the format change.
    """
    cache_file = tmp_path / "cache.db"
    cache = SQLiteCache(path=str(cache_file))
    cache["k"] = (1, 2, "three")
    assert cache["k"] == [1, 2, "three"]


def test_h8_sqlitecache_usable_from_another_thread(tmp_path):
    """REGRESSION (H8): sqlite3.connect defaults to check_same_thread=True,
    so a single YtMeta shared across threads (ThreadPoolExecutor, FastAPI
    request handlers, off-thread generator consumption) raised
    ProgrammingError on the second thread's first cache touch. Open with
    check_same_thread=False so a single SQLiteCache survives use from
    any thread.
    """
    import threading

    cache_file = tmp_path / "cache.db"
    cache = SQLiteCache(path=str(cache_file))
    cache["from_main"] = "main_value"

    captured: dict = {}
    err: list = []

    def worker():
        try:
            cache["from_thread"] = "thread_value"
            captured["read_back"] = cache["from_main"]
        except Exception as e:
            err.append(e)

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=5)

    assert not err, f"thread raised: {err!r}"
    assert captured["read_back"] == "main_value"
    assert cache["from_thread"] == "thread_value"


def test_h8_concurrent_writes_do_not_corrupt_cache(tmp_path):
    """REGRESSION (H8): under concurrent writes from multiple threads,
    interleaved sqlite3 INSERTs could fail or lose entries without a
    serializing lock. The SQLiteCache now holds a threading.Lock around
    all DB operations so concurrent generators (e.g. multiple
    get_channel_videos pages running in parallel) cannot collide.
    """
    import threading

    cache_file = tmp_path / "cache.db"
    cache = SQLiteCache(path=str(cache_file))

    N_THREADS = 8
    PER_THREAD = 25
    errs: list = []

    def writer(thread_id: int):
        try:
            for i in range(PER_THREAD):
                cache[f"t{thread_id}_k{i}"] = {"tid": thread_id, "i": i}
        except Exception as e:
            errs.append(e)

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errs, f"concurrent writes raised: {errs!r}"
    assert len(cache) == N_THREADS * PER_THREAD


def test_h8_journal_mode_is_wal(tmp_path):
    """REGRESSION (H8): WAL journal mode improves concurrent
    reader/writer performance and is the standard recommendation for
    multi-threaded SQLite use. Without it (the default 'delete' mode),
    every commit blocks readers.
    """
    cache_file = tmp_path / "cache.db"
    cache = SQLiteCache(path=str(cache_file))
    # Force at least one write so WAL files are materialized
    cache["k"] = "v"

    mode = cache._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal", f"expected WAL, got {mode!r}"


def test_video_metadata_caching(tmp_path):
    """Verify that video metadata is cached and retrieved."""
    cache_file = tmp_path / "cache.db"
    client = YtMeta(cache_path=str(cache_file))
    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    mock_response = MagicMock()
    player_response = {
        "videoDetails": {"videoId": "dQw4w9WgXcQ"},
        "microformat": {"playerMicroformatRenderer": {}},
    }
    initial_data = {
        "contents": {},
        "frameworkUpdates": {"entityBatchUpdate": {"mutations": []}},
    }
    mock_response.text = make_mock_html(player_response, initial_data)
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.get", return_value=mock_response) as mock_get:
        # First call - should fetch and cache
        client.get_video_metadata(video_url)
        mock_get.assert_called_once()

        # Second call - should hit the cache
        client.get_video_metadata(video_url)
        mock_get.assert_called_once()  # Should not be called again


def test_cache_persistence(tmp_path):
    """Verify that the cache persists across different YtMeta instances."""
    cache_file = tmp_path / "cache.db"
    client1 = YtMeta(cache_path=str(cache_file))
    key, value = "test_key", "test_value"
    client1.cache[key] = value
    del client1

    client2 = YtMeta(cache_path=str(cache_file))
    assert client2.cache[key] == value


def test_clear_cache(tmp_path):
    """Verify that the cache can be cleared."""
    cache_file = tmp_path / "cache.db"
    client = YtMeta(cache_path=str(cache_file))
    client.cache["key1"] = "value1"
    client.clear_cache()
    assert len(client.cache) == 0


def test_channel_page_caching(tmp_path):
    cache_file = tmp_path / "cache.db"
    client = YtMeta(cache_path=str(cache_file))
    channel_url = "https://www.youtube.com/channel/test/videos"

    # Create a proper mock response with ytcfg
    mock_response = MagicMock()
    mock_response.status_code = 200
    ytcfg = {"INNERTUBE_API_KEY": "test_key", "INNERTUBE_CONTEXT": {}}
    initial_data = {
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [{"tabRenderer": {"selected": True, "title": "Test Channel"}}],
                "header": {"c4TabbedHeaderRenderer": {"title": "Test Channel"}},
            }
        },
        "metadata": {
            "channelMetadataRenderer": {
                "title": "Test Channel",
                "description": "Test Description",
                "externalId": "UCtest123",
                "vanityChannelUrl": "https://www.youtube.com/@testchannel",
                "isFamilySafe": True,
            }
        },
    }
    html_content = make_mock_html(None, initial_data, ytcfg)
    mock_response.text = html_content
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.get", return_value=mock_response) as mock_get:
        # First call should trigger a network request
        result1 = client.get_channel_metadata(channel_url)
        mock_get.assert_called_once()
        assert result1 is not None

        # Second call should hit the cache
        result2 = client.get_channel_metadata(channel_url)
        mock_get.assert_called_once()  # Should not be called again
        assert result2 == result1

        # Third call with force_refresh should trigger another request
        result3 = client.get_channel_metadata(channel_url, force_refresh=True)
        assert mock_get.call_count == 2
        assert result3 is not None
