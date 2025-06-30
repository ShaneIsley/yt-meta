import shutil
import time
from pathlib import Path

from diskcache import Cache

from yt_meta import YtMeta

# --- Configuration ---
VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
CACHE_DIR = Path(".my_yt_meta_cache_benchmark")


def clear_cache_directory():
    """Removes the cache directory if it exists to ensure a clean benchmark."""
    if CACHE_DIR.exists():
        print(f"Clearing existing cache directory: {CACHE_DIR}")
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(exist_ok=True)


def main():
    """Demonstrates the performance benefits of a persistent cache."""

    # Start with a clean slate
    clear_cache_directory()
    print("-" * 50)

    # --- Step 1: Initial fetch time with no persistent cache ---
    print("Step 1: Running with a standard client (in-memory cache).")
    client_in_memory = YtMeta()
    start_time = time.perf_counter()
    client_in_memory.get_video_metadata(VIDEO_URL)
    duration = time.perf_counter() - start_time
    print(f"-> Initial fetch took: {duration:.4f} seconds.\n")

    print("-" * 50)

    # --- Step 2: First fetch with the persistent cache (populating it) ---
    print("Step 2: Running with a new client to populate the persistent disk cache.")

    # This block ensures the cache is properly closed after use
    with Cache(CACHE_DIR) as cache1:
        client_populating = YtMeta(cache=cache1)
        start_time = time.perf_counter()
        client_populating.get_video_metadata(VIDEO_URL)
        duration = time.perf_counter() - start_time
        print(f"-> First fetch with disk cache (populating) took: {duration:.4f} seconds.\n")

    print("-" * 50)

    # --- Step 3: A completely new client reading from the populated cache ---
    print("Step 3: Simulating a new run with another new client instance.")
    print("        This demonstrates reading from the existing persistent cache.")

    with Cache(CACHE_DIR) as cache2:
        client_from_disk = YtMeta(cache=cache2)
        start_time = time.perf_counter()
        client_from_disk.get_video_metadata(VIDEO_URL)
        duration_cached = time.perf_counter() - start_time
        print(f"-> First fetch for this new client (from disk) took: {duration_cached:.4f} seconds.\n")

    print("-" * 50)

    # --- Conclusion ---
    if duration_cached > 0:
        speedup = duration / duration_cached
        print("Conclusion:")
        print(f"The call using the populated persistent cache was ~{speedup:.0f}x faster.")

    # Clean up the created cache directory
    shutil.rmtree(CACHE_DIR)
    print(f"Cleaned up cache directory: {CACHE_DIR}")


if __name__ == "__main__":
    main()
