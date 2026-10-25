"""
Example: SQLite persistent cache

Times one video fetch three ways: with no cache, with a new SQLite cache
(cache_path=), and from a second client reading that same cache file. The
first two runs hit YouTube; the third reads from disk.
"""

import os
import time
from pathlib import Path

from yt_meta import YtMeta

VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
DB_FILE = Path("alternative_cache.sqlite")


def clear_cache_files():
    """Delete the cache file so each run starts cold."""
    if DB_FILE.exists():
        os.remove(DB_FILE)


def main():
    """Time an uncached fetch, a cache-populating fetch, and a fetch from disk."""
    clear_cache_files()
    print("Built-in SQLite persistent cache")
    print()

    # A bare YtMeta() has no cache, so every call hits the network.
    print("Step 1: client without a cache.")
    client_uncached = YtMeta()
    start_time = time.perf_counter()
    client_uncached.get_video_metadata(VIDEO_URL)
    duration_uncached = time.perf_counter() - start_time
    print(f"-> Fetch took: {duration_uncached:.4f} seconds.\n")

    print("Step 2: new client that writes to the SQLite cache.")
    client_populating = YtMeta(cache_path=str(DB_FILE))
    start_time = time.perf_counter()
    client_populating.get_video_metadata(VIDEO_URL)
    duration_populating = time.perf_counter() - start_time
    print(
        f"-> Fetch that populated the SQLite cache took: {duration_populating:.4f} seconds.\n"
    )

    # A separate client stands in for a later run of the program.
    print("Step 3: another new client reading the same cache file.")
    client_from_disk = YtMeta(cache_path=str(DB_FILE))
    start_time = time.perf_counter()
    client_from_disk.get_video_metadata(VIDEO_URL)
    duration_cached = time.perf_counter() - start_time
    print(
        f"-> Fetch from the cache on disk took: {duration_cached:.4f} seconds.\n"
    )

    if duration_cached > 0:
        speedup = duration_populating / duration_cached
        print("Result:")
        print(f"The fetch from the SQLite cache was ~{speedup:.0f}x faster.")

    clear_cache_files()
    print(f"Removed cache file: {DB_FILE}")


if __name__ == "__main__":
    main()
