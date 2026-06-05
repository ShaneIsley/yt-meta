from datetime import date

import pytest
from httpx import Client

from yt_meta.fetchers import PlaylistFetcher, VideoFetcher


@pytest.fixture
def video_fetcher():
    """Provides a real VideoFetcher instance for integration tests."""
    return VideoFetcher(session=Client(), cache={})


@pytest.fixture
def playlist_fetcher(video_fetcher):
    """Provides a PlaylistFetcher instance with a real session and video_fetcher."""
    return PlaylistFetcher(session=Client(), cache={}, video_fetcher=video_fetcher)


@pytest.mark.integration
def test_get_playlist_videos_integration(playlist_fetcher):
    # Google "110-language Google Translate journey 2024"
    playlist_id = "PLXFtMv-aATMXRyFmX7hw2D2j2LtmFW5un"
    videos = list(playlist_fetcher.get_playlist_videos(playlist_id, max_videos=3))
    assert len(videos) == 3
    assert "video_id" in videos[0]
    assert "title" in videos[0]


def test_regression_h1_get_playlist_videos_with_start_date_filters(
    playlist_fetcher, mocker
):
    """REGRESSION (H1): get_playlist_videos previously built `publish_date` as
    a tuple (">=", date), which raised AttributeError in apply_filters because
    tuples have no .items(). The operators ">=" / "<=" / "between" also weren't
    in the schema or _check_date_condition. ChannelFetcher.get_channel_videos
    uses the correct dict shape {"gte": ..., "lte": ...}.
    """
    fake_videos = [
        {"video_id": "v1", "publish_date": date(2023, 6, 15)},
        {"video_id": "v2", "publish_date": date(2024, 6, 15)},
        {"video_id": "v3", "publish_date": date(2025, 6, 15)},
    ]
    mocker.patch.object(
        playlist_fetcher,
        "_get_raw_playlist_videos_generator",
        return_value=iter(fake_videos),
    )

    result = list(
        playlist_fetcher.get_playlist_videos(
            "PLfake", start_date=date(2024, 1, 1)
        )
    )

    assert [v["video_id"] for v in result] == ["v2", "v3"]


def test_regression_h1_get_playlist_videos_with_start_and_end_date(
    playlist_fetcher, mocker
):
    """REGRESSION (H1): combined start_date + end_date previously produced
    a ("between", (a, b)) tuple, also crashing apply_filters.
    """
    fake_videos = [
        {"video_id": "v1", "publish_date": date(2023, 6, 15)},
        {"video_id": "v2", "publish_date": date(2024, 6, 15)},
        {"video_id": "v3", "publish_date": date(2025, 6, 15)},
    ]
    mocker.patch.object(
        playlist_fetcher,
        "_get_raw_playlist_videos_generator",
        return_value=iter(fake_videos),
    )

    result = list(
        playlist_fetcher.get_playlist_videos(
            "PLfake",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
    )

    assert [v["video_id"] for v in result] == ["v2"]
