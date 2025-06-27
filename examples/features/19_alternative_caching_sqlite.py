import time
import os
from pathlib import Path
import shutil
from sqlitedict import SqliteDict
from yt_meta import YtMeta

# --- Configuration ---
VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
DB_FILE = Path("alternative_cache.sqlite")
CACHE_DIR = Path(f"{DB_FILE}.cache")  # SqliteDict creates a journal/cache dir


def clear_cache_files():
    """Removes the cache files if they exist to ensure a clean benchmark."""
    if DB_FILE.exists():
        os.remove(DB_FILE)
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)


def main():
    """
    Demonstrates using SqliteDict as a persistent cache, mimicking the 3-step
    benchmark for clarity.
    """
    clear_cache_files()
    print("--- Using SqliteDict as a persistent cache backend ---")
    print("-" * 50)

    # --- Step 1: Initial fetch time with no persistent cache ---
    print("Step 1: Running with a standard client (in-memory cache).")
    client_in_memory = YtMeta()
    start_time = time.perf_counter()
    client_in_memory.get_video_metadata(VIDEO_URL)
    duration_uncached = time.perf_counter() - start_time
    print(f"-> Initial fetch took: {duration_uncached:.4f} seconds.\n")

    print("-" * 50)

    # --- Step 2: First fetch with the persistent cache (populating it) ---
    print("Step 2: Running with a new client to populate the SQLite cache.")

    with SqliteDict(str(DB_FILE), autocommit=True) as cache1:
        client_populating = YtMeta(cache=cache1)
        start_time = time.perf_counter()
        client_populating.get_video_metadata(VIDEO_URL)
        duration_populating = time.perf_counter() - start_time
        print(f"-> First fetch with SQLite (populating) took: {duration_populating:.4f} seconds.\n")

    print("-" * 50)

    # --- Step 3: A completely new client reading from the populated cache ---
    print("Step 3: Simulating a new run with another new client instance.")
    print("        This demonstrates reading from the existing SQLite cache.")

    with SqliteDict(str(DB_FILE), autocommit=True) as cache2:
        client_from_disk = YtMeta(cache=cache2)
        start_time = time.perf_counter()
        client_from_disk.get_video_metadata(VIDEO_URL)
        duration_cached = time.perf_counter() - start_time
        print(f"-> First fetch for this new client (from disk) took: {duration_cached:.4f} seconds.\n")

    print("-" * 50)

    # --- Conclusion ---
    if duration_cached > 0:
        speedup = duration_populating / duration_cached
        print("Conclusion:")
        print(f"The call using the populated SQLite cache was ~{speedup:.0f}x faster.")

    # Clean up
    clear_cache_files()
    print(f"Cleaned up cache files: {DB_FILE} and related journal/cache files.")


if __name__ == "__main__":
    main()
