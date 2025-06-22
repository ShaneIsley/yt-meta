import json
from pathlib import Path

from yt_meta import YtMetaClient
from yt_meta.utils import _deep_get

# New channel for a final data check
CHANNEL_URL = "https://www.youtube.com/@AI-Makerspace"
FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


def main():
    """
    Fetches live data and saves it as fixtures for our mocked tests.
    It now also saves a dedicated file for the list of video renderers.
    """
    print(f"Fetching live data for: {CHANNEL_URL}")
    client = YtMetaClient()

    # Use our internal method to get the data
    initial_data, ytcfg, _ = client._get_channel_page_data(f"{CHANNEL_URL}/videos")

    # Create the fixtures directory if it doesn't exist
    FIXTURES_DIR.mkdir(exist_ok=True)

    # --- Save the full data blobs ---
    initial_data_path = FIXTURES_DIR / "aimakerspace_channel_initial_data.json"
    ytcfg_path = FIXTURES_DIR / "aimakerspace_channel_ytcfg.json"

    with open(initial_data_path, "w", encoding="utf-8") as f:
        json.dump(initial_data, f, indent=2)
    print(f"✅ Saved initial data to: {initial_data_path}")

    with open(ytcfg_path, "w", encoding="utf-8") as f:
        json.dump(ytcfg, f, indent=2)
    print(f"✅ Saved ytcfg data to: {ytcfg_path}")

    # --- Extract and save just the video renderers ---
    tabs = _deep_get(initial_data, "contents.twoColumnBrowseResultsRenderer.tabs", [])
    videos_tab = next((tab for tab in tabs if _deep_get(tab, "tabRenderer.selected")), None)

    if videos_tab:
        video_renderers = _deep_get(videos_tab, "tabRenderer.content.richGridRenderer.contents", [])
        video_renderers_path = FIXTURES_DIR / "aimakerspace_channel_video_renderers.json"
        with open(video_renderers_path, "w", encoding="utf-8") as f:
            # We only want the video renderers, not the continuation token at the end
            json.dump([r for r in video_renderers if "richItemRenderer" in r], f, indent=2)
        print(f"✅ Extracted and saved video renderers to: {video_renderers_path}")
    else:
        print("❌ Could not find the videos tab to extract renderers.")


if __name__ == "__main__":
    main()
