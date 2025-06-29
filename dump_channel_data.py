import json
import logging
from yt_meta import YtMeta

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    client = YtMeta()
    channel_url = "https://www.youtube.com/@bashbunni"
    
    # --- Dump Regular Videos Page Initial Data ---
    try:
        initial_data, _, _ = client._channel_fetcher._get_channel_page_data(channel_url)
        with open("bashbunni_videos_initial_data.json", "w") as f:
            json.dump(initial_data, f, indent=2)
        print("Successfully dumped bashbunni_videos_initial_data.json")
    except Exception as e:
        print(f"Failed to dump videos initial data: {e}")

    # --- Dump Shorts Page Initial Data ---
    try:
        initial_data, _, _ = client._channel_fetcher._get_channel_shorts_page_data(channel_url)
        with open("bashbunni_shorts_initial_data.json", "w") as f:
            json.dump(initial_data, f, indent=2)
        print("Successfully dumped bashbunni_shorts_initial_data.json")
    except Exception as e:
        print(f"Failed to dump shorts initial data: {e}") 