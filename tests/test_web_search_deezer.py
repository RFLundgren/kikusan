"""Tests for Deezer handling in web search endpoint."""

import pytest
from fastapi import HTTPException

from kikusan.deezer import DeezerQuotaError
from kikusan.web.app import api_search


@pytest.mark.asyncio
async def test_api_search_returns_503_on_deezer_quota(monkeypatch):
    """Deezer quota errors should map to a temporary-unavailable HTTP status."""

    def fake_get_tracks(_url: str):
        raise DeezerQuotaError("Deezer API quota limit exceeded. Please retry later.")

    monkeypatch.setattr("kikusan.deezer.is_deezer_url", lambda _q: True)
    monkeypatch.setattr("kikusan.deezer.get_tracks_from_url", fake_get_tracks)

    with pytest.raises(HTTPException) as exc:
        await api_search("https://www.deezer.com/en/playlist/908622995")

    assert exc.value.status_code == 503
    assert "quota" in exc.value.detail.lower()
