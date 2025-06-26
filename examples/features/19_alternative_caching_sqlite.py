import time
import os
from pathlib import Path
from sqlitedict import SqliteDict
from yt_meta import YtMeta

# --- Configuration ---
VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
DB_FILE = Path("alternative_cache.sqlite")

def main():
    """
    Demonstrates using a different persistent cache backend (SqliteDict)
    that conforms to the dictionary-like interface required by YtMeta.
    """
    print("--- Using SqliteDict as a persistent cache backend ---")
    
    # Clean up previous database file if it exists
    if DB_FILE.exists():
        os.remove(DB_FILE)

    # 1. Instantiate the cache. `autocommit=True` ensures writes are saved immediately.
    # The `SqliteDict` object behaves just like a standard Python dictionary.
    sqlite_cache = SqliteDict(str(DB_FILE), autocommit=True)

    # 2. First run with the SqliteDict cache
    print("Step 1: Running with a new client using the SqliteDict cache.")
    client1 = YtMeta(cache=sqlite_cache)
    start_time1 = time.perf_counter()
    meta1 = client1.get_video_metadata(VIDEO_URL)
    duration1 = time.perf_counter() - start_time1
    print(f"-> First fetch (populating SQLite) took: {duration1:.4f} seconds.")
    
    # The SqliteDict connection should be closed when it's no longer in use.
    sqlite_cache.close()
    print("-" * 50)

    # 3. Second run with a new client and a new SqliteDict instance on the same file
    print("Step 2: A new client instance reading from the same SQLite file.")
    
    # Re-opening the connection to the same database file
    sqlite_cache_2 = SqliteDict(str(DB_FILE), autocommit=True)

    client2 = YtMeta(cache=sqlite_cache_2)
    start_time2 = time.perf_counter()
    meta2 = client2.get_video_metadata(VIDEO_URL)
    duration2 = time.perf_counter() - start_time2
    print(f"-> Second fetch (from SQLite cache) took: {duration2:.4f} seconds.")

    # 4. Verification and Conclusion
    if duration2 > 0:
        speedup = duration1 / duration2
        print("\nConclusion:")
        print(f"The call using the populated SqliteDict cache was ~{speedup:.0f}x faster.")
        assert meta1 == meta2
        print("Metadata from both calls is identical, proving the interface works.")

    # Clean up
    sqlite_cache_2.close()
    os.remove(DB_FILE)
    print(f"\nCleaned up cache database: {DB_FILE}")


if __name__ == "__main__":
    main() 