"""Tests for web download file endpoint path normalization."""

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from kikusan.web.app import download_file


class _DummyConfig:
    """Simple config stub for download_file tests."""

    def __init__(self, download_dir: Path):
        self.download_dir = download_dir


@pytest.mark.asyncio
async def test_download_file_accepts_path_prefixed_with_download_dir(tmp_path, monkeypatch):
    """Route should accept paths like 'downloads/file.opus' from queue jobs."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    audio_file = download_dir / "Foo Fighters - Arlandria.opus"
    audio_file.write_text("audio")

    monkeypatch.setattr("kikusan.web.app.get_config", lambda: _DummyConfig(download_dir))

    response = await download_file("downloads/Foo%20Fighters%20-%20Arlandria.opus")

    assert isinstance(response, FileResponse)
    assert Path(response.path) == audio_file.resolve()


@pytest.mark.asyncio
async def test_download_file_accepts_plain_relative_entry_path(tmp_path, monkeypatch):
    """Route should continue to accept plain relative M3U entry paths."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    artist_dir = download_dir / "Foo Fighters"
    artist_dir.mkdir()
    audio_file = artist_dir / "Arlandria.opus"
    audio_file.write_text("audio")

    monkeypatch.setattr("kikusan.web.app.get_config", lambda: _DummyConfig(download_dir))

    response = await download_file("Foo Fighters/Arlandria.opus")

    assert isinstance(response, FileResponse)
    assert Path(response.path) == audio_file.resolve()


@pytest.mark.asyncio
async def test_download_file_rejects_path_outside_download_dir(tmp_path, monkeypatch):
    """Route must keep blocking traversal outside download_dir."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()

    monkeypatch.setattr("kikusan.web.app.get_config", lambda: _DummyConfig(download_dir))

    with pytest.raises(HTTPException) as exc:
        await download_file("../secrets.txt")

    assert exc.value.status_code == 403
