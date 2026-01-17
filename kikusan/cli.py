"""Command-line interface for Kikusan."""

import logging
from pathlib import Path

import click

from kikusan.config import get_config
from kikusan.download import download, download_url
from kikusan.search import search

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)


@click.group()
@click.version_option()
def main():
    """Kikusan - Search and download music from YouTube Music."""
    pass


@main.command()
@click.argument("query")
@click.option("-l", "--limit", default=10, help="Maximum number of results")
def search_cmd(query: str, limit: int):
    """Search for music on YouTube Music."""
    results = search(query, limit=limit)

    if not results:
        click.echo("No results found.")
        return

    click.echo(f"\nFound {len(results)} results:\n")

    for i, track in enumerate(results, 1):
        album_info = f" [{track.album}]" if track.album else ""
        click.echo(f"{i:2}. {track.title} - {track.artist}{album_info}")
        click.echo(f"    ID: {track.video_id}  Duration: {track.duration_display}")
        click.echo()


# Register search command with alias
main.add_command(search_cmd, name="search")


@main.command()
@click.argument("video_id", required=False)
@click.option("--url", "-u", help="YouTube or YouTube Music URL")
@click.option("--output", "-o", type=click.Path(), help="Output directory")
@click.option(
    "--format",
    "-f",
    "audio_format",
    default=None,
    type=click.Choice(["opus", "mp3", "flac"]),
    help="Audio format (default: opus)",
)
@click.option("--no-lyrics", is_flag=True, help="Skip fetching lyrics")
def download_cmd(
    video_id: str | None,
    url: str | None,
    output: str | None,
    audio_format: str | None,
    no_lyrics: bool,
):
    """Download a track by video ID or URL."""
    if not video_id and not url:
        raise click.UsageError("Either VIDEO_ID or --url is required")

    config = get_config()
    output_dir = Path(output) if output else config.download_dir
    fmt = audio_format or config.audio_format

    try:
        if url:
            audio_path = download_url(
                url=url,
                output_dir=output_dir,
                audio_format=fmt,
                fetch_lyrics=not no_lyrics,
            )
        else:
            audio_path = download(
                video_id=video_id,
                output_dir=output_dir,
                audio_format=fmt,
                fetch_lyrics=not no_lyrics,
            )

        if audio_path:
            click.echo(f"Downloaded: {audio_path}")
        else:
            click.echo("Download completed but could not locate file.")

    except Exception as e:
        raise click.ClickException(str(e))


main.add_command(download_cmd, name="download")


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=None, type=int, help="Port to listen on")
def web(host: str, port: int | None):
    """Start the web interface."""
    import uvicorn

    from kikusan.config import get_config

    config = get_config()
    server_port = port or config.web_port

    click.echo(f"Starting web server at http://{host}:{server_port}")

    from kikusan.web.app import app

    uvicorn.run(app, host=host, port=server_port)


if __name__ == "__main__":
    main()
