"""FastAPI web application for Kikusan."""

import urllib.parse
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
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
    audio_format: str = "opus"


class DownloadResponse(BaseModel):
    """Response body for download endpoint."""

    success: bool
    message: str
    file_path: str | None = None
    file_name: str | None = None


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


class StreamUrlResponse(BaseModel):
    """Response for stream URL endpoint."""

    video_id: str
    url: str
    expires_in: int


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

    # Validate format
    valid_formats = ['opus', 'mp3', 'flac']
    audio_format = request.audio_format.lower()
    if audio_format not in valid_formats:
        return DownloadResponse(
            success=False,
            message=f"Invalid format. Must be one of: {', '.join(valid_formats)}",
        )

    try:
        audio_path = download(
            video_id=request.video_id,
            output_dir=config.download_dir,
            audio_format=audio_format,
            filename_template=config.filename_template,
            fetch_lyrics=True,
        )

        # Add to playlist if configured
        if audio_path and config.web_playlist_name:
            add_to_m3u([audio_path], config.web_playlist_name, config.download_dir)

        return DownloadResponse(
            success=True,
            message=f"Downloaded: {request.title} - {request.artist} ({audio_format.upper()})",
            file_path=str(audio_path) if audio_path else None,
            file_name=audio_path.name if audio_path else None,
        )

    except Exception as e:
        return DownloadResponse(
            success=False,
            message=f"Download failed: {str(e)}",
        )


@app.get("/api/download-file/{file_path:path}")
async def download_file(file_path: str):
    """Serve downloaded file for browser download."""
    config = get_config()
    file_path = urllib.parse.unquote(file_path)
    requested_path = Path(file_path)

    try:
        abs_requested = requested_path.resolve()
        abs_download_dir = config.download_dir.resolve()

        # Security: ensure path is within download_dir
        if not str(abs_requested).startswith(str(abs_download_dir)):
            raise HTTPException(status_code=403, detail="Access denied")

        if not abs_requested.exists():
            raise HTTPException(status_code=404, detail="File not found")

        if not abs_requested.is_file():
            raise HTTPException(status_code=400, detail="Not a file")

        return FileResponse(
            path=abs_requested,
            filename=abs_requested.name,
            media_type='application/octet-stream'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to serve file")


@app.get("/api/stream-url/{video_id}", response_model=StreamUrlResponse)
async def get_stream_url(video_id: str):
    """Get direct stream URL for a video using yt-dlp."""
    try:
        youtube_url = f"https://music.youtube.com/watch?v={video_id}"
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)

            # Extract direct audio URL
            if 'url' in info:
                stream_url = info['url']
            elif 'formats' in info:
                audio_formats = [f for f in info['formats'] if f.get('acodec') != 'none']
                if audio_formats:
                    audio_formats.sort(key=lambda f: f.get('abr', 0), reverse=True)
                    stream_url = audio_formats[0]['url']
                else:
                    raise HTTPException(status_code=404, detail="No audio stream found")
            else:
                raise HTTPException(status_code=404, detail="No stream URL available")

            return StreamUrlResponse(
                video_id=video_id,
                url=stream_url,
                expires_in=21600
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stream URL: {str(e)}")
