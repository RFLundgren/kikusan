"""Cron configuration loading and validation."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from croniter import croniter

logger = logging.getLogger(__name__)


@dataclass
class PlaylistConfig:
    """Configuration for a single playlist."""

    name: str
    url: str
    sync: bool
    schedule: str


@dataclass
class CronConfig:
    """Root configuration for cron playlists."""

    playlists: dict[str, PlaylistConfig]


def load_config(path: Path) -> CronConfig:
    """
    Load and validate cron configuration from YAML file.

    Args:
        path: Path to cron.yaml file

    Returns:
        Validated CronConfig

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML syntax: {e}")

    if not data or "playlists" not in data:
        raise ValueError("Config must have 'playlists' key")

    playlists_data = data["playlists"]
    if not isinstance(playlists_data, dict):
        raise ValueError("'playlists' must be a dictionary")

    if not playlists_data:
        raise ValueError("No playlists defined in config")

    playlists = {}
    for name, config in playlists_data.items():
        # Validate playlist name
        sanitized_name = validate_playlist_name(name)

        # Validate required fields
        if not isinstance(config, dict):
            raise ValueError(f"Playlist '{name}' config must be a dictionary")

        if "url" not in config:
            raise ValueError(f"Playlist '{name}' missing required field: url")
        if "sync" not in config:
            raise ValueError(f"Playlist '{name}' missing required field: sync")
        if "schedule" not in config:
            raise ValueError(f"Playlist '{name}' missing required field: schedule")

        url = config["url"]
        sync = config["sync"]
        schedule = config["schedule"]

        # Validate types
        if not isinstance(url, str):
            raise ValueError(f"Playlist '{name}' url must be a string")
        if not isinstance(sync, bool):
            raise ValueError(f"Playlist '{name}' sync must be a boolean")
        if not isinstance(schedule, str):
            raise ValueError(f"Playlist '{name}' schedule must be a string")

        # Validate URL
        validate_url(url, name)

        # Validate cron schedule
        validate_cron_schedule(schedule, name)

        playlists[sanitized_name] = PlaylistConfig(
            name=sanitized_name,
            url=url,
            sync=sync,
            schedule=schedule,
        )

    logger.info("Loaded configuration for %d playlist(s)", len(playlists))
    return CronConfig(playlists=playlists)


def validate_playlist_name(name: str) -> str:
    """
    Validate and sanitize playlist name.

    Only allows alphanumeric characters, dash, and underscore to prevent
    path traversal and filesystem issues.

    Args:
        name: Playlist name

    Returns:
        Sanitized playlist name

    Raises:
        ValueError: If name contains invalid characters
    """
    if not re.match(r"^[\w\-]+$", name):
        raise ValueError(
            f"Invalid playlist name '{name}': "
            "only alphanumeric, dash, and underscore allowed"
        )
    return name


def validate_url(url: str, playlist_name: str) -> None:
    """
    Validate playlist URL.

    Ensures URL is a valid YouTube, YouTube Music, or Spotify URL.

    Args:
        url: Playlist URL
        playlist_name: Playlist name for error messages

    Raises:
        ValueError: If URL is invalid
    """
    # YouTube/YouTube Music patterns
    youtube_patterns = [
        r"^https?://(www\.)?youtube\.com/",
        r"^https?://music\.youtube\.com/",
        r"^https?://youtu\.be/",
    ]

    # Spotify patterns
    spotify_patterns = [
        r"^https?://(open\.)?spotify\.com/playlist/",
        r"^https?://(open\.)?spotify\.com/album/",
    ]

    is_valid = False
    for pattern in youtube_patterns + spotify_patterns:
        if re.match(pattern, url):
            is_valid = True
            break

    if not is_valid:
        raise ValueError(
            f"Playlist '{playlist_name}' has invalid URL: {url}. "
            "Must be a YouTube, YouTube Music, or Spotify URL"
        )


def validate_cron_schedule(schedule: str, playlist_name: str) -> None:
    """
    Validate cron schedule expression.

    Args:
        schedule: Cron expression (e.g., "5 4 * * *")
        playlist_name: Playlist name for error messages

    Raises:
        ValueError: If cron expression is invalid
    """
    if not schedule or not schedule.strip():
        raise ValueError(f"Playlist '{playlist_name}' has empty schedule")

    try:
        # croniter will raise ValueError if expression is invalid
        croniter(schedule)
    except Exception as e:
        raise ValueError(
            f"Playlist '{playlist_name}' has invalid cron schedule '{schedule}': {e}"
        )
