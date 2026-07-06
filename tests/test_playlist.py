from pathlib import Path

import pytest

from yt_meta import parsing

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
        # Current lockupViewModel shape (refreshed 2026-06).
        ("playlist_lockup_page.html", 100, True),
        # Legacy playlistVideoRenderer shape — kept to guard back-compat.
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
    # Shape-agnostic resolution: works for both the legacy
    # playlistVideoListRenderer wrapper and the bare-lockup item list.
    items = parsing.get_playlist_item_list(initial_data)
    videos, continuation_token = parsing.extract_videos_from_playlist_items(items)

    assert len(videos) == expected_video_count
    if expect_token:
        assert continuation_token is not None
    else:
        assert continuation_token is None


def test_regression_playlist_lockup_migration():
    """REGRESSION: YouTube migrated the playlist page from
    ``playlistVideoListRenderer`` / ``playlistVideoRenderer`` to a bare
    ``lockupViewModel`` item list with a ``continuationItemViewModel``
    token (the same migration that broke get_channel_videos in 0.6.0).

    The old fetcher hardcoded the ``playlistVideoListRenderer`` path, so
    get_playlist_videos returned 0 videos against the current page while
    every offline test stayed green on stale fixtures. This asserts the
    current shape parses to videos AND yields a pagination token.
    """
    html = (FIXTURES_DIR / "playlist_lockup_page.html").read_text()
    initial_data = parsing.extract_and_parse_json(html, "ytInitialData")

    items = parsing.get_playlist_item_list(initial_data)
    videos, continuation_token = parsing.extract_videos_from_playlist_items(items)

    assert videos, "lockup-shape playlist parsed to zero videos"
    assert all(v["video_id"] for v in videos)
    assert continuation_token, "no continuation token from continuationItemViewModel"


def test_fixture_freshness_lockup_page_is_current_shape():
    """Guard against fixture rot: the current-shape playlist fixture must
    actually contain ``lockupViewModel`` (and not the legacy renderer),
    otherwise it would silently re-freeze the pre-migration structure and
    stop guarding the regression above.
    """
    html = (FIXTURES_DIR / "playlist_lockup_page.html").read_text()
    assert "lockupViewModel" in html
    assert "playlistVideoRenderer" not in html


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


def test_get_playlist_metadata_via_facade():
    """parse_playlist_metadata existed with tests but was unreachable
    from the facade (June review: 'wire it up or drop it'). Wired:
    YtMeta.get_playlist_metadata fetches the playlist page and parses
    it — driven here through the real HTTP layer (R1) with the captured
    lockup-shape playlist page."""
    import httpx

    from yt_meta import YtMeta

    html = (FIXTURES_DIR / "playlist_lockup_page.html").read_text()
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=html))
    with YtMeta() as client:
        client.session._transport = transport
        client._playlist_fetcher.session = httpx.Client(transport=transport)
        meta = client.get_playlist_metadata("PLxxxx")
    assert isinstance(meta["title"], str) and meta["title"]
    assert meta["author"]
