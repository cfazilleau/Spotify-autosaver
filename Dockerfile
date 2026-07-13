FROM python:3.12-slim

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
