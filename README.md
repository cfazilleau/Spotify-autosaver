# 🎵 Spotify Autosaver

Keep a Spotify playlist that always mirrors your **most recently liked songs**.

Spotify won't let you download your *Liked Songs* for offline listening, and the
list keeps growing forever. Autosaver solves both problems: it maintains a
regular playlist containing your latest liked tracks (100 by default), so you can
mark **that** playlist for offline download and it stays fresh automatically.

## How it works

Every time it runs, Autosaver:

1. Fetches the *N* most recently added tracks from your **Liked Songs**
   (`GET /v1/me/tracks`, which is already ordered newest-first).
2. Finds — or creates — your target playlist.
3. Replaces the playlist's contents with those tracks.

That's it. Run it continuously, on a cron, in Docker, or via GitHub Actions.

### Efficient polling (fast loops are fine)

In continuous (`run`) mode the tool is built to poll frequently without
hammering the API. On each tick it makes **one** cheap request for a lightweight
fingerprint of your library — `(total liked count, newest track)` — and only
runs the full fetch-and-replace when that fingerprint changes. The playlist is
resolved once at startup rather than on every tick.

That fingerprint catches every meaningful change with a single call: liking a
new song (count rises, newest changes), unliking the top song (newest changes),
or unliking any other song (count drops). So a **10-second** interval costs just
6 idle calls/minute and stays well within Spotify's rate limits. (spotipy also
transparently retries on `429 Too Many Requests`, honouring `Retry-After`.)

## Setup

### 1. Create a Spotify app

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   and create an app.
2. Copy the **Client ID** and **Client Secret**.
3. In the app settings, add a **Redirect URI**: `http://127.0.0.1:8888/callback`.

### 2. Install

```bash
git clone https://github.com/cfazilleau/spotify-autosaver.git
cd spotify-autosaver
pip install -e .
```

### 3. Configure

```bash
cp .env.example .env
# edit .env and fill in SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET
```

See [`.env.example`](.env.example) for every available setting.

## Usage

```bash
# Run once (great for cron / CI)
spotify-autosaver sync

# Run continuously, polling on an interval and syncing only on change.
# Set a fast interval with AUTOSAVER_INTERVAL_SECONDS (e.g. 10); default hourly.
spotify-autosaver run

# First-time login on a machine with a browser; prints a reusable
# refresh token for headless deployments.
spotify-autosaver auth
```

The first `sync`/`run` on a machine with a browser opens a login page and caches
the token locally (`.cache`). After that it refreshes automatically.

## Running headlessly (server, Docker, CI)

Headless environments have no browser, so authenticate once locally to obtain a
refresh token:

```bash
spotify-autosaver auth
# → prints a users.json entry AND a SPOTIFY_REFRESH_TOKEN= line
```

Provide that token (plus the client id/secret) and no interactive login is ever
needed. For a single account you can set `SPOTIFY_REFRESH_TOKEN` in the
environment; for one or more accounts, use the users file below.

## Syncing multiple accounts (users file)

To mirror liked songs for several people (e.g. you and friends) from **one**
deployment, list each account's refresh token in a JSON file — by default
`users.json`, or set `AUTOSAVER_USERS_FILE`. When this file exists it takes
precedence over `SPOTIFY_REFRESH_TOKEN`.

```json
{
  "users": [
    { "name": "me", "refresh_token": "AQ...my-token" },
    { "name": "alex", "refresh_token": "AQ...alex-token", "playlist_name": "Alex latest 100" }
  ]
}
```

- Only `refresh_token` is required per entry. `name`, `playlist_name`,
  `playlist_id`, `track_count`, `playlist_public`, and `playlist_description`
  are optional and fall back to the global defaults.
- Each account gets its **own** playlist in its **own** Spotify account, its own
  change-detection state, and is polled independently. One failing account never
  stops the others.
- Each friend generates their token by running `spotify-autosaver auth` (on a
  machine with a browser) and sending you the printed entry, which you paste in.
- The client id/secret in `.env` are the shared **app** credentials — they stay
  in the environment; only the per-account tokens go in this file.

> **Heads-up (Spotify limit):** a Spotify app starts in *Development Mode*,
> capped at **25 users**, and each account's email must be added under
> **User Management** in the [developer dashboard](https://developer.spotify.com/dashboard)
> before it can authorize. More than that requires a quota-extension request.

> **Security:** `users.json` holds credentials that can read libraries and edit
> playlists for every listed account. It's git-ignored by default — keep it
> private and mount it read-only (as the compose file does).

Copy [`users.example.json`](users.example.json) to `users.json` to get started.

### Docker (build locally)

```bash
docker compose up -d --build   # uses .env, restarts automatically
```

### Deploying from GHCR (published image)

The [`docker-publish.yml`](.github/workflows/docker-publish.yml) workflow builds
the image on every push to `main` (and on `v*` git tags) and publishes it to the
**GitHub Container Registry**:

```
ghcr.io/cfazilleau/spotify-autosaver:latest
```

**1. Authenticate your local Docker to GHCR.** GHCR requires a login even for
your own images. Create a [Personal Access Token (classic)](https://github.com/settings/tokens)
with the **`read:packages`** scope, then:

```bash
export CR_PAT=ghp_your_token_here
echo "$CR_PAT" | docker login ghcr.io -u cfazilleau --password-stdin
```

> If your package is set to **public** (Package settings → Change visibility),
> you can `docker pull` it without logging in — but a login is still needed to
> push, and for any private package.

**2. Pull and run.** The bundled [`docker-compose.yml`](docker-compose.yml)
already points at the GHCR image and mounts `users.json`, so on your local
machine just:

```bash
cp .env.example .env             # fill in the app client id/secret
cp users.example.json users.json # add each account's refresh token
docker compose pull              # fetch the latest published image
docker compose up -d             # run continuously, auto-restart
```

Add or remove friends by editing `users.json` and running
`docker compose restart`. Or without compose:

```bash
docker run -d --name spotify-autosaver --restart unless-stopped \
  --env-file .env \
  -e AUTOSAVER_USERS_FILE=/app/users.json \
  -v "$PWD/users.json:/app/users.json:ro" \
  ghcr.io/cfazilleau/spotify-autosaver:latest run
```

**Note on registry permissions:** the first publish creates the package as
**private** and linked to this repo (via the image's
`org.opencontainers.image.source` label). The `read:packages` PAT above is what
your local Docker uses to pull it. In CI, publishing uses the automatic
`GITHUB_TOKEN` — no PAT needed there.

### GitHub Actions (zero infrastructure)

The included [`.github/workflows/sync.yml`](.github/workflows/sync.yml) runs
`sync` on a schedule using GitHub's runners. Add these repository secrets under
**Settings → Secrets and variables → Actions**:

| Secret | Value |
| --- | --- |
| `SPOTIPY_CLIENT_ID` | your app's client id |
| `SPOTIPY_CLIENT_SECRET` | your app's client secret |
| `SPOTIFY_REFRESH_TOKEN` | output of `spotify-autosaver auth` |

Then enable the workflow. It runs hourly (and can be triggered manually via
**Run workflow**).

## Configuration reference

| Variable | Default | Description |
| --- | --- | --- |
| `SPOTIPY_CLIENT_ID` | — | **Required.** Spotify app client id. |
| `SPOTIPY_CLIENT_SECRET` | — | **Required.** Spotify app client secret. |
| `SPOTIPY_REDIRECT_URI` | `http://127.0.0.1:8888/callback` | Must match the dashboard. |
| `SPOTIFY_REFRESH_TOKEN` | — | Enables headless auth when set. |
| `AUTOSAVER_CACHE_PATH` | `.cache` | Token cache for interactive auth. |
| `AUTOSAVER_TRACK_COUNT` | `100` | How many recent liked songs to mirror. |
| `AUTOSAVER_PLAYLIST_ID` | — | Target an existing playlist by id. |
| `AUTOSAVER_PLAYLIST_NAME` | `Liked Songs (Latest 100)` | Name to find/create. |
| `AUTOSAVER_PLAYLIST_PUBLIC` | `false` | Make the created playlist public. |
| `AUTOSAVER_PLAYLIST_DESCRIPTION` | *(see .env.example)* | Description for created playlist. |
| `AUTOSAVER_INTERVAL_SECONDS` | `3600` | Poll interval for `run` (seconds). Short values are safe. |

## Development

```bash
pip install -e ".[dev]"
pytest        # run tests
ruff check .  # lint
```

## Notes

- The playlist is **replaced** each run, so don't add tracks to it manually —
  they'll be overwritten. Point Autosaver at a dedicated playlist.
- Local files in your Liked Songs are skipped (they can't be added by URI).
- OAuth scopes used: `user-library-read`, `playlist-modify-public`,
  `playlist-modify-private`.

## License

[MIT](LICENSE)
