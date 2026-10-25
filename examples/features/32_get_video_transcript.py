"""
Example: Video transcript

Fetches a video's transcript and prints the first five snippets, then asks for
Spanish with English as the fallback.
"""

import itertools

from yt_meta import YtMeta


def main():
    """Print the first snippets of the English transcript, then of the Spanish-or-English one."""
    client = YtMeta()
    video_id = "dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up

    print(f"Fetching transcript for video ID: {video_id}")
    transcript = client.get_video_transcript(video_id)

    if transcript:
        print("Transcript found. First 5 snippets:")
        for snippet in itertools.islice(transcript, 5):
            start_time = snippet["start"]
            text = snippet["text"]
            print(f"- [{start_time:.2f}s] {text}")
    else:
        print("No transcript found for this video.")

    # languages is an ordered preference list: Spanish if the video has it, else
    # English. Without "en" in the list, a missing Spanish transcript returns [].
    print(f"\nFetching Spanish transcript for video ID: {video_id}")
    spanish_transcript = client.get_video_transcript(video_id, languages=["es", "en"])
    if spanish_transcript:
        print("Transcript found. First 5 snippets of the first available language:")
        for snippet in itertools.islice(spanish_transcript, 5):
            start_time = snippet["start"]
            text = snippet["text"]
            print(f"- [{start_time:.2f}s] {text}")
    else:
        print("No transcript found for this video.")


if __name__ == "__main__":
    main()
