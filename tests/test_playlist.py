from pathlib import Path

import pytest

from yt_meta import parsing
from yt_meta.utils import _deep_get

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "playlist_fixture, expected_title, expected_author, expected_id",
    [
        (
            "playlist_page.html",
            "Python Tutorials",
            "Corey Schafer",
            "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU",
        ),
        (
            "playlist_145_videos.html",
            "Live at the Apollo: Best Bits | BBC Comedy Greats",
            "BBC Comedy Greats",
            "PLZwyeleffqk466n-1LrjzI-4MtkyxVMxw",
        ),
        (
            "playlist_118_videos.html",
            "ManDogPod",
            "ManDogPod",
            "PLa_OMsETYUxLqiD0myXN5ufVL3SoPgfpb",
        ),
        (
            "playlist_3_videos.html",
            "Destination Perfect",
            "Ozzy Man Reviews",
            "PLk7RtPiJ05L6sqKG1cdhxg29aBzUnVUPJ",
        ),
    ],
)
def test_parse_playlist_metadata(
    playlist_fixture, expected_title, expected_author, expected_id
):
    html = (FIXTURES_DIR / playlist_fixture).read_text()
    initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
    metadata = parsing.parse_playlist_metadata(initial_data)

    assert metadata["title"] == expected_title
    assert metadata["author"] == expected_author
    assert metadata["playlist_id"] == expected_id
    assert "description" in metadata
    assert metadata["video_count"] > 0


@pytest.mark.parametrize(
    "playlist_fixture, expected_video_count, expect_token",
    [
        ("playlist_page.html", 100, True),
        ("playlist_145_videos.html", 100, True),
        ("playlist_118_videos.html", 100, True),
        ("playlist_3_videos.html", 3, False),
    ],
)
def test_extract_videos_from_playlist(
    playlist_fixture, expected_video_count, expect_token
):
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


def test_get_playlist_videos_stops_at_id(client, mocker):
    # Arrange
    # Simulate a generator that would be produced by _get_raw_playlist_videos_generator
    def mock_video_generator():
        yield {"video_id": "vid1", "title": "Video 1"}
        yield {"video_id": "vid2", "title": "Video 2"}
        yield {"video_id": "vid3", "title": "Video 3"}  # This is the stop video
        yield {"video_id": "vid4", "title": "Video 4"}  # This should not be processed
        yield {"video_id": "vid5", "title": "Video 5"}  # This should not be processed

    mocker.patch(
        "yt_meta.fetchers.PlaylistFetcher._get_raw_playlist_videos_generator",
        return_value=mock_video_generator(),
    )

    # Act
    videos_gen = client.get_playlist_videos("any_playlist_id", stop_at_video_id="vid3")
    videos = list(videos_gen)

    # Assert
    assert len(videos) == 3
    assert videos[0]["video_id"] == "vid1"
    assert videos[1]["video_id"] == "vid2"
    assert videos[2]["video_id"] == "vid3"


@pytest.mark.integration
def test_get_playlist_videos(isolated_client):
    """Test fetching videos from a live playlist."""
    # Playlist: Crash Course Computer Science - stable and unlikely to change
    playlist_id = "PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo"
    videos = isolated_client.get_playlist_videos(playlist_id, max_videos=5)
    video_list = list(videos)
    assert len(video_list) >= 1
    # Verify basic metadata is present
    for video in video_list:
        assert "video_id" in video
        assert "title" in video


@pytest.mark.integration
def test_get_playlist_videos_with_full_metadata(isolated_client):
    """Test fetching full metadata for videos from a live playlist."""
    # Playlist: A short, stable playlist
    playlist_id = "PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo"
    videos = isolated_client.get_playlist_videos(
        playlist_id, fetch_full_metadata=True, max_videos=1
    )
    video_list = list(videos)
    assert len(video_list) == 1
    # Verify detailed metadata is present
    video = video_list[0]
    assert "video_id" in video
    assert "title" in video
    assert "like_count" in video
    assert isinstance(video["like_count"], int)
    assert "view_count" in video
    assert isinstance(video["view_count"], int)
