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

That's it. Run it continuously (`run`) or as a one-shot (`sync`), locally or in Docker.

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
2. Under **Which API/SDKs are you planning to use?**, tick **Web API**.
3. Copy the **Client ID** (no client secret is needed — see [Authentication](#authentication)).
4. Add a **Redirect URI** matching where you'll host the auth page — e.g. your
   GitHub Pages URL `https://<username>.github.io/Spotify-autosaver/`.

### 2. Install

```bash
git clone https://github.com/cfazilleau/spotify-autosaver.git
cd spotify-autosaver
pip install -e .
```

### 3. Configure

```bash
cp .env.example .env             # set SPOTIPY_CLIENT_ID and SPOTIPY_REDIRECT_URI
cp users.example.json users.json # add each account's refresh token (see below)
```

See [`.env.example`](.env.example) for every available setting.

## Authentication

Autosaver uses the **Authorization Code with PKCE** flow, so it needs **no client
secret** — only the client id. Accounts authorize through a small static web page
([`docs/index.html`](docs/index.html)) that runs entirely in the browser and
hands each person a refresh token to drop into [`users.json`](#syncing-multiple-accounts-users-file).

### Host the auth page on GitHub Pages

1. Edit `docs/index.html` and set `CONFIGURED_CLIENT_ID` to your app's Client ID.
2. In the repo: **Settings → Pages → Build and deployment → Source: Deploy from a
   branch**, branch `main`, folder **`/docs`**. Save.
3. Your page goes live at `https://<username>.github.io/Spotify-autosaver/`.
   Add that exact URL to the app's **Redirect URIs** in the dashboard, and set it
   as `SPOTIPY_REDIRECT_URI` in `.env`.

Then anyone (you or a friend) opens the page, clicks **Log in with Spotify**,
approves, and copies the generated `{ "name": ..., "refresh_token": ... }` entry
to send you. No secret, no server, no local install needed on their end.

> Prefer the terminal? You can still mint a token locally with any PKCE helper,
> but the hosted page is the intended path — especially for friends.

## Usage

```bash
# Run continuously: poll on an interval, sync each account only when it changes.
# Set a fast interval with AUTOSAVER_INTERVAL_SECONDS (e.g. 10); default hourly.
spotify-autosaver run

# Run a single sync for every account and exit.
spotify-autosaver sync
```

## Syncing multiple accounts (users file)

To mirror liked songs for several people (e.g. you and friends) from **one**
deployment, list each account's refresh token in a JSON file — by default
`users.json`, or set `AUTOSAVER_USERS_FILE`.

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
- Each person generates their token via the [auth page](#authentication) and
  sends you the entry, which you paste in.
- The `SPOTIPY_CLIENT_ID` in `.env` is the shared **app** identifier; only the
  per-account tokens go in this file.

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
and publishes the image to the **GitHub Container Registry** when you push a
`version/x.y.z` tag:

```bash
git tag version/1.0.0
git push origin version/1.0.0   # → builds ghcr.io/cfazilleau/spotify-autosaver:1.0.0 + :latest
```

The published image:

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
cp .env.example .env             # set SPOTIPY_CLIENT_ID + SPOTIPY_REDIRECT_URI
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

## Configuration reference

| Variable | Default | Description |
| --- | --- | --- |
| `SPOTIPY_CLIENT_ID` | — | **Required.** Spotify app client id. |
| `SPOTIPY_REDIRECT_URI` | *(Pages URL)* | Must match the dashboard and the auth page's URL. |
| `AUTOSAVER_USERS_FILE` | `users.json` | JSON file of accounts to sync. |
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
- OAuth scopes used: `user-library-read`, `playlist-read-private`,
  `playlist-modify-public`, `playlist-modify-private`.

## License

[MIT](LICENSE)
