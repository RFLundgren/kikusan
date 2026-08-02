"""Downloaded video index record model."""

from pydantic import BaseModel


class DownloadRecord(BaseModel):
    """A single downloaded-video record for JSON persistence."""

    file_path: str
    title: str | None = None
    artist: str | None = None
    downloaded_at: str
