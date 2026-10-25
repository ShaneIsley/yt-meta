"""
Example: Time an uncached fetch against a SQLite cache hit

Fetches one video three times: with no cache, with a new SQLite cache
(populating it), and with a second client reading that cache from disk.
The first two calls hit YouTube; the third makes no request.
"""

import shutil
import time
from pathlib import Path

from yt_meta import YtMeta

VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
CACHE_DIR = Path(".my_yt_meta_cache_benchmark")
CACHE_PATH = CACHE_DIR / "cache.db"


def clear_cache_directory():
    """Delete and recreate the cache directory so the run starts empty."""
    if CACHE_DIR.exists():
        print(f"Clearing existing cache directory: {CACHE_DIR}")
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(exist_ok=True)


def main():
    """Time the three fetches and print the speedup."""

    print("YouTube metadata caching benchmark")
    print(f"Video URL: {VIDEO_URL}")

    clear_cache_directory()
    print()

    # YtMeta() caches nothing by default, so this is a plain request.
    print("Step 1: fetch with no cache")
    client_in_memory = YtMeta()
    start_time = time.perf_counter()
    client_in_memory.get_video_metadata(VIDEO_URL)
    duration = time.perf_counter() - start_time
    print(f"    Uncached fetch took: {duration:.4f} seconds")
    print()

    print("Step 2: first fetch with a SQLite cache (populating it)")
    client_populating = YtMeta(cache_path=str(CACHE_PATH))
    start_time = time.perf_counter()
    client_populating.get_video_metadata(VIDEO_URL)
    duration = time.perf_counter() - start_time
    print(f"    Cache population took: {duration:.4f} seconds")
    print()

    # A fresh client stands in for an application restart.
    print("Step 3: new client reading the existing SQLite cache")
    print("        (as after an application restart)")

    client_from_disk = YtMeta(cache_path=str(CACHE_PATH))
    start_time = time.perf_counter()
    client_from_disk.get_video_metadata(VIDEO_URL)
    duration_cached = time.perf_counter() - start_time
    print(f"    Cached fetch took: {duration_cached:.4f} seconds")
    print()

    # duration is from step 2 (the populating fetch), not step 1.
    if duration_cached > 0:
        speedup = duration / duration_cached
        print("Results:")
        print(f"   Uncached (populating): {duration:.4f}s")
        print(f"   Cached (from disk):    {duration_cached:.4f}s")
        print(f"   Speedup:               ~{speedup:.0f}x")
    else:
        print("The cached fetch was too fast to time.")

    shutil.rmtree(CACHE_DIR)
    print(f"Removed cache directory: {CACHE_DIR}")


if __name__ == "__main__":
    main()
