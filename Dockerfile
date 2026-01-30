FROM python:3.14-slim@sha256:9b81fe9acff79e61affb44aaf3b6ff234392e8ca477cb86c9f7fd11732ce9b6a

# Install ffmpeg for audio processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg jq curl && \
    rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:59240a65d6b57e6c507429b45f01b8f2c7c0bbeee0fb697c41a39c6a8e3a4cfb /uv /usr/local/bin/uv

# Create non-root user for security
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} kikusan && \
    useradd -u ${UID} -g ${GID} -m -s /bin/bash kikusan

WORKDIR /app

# Copy project files
COPY README.md pyproject.toml uv.lock ./
COPY kikusan/ ./kikusan/

# Install dependencies
RUN uv sync --frozen

# Create downloads directory and set permissions
RUN mkdir -p /downloads && \
    chown -R kikusan:kikusan /app /downloads

ENV KIKUSAN_DOWNLOAD_DIR=/downloads
ENV KIKUSAN_WEB_PORT=8000
ENV KIKUSAN_WEB_PLAYLIST=web-downloads

# Switch to non-root user
USER kikusan

EXPOSE 8000

# Run the web server
CMD ["uv", "run", "kikusan", "web", "--host", "0.0.0.0"]
