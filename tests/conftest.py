import json
import os
from pathlib import Path

import pytest

from yt_meta import YtMeta, parsing

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def channel_page():
    with open(FIXTURES_DIR / "channel_page.html", "r") as f:
        return f.read()


@pytest.fixture
def youtube_channel_initial_data():
    with open(FIXTURES_DIR / "youtube_channel_initial_data.json", "r") as f:
        return json.load(f)


@pytest.fixture
def youtube_channel_video_renderers():
    with open(FIXTURES_DIR / "youtube_channel_video_renderers.json", "r") as f:
        return json.load(f)


@pytest.fixture
def youtube_channel_ytcfg():
    with open(FIXTURES_DIR / "youtube_channel_ytcfg.json", "r") as f:
        return json.load(f)


@pytest.fixture
def debug_continuation_response():
    with open(FIXTURES_DIR / "debug_continuation_response.json", "r") as f:
        return json.load(f)


@pytest.fixture
def bulwark_channel_video_renderers():
    with open(FIXTURES_DIR / "bulwark_channel_video_renderers.json", "r") as f:
        return json.load(f)


@pytest.fixture
def aimakerspace_channel_video_renderers():
    with open(FIXTURES_DIR / "aimakerspace_channel_video_renderers.json", "r") as f:
        return json.load(f)


@pytest.fixture
def bulwark_channel_initial_data():
    with open(FIXTURES_DIR / "bulwark_channel_initial_data.json", "r") as f:
        return json.load(f)


@pytest.fixture
def bulwark_channel_ytcfg():
    with open(FIXTURES_DIR / "bulwark_channel_ytcfg.json", "r") as f:
        return json.load(f)


@pytest.fixture
def video_html():
    with open(FIXTURES_DIR / "B68agR-OeJM.html", "r") as f:
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
    with open(get_fixture_path(filename), "r") as f:
        return f.read()


@pytest.fixture
def client():
    """Provides a YtMetaClient instance for integration tests."""
    return YtMeta()
