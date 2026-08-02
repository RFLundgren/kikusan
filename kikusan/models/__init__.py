"""Pydantic domain models for Kikusan.

Canonical import location for all domain models. Original modules
re-export these for backward compatibility.
"""

from kikusan.models.cron import (
    CronConfig,
    ExploreConfig,
    PlaylistConfig,
    PluginInstanceConfig,
)
from kikusan.models.deezer import DeezerTrack
from kikusan.models.queue import DownloadJob, JobStatus
from kikusan.models.search import (
    Album,
    Artist,
    ChartArtist,
    Charts,
    ChartTrack,
    MoodCategory,
    MoodPlaylist,
    MoodSection,
    SongMetadata,
    Track,
)
from kikusan.models.state import (
    PlaylistState,
    PluginState,
    PluginTrackState,
    TrackState,
)
from kikusan.models.unavailable import UnavailableRecord

__all__ = [
    "Album",
    "Artist",
    "ChartArtist",
    "Charts",
    "ChartTrack",
    "CronConfig",
    "DeezerTrack",
    "DownloadJob",
    "ExploreConfig",
    "JobStatus",
    "MoodCategory",
    "MoodPlaylist",
    "MoodSection",
    "PlaylistConfig",
    "PlaylistState",
    "PluginInstanceConfig",
    "PluginState",
    "PluginTrackState",
    "SongMetadata",
    "Track",
    "TrackState",
    "UnavailableRecord",
]
