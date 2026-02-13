"""Tests for playlist streaming search SSE endpoint."""

import json

import pytest
from starlette.requests import Request

from kikusan.deezer import DeezerTrack
from kikusan.search import Track
from kikusan.web.app import api_search_playlist_stream


def _make_track(video_id: str, title: str, artist: str) -> Track:
    return Track(
        video_id=video_id,
        title=title,
        artist=artist,
        artists=[artist],
        album=None,
        duration_seconds=180,
        thumbnail_url=None,
        view_count=None,
    )


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


async def _false_disconnected(_self) -> bool:
    return False


def _parse_sse_events(payload: str) -> list[dict]:
    events: list[dict] = []
    current: dict | None = None

    for raw_line in payload.splitlines():
        line = raw_line.strip("\r")
        if not line:
            if current:
                events.append(current)
                current = None
            continue

        if line.startswith("event:"):
            current = {"event": line.split(":", 1)[1].strip()}
            continue

        if line.startswith("data:"):
            payload_json = line.split(":", 1)[1].strip()
            if current is None:
                current = {}
            current["data"] = json.loads(payload_json)

    if current:
        events.append(current)

    return events


@pytest.mark.asyncio
async def test_playlist_stream_reports_progress_and_complete(monkeypatch):
    """Streaming search should report progress and final results for Deezer playlists."""

    deezer_tracks = [
        DeezerTrack(
            name="Song A",
            artist="Artist A",
            artists=["Artist A"],
            album=None,
            duration_ms=180000,
        ),
        DeezerTrack(
            name="Song B",
            artist="Artist B",
            artists=["Artist B"],
            album=None,
            duration_ms=200000,
        ),
    ]

    def fake_search(_query: str, limit: int = 1):
        return [_make_track("video12345AA", "Song A", "Artist A")]

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("kikusan.deezer.is_deezer_url", lambda _q: True)
    monkeypatch.setattr("kikusan.deezer.get_tracks_from_url", lambda _q: deezer_tracks)
    monkeypatch.setattr("kikusan.search.search", fake_search)
    monkeypatch.setattr("kikusan.web.app.asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr(Request, "is_disconnected", _false_disconnected)

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/search/playlist/stream",
            "headers": [],
            "query_string": b"",
        },
        receive=_receive,
    )

    response = await api_search_playlist_stream(
        request,
        q="https://www.deezer.com/playlist/123",
    )

    assert response.status_code == 200

    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, (bytes, bytearray)) else str(chunk))

    events = _parse_sse_events("".join(chunks))
    progress_events = [event for event in events if event.get("event") == "progress"]
    complete_events = [event for event in events if event.get("event") == "complete"]

    assert progress_events
    assert complete_events

    first_progress = progress_events[0]["data"]
    assert first_progress["stage"] in {"fetching", "matching"}

    final_progress = progress_events[-1]["data"]
    assert final_progress["stage"] == "matching"
    assert final_progress["total"] == len(deezer_tracks)
    assert final_progress["processed"] == len(deezer_tracks)

    complete_payload = complete_events[-1]["data"]
    assert complete_payload["total"] == 2
    assert len(complete_payload["results"]) == 2
