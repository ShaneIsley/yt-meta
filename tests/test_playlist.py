import json
from pathlib import Path

import pytest

from yt_meta import parsing
from yt_meta.utils import _deep_get

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "playlist_fixture, expected_title, expected_author, expected_id",
    [
        ("playlist_page.html", "Python Tutorials", "Corey Schafer", "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"),
        ("playlist_145_videos.html", "Live at the Apollo: Best Bits | BBC Comedy Greats", "BBC Comedy Greats", "PLZwyeleffqk466n-1LrjzI-4MtkyxVMxw"),
        ("playlist_118_videos.html", "ManDogPod", "ManDogPod", "PLa_OMsETYUxLqiD0myXN5ufVL3SoPgfpb"),
        ("playlist_3_videos.html", "Destination Perfect", "Ozzy Man Reviews", "PLk7RtPiJ05L6sqKG1cdhxg29aBzUnVUPJ"),
    ],
)
def test_parse_playlist_metadata(playlist_fixture, expected_title, expected_author, expected_id):
    html = (FIXTURES_DIR / playlist_fixture).read_text()
    initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
    metadata = parsing.parse_playlist_metadata(initial_data)

    assert metadata["title"] == expected_title
    assert metadata["author"] == expected_author
    assert metadata["playlist_id"] == expected_id
    assert "description" in metadata
    assert metadata["video_count"] > 0


def find_keys(data, target_key):
    """Recursively find all paths to a target key in a nested dict/list."""
    paths = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key == target_key:
                paths.append([key])
            sub_paths = find_keys(value, target_key)
            for sub_path in sub_paths:
                paths.append([key] + sub_path)
    elif isinstance(data, list):
        for index, item in enumerate(data):
            sub_paths = find_keys(item, target_key)
            for sub_path in sub_paths:
                paths.append([index] + sub_path)
    return paths


@pytest.mark.parametrize(
    "playlist_fixture, expected_video_count, expect_token",
    [
        ("playlist_page.html", 100, True),
        ("playlist_145_videos.html", 100, True),
        ("playlist_118_videos.html", 100, True),
        ("playlist_3_videos.html", 3, False),
    ],
)
def test_extract_videos_from_playlist(playlist_fixture, expected_video_count, expect_token):
    html = (FIXTURES_DIR / playlist_fixture).read_text()
    initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
    renderer = _deep_get(
        initial_data,
        "contents.twoColumnBrowseResultsRenderer.tabs.0.tabRenderer.content.sectionListRenderer.contents.0.itemSectionRenderer.contents.0.playlistVideoListRenderer",
    )
    if not renderer:
        renderer = _deep_get(
            initial_data,
            "contents.twoColumnBrowseResultsRenderer.tabs.0.tabRenderer.content.sectionListRenderer.contents.0.playlistVideoListRenderer",
        )
    
    videos, continuation_token = parsing.extract_videos_from_playlist_renderer(renderer)

    assert len(videos) == expected_video_count
    if expect_token:
        assert continuation_token is not None
    else:
        assert continuation_token is None 