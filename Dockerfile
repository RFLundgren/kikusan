FROM python:3.14-slim@sha256:486b8092bfb12997e10d4920897213a06563449c951c5506c2a2cfaf591c599f

# Install ffmpeg for audio processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg jq curl && \
    rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:78a7ff97cd27b7124a5f3c2aefe146170793c56a1e03321dd31a289f6d82a04f /uv /usr/local/bin/uv

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
