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

All configuration lives in a single **`settings.json`** — client id, global
playlist settings, and the list of accounts to sync. Copy the example and fill
it in:

```bash
cp settings.example.json settings.json
```

```json
{
  "client_id": "your_spotify_app_client_id",
  "redirect_uri": "https://<username>.github.io/Spotify-autosaver/",
  "track_count": 100,
  "playlist_name": "Liked Songs (Latest 100)",
  "playlist_public": false,
  "interval_seconds": 10,

  "users": [
    { "name": "me", "refresh_token": "AQ...my-token" },
    { "name": "alex", "refresh_token": "AQ...alex-token", "playlist_name": "Alex latest 100" }
  ]
}
```

- `client_id` and a non-empty `users` list are **required**; everything else is
  optional and has a default (see [Configuration reference](#configuration-reference)).
- Top-level keys are the **global defaults**; each entry in `users` may override
  `playlist_name`, `playlist_id`, `track_count`, `playlist_public`, or
  `playlist_description` for that account.
- Each account gets its **own** playlist in its **own** Spotify account, its own
  change-detection state, and is polled independently — one failing account never
  stops the others.
- Generate each `refresh_token` with the [auth page](#authentication) below.

> **Security:** `settings.json` holds credentials that can read libraries and
> edit playlists for every listed account. It's git-ignored by default — keep it
> private and mount it read-only (as the compose file does).

## Authentication

Autosaver uses the **Authorization Code with PKCE** flow, so it needs **no client
secret** — only the client id. Accounts authorize through a small static web page
([`docs/index.html`](docs/index.html)) that runs entirely in the browser and
hands each person a refresh token to paste into `settings.json`.

### Host the auth page on GitHub Pages

1. Edit `docs/index.html` and set `CONFIGURED_CLIENT_ID` to your app's Client ID.
2. In the repo: **Settings → Pages → Build and deployment → Source: Deploy from a
   branch**, branch `main`, folder **`/docs`**. Save.
3. Your page goes live at `https://<username>.github.io/Spotify-autosaver/`.
   Add that exact URL to the app's **Redirect URIs** in the dashboard, and use it
   as `redirect_uri` in `settings.json`.

Then anyone (you or a friend) opens the page, clicks **Log in with Spotify**,
approves, and copies the generated `{ "name": ..., "refresh_token": ... }` entry
to send you. You paste it into the `users` list. No secret, no server, no local
install needed on their end.

> **Heads-up (Spotify limit):** a Spotify app starts in *Development Mode*,
> capped at **25 users**, and each account's email must be added under
> **User Management** in the [developer dashboard](https://developer.spotify.com/dashboard)
> before it can authorize. More than that requires a quota-extension request.

## Usage

```bash
# Run continuously: poll on an interval, sync each account only when it changes.
# Set a fast interval with "interval_seconds" in settings.json (e.g. 10).
spotify-autosaver run

# Run a single sync for every account and exit.
spotify-autosaver sync
```

By default it reads `settings.json` from the working directory; point it
elsewhere with `AUTOSAVER_SETTINGS_FILE=/path/to/settings.json`.

### Docker (build locally)

With `settings.json` in place (the compose file mounts it):

```bash
docker compose up -d --build   # restarts automatically
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
points at the GHCR image and mounts `settings.json` — no other config needed:

```bash
cp settings.example.json settings.json   # fill in client id + accounts
docker compose pull                       # fetch the latest published image
docker compose up -d                      # run continuously, auto-restart
```

Add or remove friends by editing `settings.json` and running
`docker compose restart`. Or without compose:

```bash
docker run -d --name spotify-autosaver --restart unless-stopped \
  -v "$PWD/settings.json:/app/settings.json:ro" \
  ghcr.io/cfazilleau/spotify-autosaver:latest run
```

**Note on registry permissions:** the first publish creates the package as
**private** and linked to this repo (via the image's
`org.opencontainers.image.source` label). The `read:packages` PAT above is what
your local Docker uses to pull it. In CI, publishing uses the automatic
`GITHUB_TOKEN` — no PAT needed there.

## Configuration reference

Keys in `settings.json`. Top-level keys are global; those marked *(per-account)*
can also be set on an individual entry in `users` to override the global value.

| Key | Default | Description |
| --- | --- | --- |
| `client_id` | — | **Required.** Spotify app client id. |
| `redirect_uri` | *(Pages URL)* | Must match the dashboard and the auth page's URL. |
| `users` | — | **Required.** List of accounts; each needs `refresh_token`, optional `name`. |
| `track_count` | `100` | How many recent liked songs to mirror. *(per-account)* |
| `playlist_name` | `Liked Songs (Latest 100)` | Playlist to find/create. *(per-account)* |
| `playlist_id` | — | Target an existing playlist by id. *(per-account only)* |
| `playlist_public` | `false` | Make the created playlist public. *(per-account)* |
| `playlist_description` | *(auto)* | Description for the created playlist. *(per-account)* |
| `interval_seconds` | `3600` | Poll interval for `run` (seconds). Short values are safe. |

The only environment variable is `AUTOSAVER_SETTINGS_FILE` (path to the settings
file; defaults to `settings.json`).

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
