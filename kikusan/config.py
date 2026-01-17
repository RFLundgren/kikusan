"""Configuration handling for Kikusan."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Application configuration."""

    download_dir: Path
    audio_format: str
    web_port: int

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables with defaults."""
        return cls(
            download_dir=Path(os.getenv("KIKUSAN_DOWNLOAD_DIR", "./downloads")),
            audio_format=os.getenv("KIKUSAN_AUDIO_FORMAT", "opus"),
            web_port=int(os.getenv("KIKUSAN_WEB_PORT", "8000")),
        )


def get_config() -> Config:
    """Get the current configuration."""
    return Config.from_env()
