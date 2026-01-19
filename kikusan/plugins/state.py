"""Plugin state management."""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PluginTrackState:
    """State for a track downloaded by a plugin."""

    cache_key: str
    artist: str
    title: str
    file_path: str
    downloaded_at: str
    video_id: str | None = None


@dataclass
class PluginState:
    """State for a plugin sync instance."""

    plugin_name: str
    plugin_type: str
    source_url: str | None
    last_check: str
    tracks: list[PluginTrackState]


def get_state_dir(download_dir: Path) -> Path:
    """Get the plugin state directory path.

    Creates directory if it doesn't exist.

    Args:
        download_dir: Download directory

    Returns:
        Path to plugin state directory ({download_dir}/.kikusan/plugin_state)
    """
    state_dir = download_dir / ".kikusan" / "plugin_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def load_plugin_state(state_dir: Path, plugin_name: str) -> PluginState | None:
    """Load plugin state from JSON file.

    Args:
        state_dir: State directory path
        plugin_name: Plugin instance name

    Returns:
        PluginState if file exists and is valid, None otherwise
    """
    state_file = state_dir / f"{plugin_name}.json"

    if not state_file.exists():
        logger.debug("State file not found: %s", state_file)
        return None

    try:
        content = state_file.read_text(encoding="utf-8")
        data = json.loads(content)

        # Parse tracks
        tracks = [PluginTrackState(**t) for t in data.get("tracks", [])]

        return PluginState(
            plugin_name=data["plugin_name"],
            plugin_type=data["plugin_type"],
            source_url=data.get("source_url"),
            last_check=data["last_check"],
            tracks=tracks,
        )

    except json.JSONDecodeError as e:
        logger.error("Corrupted state file: %s - %s", state_file, e)
        # Backup corrupted file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = state_dir / f"{plugin_name}.json.corrupt.{timestamp}"
        state_file.rename(backup)
        logger.info("Backed up corrupted state to: %s", backup)
        return None

    except Exception as e:
        logger.error("Failed to load state file %s: %s", state_file, e)
        return None


def save_plugin_state(state_dir: Path, state: PluginState) -> None:
    """Save plugin state to JSON file using atomic write.

    Args:
        state_dir: State directory path
        state: Plugin state to save
    """
    state_file = state_dir / f"{state.plugin_name}.json"
    temp_file = state_dir / f"{state.plugin_name}.json.tmp"

    try:
        # Serialize to JSON
        data = asdict(state)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)

        # Write to temp file
        temp_file.write_text(json_str, encoding="utf-8")

        # Atomic rename (POSIX guarantee)
        temp_file.rename(state_file)

        logger.debug("Saved plugin state: %s", state.plugin_name)

    except Exception as e:
        logger.error("Failed to save state for %s: %s", state.plugin_name, e)
        # Clean up temp file if it exists
        if temp_file.exists():
            temp_file.unlink()
        raise
