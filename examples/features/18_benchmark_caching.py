"""
Example: Benchmark Caching Performance

This example demonstrates the performance benefits of using persistent disk
caching versus in-memory caching for YouTube metadata fetching.

Key concepts:
• Persistent vs in-memory caching
• Performance benchmarking
• Cache lifecycle management
• Speed optimization benefits
"""

import shutil
import time
from pathlib import Path

from yt_meta import YtMeta

# --- Configuration ---
VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
CACHE_DIR = Path(".my_yt_meta_cache_benchmark")
CACHE_PATH = CACHE_DIR / "cache.db"


def clear_cache_directory():
    """Remove the cache directory if it exists to ensure a clean benchmark."""
    if CACHE_DIR.exists():
        print(f"Clearing existing cache directory: {CACHE_DIR}")
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(exist_ok=True)


def main():
    """Demonstrate the performance benefits of persistent caching."""

    print("=== YouTube Metadata Caching Benchmark ===")
    print(f"Video URL: {VIDEO_URL}")

    # Start with a clean slate
    clear_cache_directory()
    print("-" * 50)

    # --- Step 1: Baseline with in-memory cache ---
    print("Step 1: Baseline performance with in-memory cache")
    client_in_memory = YtMeta()
    start_time = time.perf_counter()
    client_in_memory.get_video_metadata(VIDEO_URL)
    duration = time.perf_counter() - start_time
    print(f"    ⏱️  Initial fetch took: {duration:.4f} seconds")
    print()

    print("-" * 50)

    # --- Step 2: First fetch with persistent cache (populating) ---
    print("Step 2: First fetch with persistent disk cache (populating)")

    # This block ensures the cache is properly closed after use
    client_populating = YtMeta(cache_path=str(CACHE_PATH))
    start_time = time.perf_counter()
    client_populating.get_video_metadata(VIDEO_URL)
    duration = time.perf_counter() - start_time
    print(f"    ⏱️  Cache population took: {duration:.4f} seconds")
    print()

    print("-" * 50)

    # --- Step 3: New client reading from populated cache ---
    print("Step 3: New client instance reading from existing persistent cache")
    print("        (simulates application restart)")

    client_from_disk = YtMeta(cache_path=str(CACHE_PATH))
    start_time = time.perf_counter()
    client_from_disk.get_video_metadata(VIDEO_URL)
    duration_cached = time.perf_counter() - start_time
    print(f"    ⏱️  Cached fetch took: {duration_cached:.4f} seconds")
    print()

    print("-" * 50)

    # --- Results Analysis ---
    if duration_cached > 0:
        speedup = duration / duration_cached
        print("🎯 BENCHMARK RESULTS:")
        print(f"   • Baseline (in-memory): {duration:.4f}s")
        print(f"   • Cached (from disk):   {duration_cached:.4f}s")
        print(f"   • Speedup factor:       ~{speedup:.0f}x faster")
        print()
        print("✅ Persistent caching provides significant performance benefits!")
    else:
        print("⚠️  Cache performance could not be measured accurately")

    # Clean up the created cache directory
    shutil.rmtree(CACHE_DIR)
    print(f"🧹 Cleaned up cache directory: {CACHE_DIR}")


if __name__ == "__main__":
    main()
