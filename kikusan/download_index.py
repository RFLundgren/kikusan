"""Index of downloaded video IDs, used to show "already downloaded" status in the UI.

Tracks which YouTube video IDs have been downloaded and where, so search
results can indicate whether a track is already present on disk (or was
downloaded previously but the file has since been removed).

Storage: {data_dir}/downloaded.json
Format: {"video_id": {"file_path": "...", "title": "...", "artist": "...", "downloaded_at": "ISO timestamp"}}
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from kikusan.models.download_index import DownloadRecord

logger = logging.getLogger(__name__)


def get_index_file(data_dir: Path) -> Path:
    """Get the path to the downloaded videos JSON file.

    Creates the parent directory if it doesn't exist.

    Args:
        data_dir: Data directory (e.g. ~/.kikusan)

    Returns:
        Path to downloaded.json
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "downloaded.json"


def load_index(data_dir: Path) -> dict:
    """Load the downloaded videos index from disk.

    Args:
        data_dir: Data directory (e.g. ~/.kikusan)

    Returns:
        Dict mapping video_id to download record
    """
    index_file = get_index_file(data_dir)

    if not index_file.exists():
        return {}

    try:
        content = index_file.read_text(encoding="utf-8")
        data = json.loads(content)
        if not isinstance(data, dict):
            logger.warning("Download index file has unexpected format, resetting")
            return {}
        return data
    except json.JSONDecodeError as e:
        logger.error("Corrupted download index file: %s", e)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = index_file.with_suffix(f".json.corrupt.{timestamp}")
        index_file.rename(backup)
        logger.info("Backed up corrupted download index file to: %s", backup)
        return {}
    except Exception as e:
        logger.error("Failed to load download index file: %s", e)
        return {}


def save_index(data_dir: Path, data: dict) -> None:
    """Save the downloaded videos index to disk using atomic write.

    Args:
        data_dir: Data directory (e.g. ~/.kikusan)
        data: Dict mapping video_id to download record
    """
    index_file = get_index_file(data_dir)
    temp_file = index_file.with_suffix(".json.tmp")

    try:
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        temp_file.write_text(json_str, encoding="utf-8")
        temp_file.replace(index_file)
        logger.debug("Saved download index (%d entries)", len(data))
    except Exception as e:
        logger.error("Failed to save download index file: %s", e)
        if temp_file.exists():
            temp_file.unlink()
        raise


def record_downloaded(
    data_dir: Path,
    video_id: str,
    file_path: str,
    title: str | None = None,
    artist: str | None = None,
) -> None:
    """Record a video as downloaded.

    Args:
        data_dir: Data directory (e.g. ~/.kikusan)
        video_id: YouTube video ID
        file_path: Path to the downloaded audio file
        title: Optional track title
        artist: Optional track artist
    """
    try:
        data = load_index(data_dir)

        record = DownloadRecord(
            file_path=file_path,
            title=title,
            artist=artist,
            downloaded_at=datetime.now(timezone.utc).isoformat(),
        )
        data[video_id] = record.model_dump()

        save_index(data_dir, data)
    except Exception as e:
        # Never let index bookkeeping break a successful download
        logger.warning("Failed to record download index for %s: %s", video_id, e)


def get_download_statuses(data_dir: Path, video_ids: list[str]) -> dict[str, str]:
    """Get download status for a list of video IDs.

    Args:
        data_dir: Data directory (e.g. ~/.kikusan)
        video_ids: YouTube video IDs to check

    Returns:
        Dict mapping video_id to "downloaded" or "missing" (file was
        downloaded but no longer exists at the recorded path). Video IDs
        never downloaded are omitted from the result entirely.
    """
    data = load_index(data_dir)

    statuses = {}
    for video_id in video_ids:
        record = data.get(video_id)
        if record is None:
            continue
        file_path = record.get("file_path")
        statuses[video_id] = "downloaded" if file_path and Path(file_path).exists() else "missing"

    return statuses
