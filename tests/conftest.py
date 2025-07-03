import json
import os
from pathlib import Path

import pytest

from yt_meta import YtMeta, parsing


def make_mock_html(player_response, initial_data, ytcfg=None):
    """Creates a minimal HTML structure for mocking video pages."""
    if ytcfg is None:
        ytcfg = {"INNERTUBE_API_KEY": "test_key", "INNERTUBE_CONTEXT": {}}

    player_script = (
        f"<script>var ytInitialPlayerResponse = {json.dumps(player_response)};</script>"
        if player_response
        else ""
    )
    data_script = (
        f"<script>var ytInitialData = {json.dumps(initial_data)};</script>"
        if initial_data
        else ""
    )
    ytcfg_script = f"<script>ytcfg.set({json.dumps(ytcfg)});</script>"

    return f"""
    <html><body>
    {player_script}
    {data_script}
    {ytcfg_script}
    </body></html>
    """


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def channel_page():
    with open(FIXTURES_DIR / "channel_page.html") as f:
        return f.read()


@pytest.fixture
def youtube_channel_initial_data():
    with open(FIXTURES_DIR / "youtube_channel_initial_data.json") as f:
        return json.load(f)


@pytest.fixture
def youtube_channel_video_renderers():
    with open(FIXTURES_DIR / "youtube_channel_video_renderers.json") as f:
        return json.load(f)


@pytest.fixture
def youtube_channel_ytcfg():
    with open(FIXTURES_DIR / "youtube_channel_ytcfg.json") as f:
        return json.load(f)


@pytest.fixture
def debug_continuation_response():
    with open(FIXTURES_DIR / "debug_continuation_response.json") as f:
        return json.load(f)


@pytest.fixture
def bulwark_channel_video_renderers():
    with open(FIXTURES_DIR / "bulwark_channel_video_renderers.json") as f:
        return json.load(f)


@pytest.fixture
def aimakerspace_channel_video_renderers():
    with open(FIXTURES_DIR / "aimakerspace_channel_video_renderers.json") as f:
        return json.load(f)


@pytest.fixture
def bulwark_channel_initial_data():
    with open(FIXTURES_DIR / "bulwark_channel_initial_data.json") as f:
        return json.load(f)


@pytest.fixture
def bulwark_channel_ytcfg():
    with open(FIXTURES_DIR / "bulwark_channel_ytcfg.json") as f:
        return json.load(f)


@pytest.fixture
def video_html():
    with open(FIXTURES_DIR / "B68agR-OeJM.html") as f:
        return f.read()


@pytest.fixture
def player_response_data(video_html):
    return parsing.extract_and_parse_json(video_html, "ytInitialPlayerResponse")


@pytest.fixture
def initial_data(video_html):
    return parsing.extract_and_parse_json(video_html, "ytInitialData")


def get_fixture_path(filename):
    """Returns the absolute path to a fixture file."""
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


def get_fixture(filename):
    """Reads and returns the content of a fixture file."""
    with open(get_fixture_path(filename)) as f:
        return f.read()


@pytest.fixture
def client() -> YtMeta:
    """Provides a cache-less YtMeta instance for unit testing."""
    return YtMeta(cache_path=None)


@pytest.fixture
def isolated_client(tmp_path) -> YtMeta:
    """
    Provides a YtMeta client with a fresh, isolated cache in a temporary
    directory for each test. This prevents cache pollution between tests.
    """
    cache_file = tmp_path / "test_cache.db"
    return YtMeta(cache_path=str(cache_file))


@pytest.fixture
def video_fetcher(isolated_client: YtMeta):
    """Provides a VideoFetcher instance with an isolated cache."""
    return isolated_client._video_fetcher
