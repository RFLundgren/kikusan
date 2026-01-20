FROM python:3.14-slim@sha256:9b81fe9acff79e61affb44aaf3b6ff234392e8ca477cb86c9f7fd11732ce9b6a

# Install ffmpeg for audio processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:9a23023be68b2ed09750ae636228e903a54a05ea56ed03a934d00fe9fbeded4b /uv /usr/local/bin/uv

WORKDIR /app

# Copy project files
COPY README.md pyproject.toml uv.lock ./
COPY kikusan/ ./kikusan/

# Install dependencies
RUN uv sync --frozen

# Create downloads directory
RUN mkdir -p /downloads

ENV KIKUSAN_DOWNLOAD_DIR=/downloads
ENV KIKUSAN_WEB_PORT=8000
ENV KIKUSAN_WEB_PLAYLIST=web-downloads

EXPOSE 8000

# Run the web server
CMD ["uv", "run", "kikusan", "web", "--host", "0.0.0.0"]
