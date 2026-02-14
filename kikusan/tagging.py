"""Tag existing audio files with lyrics and ReplayGain.

Recursively walks a directory, extracts metadata via mutagen, and applies:
- Lyrics from lrclib.net (via lyrics.py)
- ReplayGain/R128 tags (via replaygain.py)
"""

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".opus", ".mp3", ".flac"}

# Map file extension to audio format name used by replaygain.py
EXTENSION_TO_FORMAT = {
    ".opus": "opus",
    ".mp3": "mp3",
    ".flac": "flac",
}


@dataclass
class TagStats:
    """Accumulated statistics from a tagging run."""

    files_found: int = 0
    lyrics_added: int = 0
    lyrics_skipped: int = 0
    lyrics_not_found: int = 0
    lyrics_failed: int = 0
    replaygain_applied: int = 0
    replaygain_skipped: int = 0
    replaygain_failed: int = 0
    errors: int = 0


@dataclass
class FileMetadata:
    """Metadata extracted from an audio file."""

    title: str
    artist: str
    album: str | None
    duration_seconds: int


def extract_metadata(file_path: Path) -> FileMetadata | None:
    """Extract title, artist, album, and duration from an audio file via mutagen.

    Args:
        file_path: Path to the audio file

    Returns:
        FileMetadata if extraction succeeded, None if file is unreadable or has no metadata
    """
    try:
        from mutagen import File

        audio = File(file_path)
        if audio is None:
            logger.debug("Mutagen could not open: %s", file_path)
            return None

        # Extract artist: prefer ARTISTS multi-value tag, fall back to artist
        artist_raw = (
            audio.get("ARTISTS")
            or audio.get("artists")
            or audio.get("artist")
        )
        title_raw = audio.get("title")

        if not title_raw or not artist_raw:
            logger.debug("Missing title or artist metadata in: %s", file_path)
            return None

        artist = artist_raw[0] if isinstance(artist_raw, list) else str(artist_raw)
        title = title_raw[0] if isinstance(title_raw, list) else str(title_raw)

        # Extract album (optional)
        album_raw = audio.get("album")
        album = None
        if album_raw:
            album = album_raw[0] if isinstance(album_raw, list) else str(album_raw)

        # Extract duration (mutagen stores as float seconds in info.length)
        duration_seconds = 0
        if audio.info and hasattr(audio.info, "length"):
            duration_seconds = int(audio.info.length)

        return FileMetadata(
            title=str(title),
            artist=str(artist),
            album=album,
            duration_seconds=duration_seconds,
        )

    except Exception as e:
        logger.warning("Failed to extract metadata from %s: %s", file_path, e)
        return None


def collect_audio_files(directory: Path) -> list[Path]:
    """Recursively collect audio files with supported extensions.

    Args:
        directory: Root directory to search

    Returns:
        Sorted list of audio file paths
    """
    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(directory.rglob(f"*{ext}"))
    return sorted(files)


def tag_file(
    file_path: Path,
    *,
    do_lyrics: bool = True,
    do_replaygain: bool = True,
    dry_run: bool = False,
    stats: TagStats | None = None,
) -> None:
    """Apply lyrics and/or ReplayGain tags to a single audio file.

    Args:
        file_path: Path to the audio file
        do_lyrics: Whether to fetch and save lyrics
        do_replaygain: Whether to apply ReplayGain tags
        dry_run: If True, only log what would be done
        stats: Optional stats object to update
    """
    if stats is None:
        stats = TagStats()

    metadata = extract_metadata(file_path)
    if metadata is None:
        logger.warning("Skipping %s: could not extract metadata", file_path.name)
        stats.errors += 1
        return

    if do_lyrics:
        _tag_lyrics(file_path, metadata, dry_run=dry_run, stats=stats)

    if do_replaygain:
        _tag_replaygain(file_path, dry_run=dry_run, stats=stats)


def _tag_lyrics(
    file_path: Path,
    metadata: FileMetadata,
    *,
    dry_run: bool,
    stats: TagStats,
) -> None:
    """Fetch and save lyrics for a single file."""
    from kikusan.lyrics import _search_lyrics, _try_cleaned_lookup, get_lyrics, save_lyrics

    lrc_path = file_path.with_suffix(".lrc")
    if lrc_path.exists():
        logger.info("Lyrics already exist: %s", lrc_path.name)
        stats.lyrics_skipped += 1
        return

    if dry_run:
        logger.info(
            "[dry-run] Would fetch lyrics for: %s - %s",
            metadata.artist,
            metadata.title,
        )
        return

    try:
        # Strategy 1: exact match via get_lyrics
        lyrics = get_lyrics(metadata.title, metadata.artist, metadata.duration_seconds)

        # Strategy 2: search with album for fuzzy match
        if not lyrics:
            lyrics = _search_lyrics(
                metadata.title,
                metadata.artist,
                metadata.album,
                metadata.duration_seconds,
            )

        # Strategy 3: retry with cleaned title/artist (strip parentheticals, secondary artists)
        if not lyrics:
            lyrics = _try_cleaned_lookup(
                metadata.title,
                metadata.artist,
                metadata.album,
                metadata.duration_seconds,
            )

        if lyrics:
            save_lyrics(lyrics, file_path)
            stats.lyrics_added += 1
        else:
            logger.info("No lyrics found for: %s - %s", metadata.artist, metadata.title)
            stats.lyrics_not_found += 1

    except Exception as e:
        logger.warning("Failed to fetch lyrics for %s: %s", file_path.name, e)
        stats.lyrics_failed += 1


def _has_replaygain_tags(file_path: Path, audio_format: str) -> bool:
    """Check if a file already has ReplayGain tags.

    Args:
        file_path: Path to the audio file
        audio_format: Audio format (opus, mp3, flac)

    Returns:
        True if ReplayGain tags exist, False otherwise
    """
    try:
        from mutagen import File

        audio = File(file_path)
        if audio is None:
            return False

        # Check for ReplayGain tags based on format
        if audio_format == "opus":
            # Opus uses R128_TRACK_GAIN and R128_ALBUM_GAIN (RFC 7845)
            # or REPLAYGAIN_TRACK_GAIN for older files
            return (
                "R128_TRACK_GAIN" in audio
                or "REPLAYGAIN_TRACK_GAIN" in audio
            )
        elif audio_format == "mp3":
            # MP3 ID3v2 uses RVA2 frames or TXXX:replaygain_* tags
            # Common tag names from rsgain
            replaygain_keys = [
                "REPLAYGAIN_TRACK_GAIN",
                "replaygain_track_gain",
            ]
            return any(key in audio for key in replaygain_keys)
        elif audio_format == "flac":
            # FLAC uses Vorbis comments
            replaygain_keys = [
                "REPLAYGAIN_TRACK_GAIN",
                "replaygain_track_gain",
            ]
            return any(key in audio for key in replaygain_keys)

        return False

    except Exception as e:
        logger.debug("Failed to check ReplayGain tags for %s: %s", file_path.name, e)
        return False


def _tag_replaygain(
    file_path: Path,
    *,
    dry_run: bool,
    stats: TagStats,
) -> None:
    """Apply ReplayGain tags to a single file."""
    from kikusan.replaygain import apply_replaygain

    audio_format = EXTENSION_TO_FORMAT.get(file_path.suffix.lower())
    if not audio_format:
        logger.warning("Unknown format for ReplayGain: %s", file_path.suffix)
        stats.replaygain_failed += 1
        return

    # Check if ReplayGain tags already exist
    if _has_replaygain_tags(file_path, audio_format):
        logger.info("ReplayGain tags already exist: %s", file_path.name)
        stats.replaygain_skipped += 1
        return

    if dry_run:
        logger.info("[dry-run] Would apply ReplayGain to: %s", file_path.name)
        return

    success = apply_replaygain(file_path, audio_format)
    if success:
        stats.replaygain_applied += 1
    else:
        stats.replaygain_failed += 1


def tag_directory(
    directory: Path,
    *,
    do_lyrics: bool = True,
    do_replaygain: bool = True,
    dry_run: bool = False,
) -> TagStats:
    """Recursively tag all audio files in a directory.

    Args:
        directory: Root directory to process
        do_lyrics: Whether to fetch and save lyrics
        do_replaygain: Whether to apply ReplayGain tags
        dry_run: If True, only log what would be done

    Returns:
        TagStats with summary counts
    """
    files = collect_audio_files(directory)
    stats = TagStats(files_found=len(files))

    logger.info("Found %d audio files in %s", len(files), directory)

    for i, file_path in enumerate(files, 1):
        logger.info("[%d/%d] Processing: %s", i, len(files), file_path.name)
        try:
            tag_file(
                file_path,
                do_lyrics=do_lyrics,
                do_replaygain=do_replaygain,
                dry_run=dry_run,
                stats=stats,
            )
        except Exception as e:
            logger.warning("Error processing %s: %s", file_path.name, e)
            stats.errors += 1

    return stats
