"""Playlist state management."""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TrackState:
    """State for a single track."""

    video_id: str
    title: str
    artist: str
    file_path: str
    downloaded_at: str


@dataclass
class PlaylistState:
    """State for an entire playlist."""

    playlist_name: str
    url: str
    last_check: str
    tracks: list[TrackState]


def get_state_dir(download_dir: Path) -> Path:
    """
    Get the state directory path.

    Creates directory if it doesn't exist.

    Args:
        download_dir: Download directory

    Returns:
        Path to state directory ({download_dir}/.kikusan/state)
    """
    state_dir = download_dir / ".kikusan" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def load_state(state_dir: Path, playlist_name: str) -> PlaylistState | None:
    """
    Load playlist state from JSON file.

    Args:
        state_dir: State directory path
        playlist_name: Playlist name

    Returns:
        PlaylistState if file exists and is valid, None otherwise
    """
    state_file = state_dir / f"{playlist_name}.json"

    if not state_file.exists():
        logger.debug("State file not found: %s", state_file)
        return None

    try:
        content = state_file.read_text(encoding="utf-8")
        data = json.loads(content)

        # Parse tracks
        tracks = [TrackState(**track) for track in data.get("tracks", [])]

        return PlaylistState(
            playlist_name=data["playlist_name"],
            url=data["url"],
            last_check=data["last_check"],
            tracks=tracks,
        )

    except json.JSONDecodeError as e:
        logger.error("Corrupted state file: %s - %s", state_file, e)
        # Backup corrupted file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = state_dir / f"{playlist_name}.json.corrupt.{timestamp}"
        state_file.rename(backup_file)
        logger.info("Backed up corrupted state to: %s", backup_file)
        return None

    except Exception as e:
        logger.error("Failed to load state file %s: %s", state_file, e)
        return None


def save_state(state_dir: Path, state: PlaylistState) -> None:
    """
    Save playlist state to JSON file using atomic write.

    Args:
        state_dir: State directory path
        state: Playlist state to save
    """
    state_file = state_dir / f"{state.playlist_name}.json"
    temp_file = state_dir / f"{state.playlist_name}.json.tmp"

    try:
        # Serialize to JSON
        data = asdict(state)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)

        # Write to temp file
        temp_file.write_text(json_str, encoding="utf-8")

        # Atomic rename (POSIX guarantee)
        temp_file.rename(state_file)

        logger.debug("Saved state for playlist: %s", state.playlist_name)

    except Exception as e:
        logger.error("Failed to save state for %s: %s", state.playlist_name, e)
        # Clean up temp file if it exists
        if temp_file.exists():
            temp_file.unlink()
        raise
