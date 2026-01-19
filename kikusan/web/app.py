"""FastAPI web application for Kikusan."""

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from kikusan.config import get_config
from kikusan.download import download
from kikusan.playlist import add_to_m3u
from kikusan.search import search

app = FastAPI(title="Kikusan", description="Search and download music from YouTube Music")

# Setup templates and static files
templates_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(templates_dir))
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


class DownloadRequest(BaseModel):
    """Request body for download endpoint."""

    video_id: str
    title: str
    artist: str


class DownloadResponse(BaseModel):
    """Response body for download endpoint."""

    success: bool
    message: str
    file_path: str | None = None


class TrackResponse(BaseModel):
    """Track data for API responses."""

    video_id: str
    title: str
    artist: str
    album: str | None
    duration: str
    thumbnail_url: str | None
    view_count: str | None


class SearchResponse(BaseModel):
    """Response body for search endpoint."""

    query: str
    results: list[TrackResponse]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main search page."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/search", response_model=SearchResponse)
async def api_search(q: str = Query(..., min_length=1, description="Search query")):
    """Search for music on YouTube Music."""
    results = search(q, limit=20)

    return SearchResponse(
        query=q,
        results=[
            TrackResponse(
                video_id=track.video_id,
                title=track.title,
                artist=track.artist,
                album=track.album,
                duration=track.duration_display,
                thumbnail_url=track.thumbnail_url,
                view_count=track.view_count,
            )
            for track in results
        ],
    )


@app.post("/api/download", response_model=DownloadResponse)
async def api_download(request: DownloadRequest):
    """Download a track by video ID."""
    config = get_config()

    try:
        audio_path = download(
            video_id=request.video_id,
            output_dir=config.download_dir,
            audio_format=config.audio_format,
            filename_template=config.filename_template,
            fetch_lyrics=True,
        )

        # Add to playlist if configured
        if audio_path and config.web_playlist_name:
            add_to_m3u([audio_path], config.web_playlist_name, config.download_dir)

        return DownloadResponse(
            success=True,
            message=f"Downloaded: {request.title} - {request.artist}",
            file_path=str(audio_path) if audio_path else None,
        )

    except Exception as e:
        return DownloadResponse(
            success=False,
            message=f"Download failed: {str(e)}",
        )
