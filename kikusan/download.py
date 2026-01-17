"""Download functionality using yt-dlp."""

import logging
from pathlib import Path

import yt_dlp

from kikusan.lyrics import get_lyrics, save_lyrics

logger = logging.getLogger(__name__)


def download(
    video_id: str,
    output_dir: Path,
    audio_format: str = "opus",
    fetch_lyrics: bool = True,
) -> Path:
    """
    Download a track from YouTube Music.

    Args:
        video_id: YouTube video ID
        output_dir: Directory to save the downloaded file
        audio_format: Audio format (opus, mp3, flac)
        fetch_lyrics: Whether to fetch and save lyrics

    Returns:
        Path to the downloaded audio file
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Configure yt-dlp options
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "0",  # Best quality
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
            {
                "key": "EmbedThumbnail",
            },
        ],
        "writethumbnail": True,
        "quiet": True,
        "no_warnings": True,
    }

    url = f"https://music.youtube.com/watch?v={video_id}"

    # Extract info first to get metadata
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title", "Unknown")
    artist = info.get("artist") or info.get("uploader", "Unknown")
    duration = info.get("duration", 0)

    logger.info("Downloading: %s - %s", artist, title)

    # Download the track
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # Find the downloaded file
    audio_path = _find_downloaded_file(output_dir, title, audio_format)

    if audio_path and fetch_lyrics:
        lyrics = get_lyrics(title, artist, duration)
        if lyrics:
            save_lyrics(lyrics, audio_path)

    return audio_path


def download_url(
    url: str,
    output_dir: Path,
    audio_format: str = "opus",
    fetch_lyrics: bool = True,
) -> Path:
    """
    Download a track from a YouTube/YouTube Music URL.

    Args:
        url: YouTube or YouTube Music URL
        output_dir: Directory to save the downloaded file
        audio_format: Audio format (opus, mp3, flac)
        fetch_lyrics: Whether to fetch and save lyrics

    Returns:
        Path to the downloaded audio file
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "0",
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
            {
                "key": "EmbedThumbnail",
            },
        ],
        "writethumbnail": True,
        "quiet": True,
        "no_warnings": True,
    }

    # Extract info first
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title", "Unknown")
    artist = info.get("artist") or info.get("uploader", "Unknown")
    duration = info.get("duration", 0)

    logger.info("Downloading: %s - %s", artist, title)

    # Download
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    audio_path = _find_downloaded_file(output_dir, title, audio_format)

    if audio_path and fetch_lyrics:
        lyrics = get_lyrics(title, artist, duration)
        if lyrics:
            save_lyrics(lyrics, audio_path)

    return audio_path


def _find_downloaded_file(output_dir: Path, title: str, audio_format: str) -> Path | None:
    """Find the downloaded audio file in the output directory."""
    # yt-dlp sanitizes filenames, so we search for matching files
    for ext in [audio_format, "opus", "m4a", "webm"]:
        matches = list(output_dir.glob(f"*{title}*.{ext}"))
        if matches:
            return matches[0]

    # Fallback: return most recently modified audio file
    audio_extensions = ["opus", "mp3", "m4a", "flac", "webm"]
    all_audio = []
    for ext in audio_extensions:
        all_audio.extend(output_dir.glob(f"*.{ext}"))

    if all_audio:
        return max(all_audio, key=lambda p: p.stat().st_mtime)

    return None
