"""Tests for Deezer playlist support."""

import pytest

from kikusan.deezer import DeezerQuotaError, get_tracks_from_url, is_deezer_url


class _FakeResponse:
    """Simple HTTP response stub for httpx.get monkeypatching."""

    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_is_deezer_url_accepts_standard_and_localized_urls():
    assert is_deezer_url("https://www.deezer.com/playlist/908622995")
    assert is_deezer_url("https://www.deezer.com/us/playlist/908622995")


def test_is_deezer_url_rejects_non_deezer_playlist_urls():
    assert not is_deezer_url("https://open.spotify.com/playlist/123")
    assert not is_deezer_url("https://www.deezer.com/album/123")


def test_get_tracks_from_url_returns_tracks(monkeypatch):
    from kikusan import deezer as deezer_module

    def fake_get(url, params=None, timeout=30):
        if url.endswith("/playlist/908622995"):
            return _FakeResponse({"id": 908622995, "title": "Fake Deezer Playlist", "nb_tracks": 2})
        if url.endswith("/playlist/908622995/tracks"):
            index = (params or {}).get("index", 0)
            if index == 0:
                return _FakeResponse(
                    {
                        "data": [
                            {
                                "title": "My Song",
                                "duration": 200,
                                "contributors": [{"name": "Main Artist"}, {"name": "Guest Artist"}],
                                "artist": {"name": "Main Artist"},
                                "album": {"title": "My Album"},
                            },
                            {
                                "title": "Solo Song",
                                "duration": 150,
                                "contributors": [],
                                "artist": {"name": "Solo Artist"},
                                "album": None,
                            },
                        ]
                    }
                )
            return _FakeResponse({"data": []})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(deezer_module.httpx, "get", fake_get)

    tracks = get_tracks_from_url("https://www.deezer.com/playlist/908622995")

    assert len(tracks) == 2
    assert tracks[0].name == "My Song"
    assert tracks[0].artist == "Main Artist"
    assert tracks[0].artists == ["Main Artist", "Guest Artist"]
    assert tracks[0].album == "My Album"
    assert tracks[0].duration_ms == 200000
    assert tracks[0].search_query == "My Song Main Artist"
    assert tracks[1].artists == ["Solo Artist"]


def test_get_tracks_from_url_rejects_unsupported_url():
    with pytest.raises(ValueError, match="Unsupported Deezer URL"):
        get_tracks_from_url("https://www.deezer.com/album/123")


def test_get_tracks_from_url_raises_quota_error(monkeypatch):
    from kikusan import deezer as deezer_module

    def fake_get(url, params=None, timeout=30):
        return _FakeResponse(
            {"error": {"type": "Exception", "message": "Quota limit exceeded", "code": 4}}
        )

    monkeypatch.setattr(deezer_module.httpx, "get", fake_get)

    with pytest.raises(DeezerQuotaError, match="quota limit exceeded"):
        get_tracks_from_url("https://www.deezer.com/playlist/908622995")
