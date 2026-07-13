FROM python:3.12-slim

# Links the GHCR package to this repository (and lets it inherit repo visibility).
LABEL org.opencontainers.image.source="https://github.com/cfazilleau/spotify-autosaver"
LABEL org.opencontainers.image.description="Keep a Spotify playlist mirroring your most recently liked songs."
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY spotify_autosaver ./spotify_autosaver
RUN pip install --no-cache-dir .

# Run continuously by default. Provide credentials via environment variables
# (see .env.example). Headless auth requires SPOTIFY_REFRESH_TOKEN.
ENTRYPOINT ["spotify-autosaver"]
CMD ["run"]
