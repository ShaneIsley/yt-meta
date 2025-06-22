from pathlib import Path

import requests

# The three channels we want to inspect
URLS = [
    "https://www.youtube.com/@samwitteveenai/videos",
    "https://www.youtube.com/@bulwarkmedia/videos",
    "https://www.youtube.com/@AI-Makerspace/videos",
]

# A standard browser User-Agent can sometimes help avoid bot detection
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"  # noqa: E501
}

# Create a directory to store the responses
output_dir = Path(__file__).parent / "saved_responses"
output_dir.mkdir(exist_ok=True)


def save_channel_html():
    """
    Fetches the HTML content for each channel and saves it to a file.
    """
    for url in URLS:
        try:
            print(f"Fetching {url}...")
            response = requests.get(url, headers=HEADERS, timeout=15)
            # Raise an exception for bad status codes (4xx or 5xx)
            response.raise_for_status()

            # Create a filename from the channel name
            channel_name = url.split("/@")[1].split("/")[0]
            file_path = output_dir / f"{channel_name}.html"

            # Save the HTML content
            file_path.write_text(response.text, encoding="utf-8")
            print(f"✅ Successfully saved response to {file_path}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to fetch {url}: {e}")


if __name__ == "__main__":
    save_channel_html()
