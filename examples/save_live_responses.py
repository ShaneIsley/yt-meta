"""
Save the raw HTML of a few channel Videos tabs to examples/saved_responses/.

Useful for inspecting YouTube's page structure offline. One request per
channel, made with plain httpx rather than YtMeta.
"""

from pathlib import Path

import httpx

URLS = [
    "https://www.youtube.com/@samwitteveenai/videos",
    "https://www.youtube.com/@bulwarkmedia/videos",
    "https://www.youtube.com/@AI-Makerspace/videos",
]

# A browser User-Agent; YouTube may serve a different page to unknown clients.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"  # noqa: E501
}

output_dir = Path(__file__).parent / "saved_responses"
output_dir.mkdir(exist_ok=True)


def save_channel_html():
    """Fetch each channel page in URLS and write it to <handle>.html."""
    for url in URLS:
        try:
            print(f"Fetching {url}...")
            response = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            response.raise_for_status()

            channel_name = url.split("/@")[1].split("/")[0]
            file_path = output_dir / f"{channel_name}.html"

            file_path.write_text(response.text, encoding="utf-8")
            print(f"Saved response to {file_path}")

        except httpx.HTTPError as e:
            print(f"Failed to fetch {url}: {e}")


if __name__ == "__main__":
    save_channel_html()
