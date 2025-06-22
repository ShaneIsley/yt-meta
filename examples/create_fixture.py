import json
from pathlib import Path

from yt_meta import YtMetaClient
from yt_meta.utils import _deep_get


def create_fixture_from_live_data():
    """
    Fetches the initial page data for a channel and saves the LAST 10
    video renderers to a fixture file. This is to ensure we have
    accurate, live data for our tests.
    """
    channel_url = "https://www.youtube.com/@AI-Makerspace/videos"
    client = YtMetaClient()

    print(f"Fetching live data from {channel_url}...")
    initial_data, _, _ = client._get_channel_page_data(channel_url)

    tabs = _deep_get(initial_data, "contents.twoColumnBrowseResultsRenderer.tabs")
    last_ten_renderers = []
    for tab in tabs:
        if "tabRenderer" in tab:
            content = _deep_get(tab, "tabRenderer.content.richGridRenderer.contents")
            if content:
                # The last item can be a continuation token, so we take the 11 items
                # before the end to get a sample of at least 10 renderers.
                last_ten_renderers = content[-11:-1]
                break

    if not last_ten_renderers:
        print("Could not find video renderers in the page data.")
        return

    # Ensure the fixtures directory exists
    fixtures_dir = Path("tests/fixtures")
    fixtures_dir.mkdir(exist_ok=True)

    output_path = fixtures_dir / "ai_makerspace_channel_renderers_last_sample.json"

    print(f"Saving last 10 video renderers to {output_path}...")
    with open(output_path, "w") as f:
        json.dump(last_ten_renderers, f, indent=2)

    print("Fixture created successfully.")


if __name__ == "__main__":
    create_fixture_from_live_data()
