"""Configuration handling for Kikusan."""

import os
from dataclasses import dataclass
from pathlib import Path

# Default filename template: Artist - Title
DEFAULT_FILENAME_TEMPLATE = "%(artist,uploader)s - %(title)s"


@dataclass
class Config:
    """Application configuration."""

    download_dir: Path
    audio_format: str
    filename_template: str
    web_port: int

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables with defaults."""
        return cls(
            download_dir=Path(os.getenv("KIKUSAN_DOWNLOAD_DIR", "./downloads")),
            audio_format=os.getenv("KIKUSAN_AUDIO_FORMAT", "opus"),
            filename_template=os.getenv("KIKUSAN_FILENAME_TEMPLATE", DEFAULT_FILENAME_TEMPLATE),
            web_port=int(os.getenv("KIKUSAN_WEB_PORT", "8000")),
        )


def get_config() -> Config:
    """Get the current configuration."""
    return Config.from_env()
