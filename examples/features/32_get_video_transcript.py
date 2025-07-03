import itertools

from yt_meta import YtMeta


def main():
    """
    This example demonstrates how to fetch the transcript for a YouTube video
    using the get_video_transcript method.
    """
    client = YtMeta()
    video_id = "dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up

    print(f"--- Fetching transcript for video ID: {video_id} ---")
    transcript = client.get_video_transcript(video_id)

    if transcript:
        print("Transcript found. Showing the first 5 snippets:")
        for snippet in itertools.islice(transcript, 5):
            start_time = snippet["start"]
            text = snippet["text"]
            print(f"- [{start_time:.2f}s] {text}")
    else:
        print("No transcript found for this video.")

    # Example of fetching a transcript in a different language
    # Note: This video may not have a Spanish transcript, but this demonstrates
    # how to request one. The underlying library will fall back to English if
    # Spanish is not available.
    print(f"\\n--- Attempting to fetch Spanish transcript for video ID: {video_id} ---")
    spanish_transcript = client.get_video_transcript(video_id, languages=["es", "en"])
    if spanish_transcript:
        print("Transcript found. Showing the first 5 snippets of the best available match:")
        for snippet in itertools.islice(spanish_transcript, 5):
            start_time = snippet["start"]
            text = snippet["text"]
            print(f"- [{start_time:.2f}s] {text}")
    else:
        print("No transcript found for this video.")


if __name__ == "__main__":
    main() 