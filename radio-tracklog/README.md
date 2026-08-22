# Radio Tracklog

Logs the songs played on YouTube 24/7 radio streams and tells you which
songs repeat and **when each song was heard for the first time**. Ships
configured for **"Deep & Melodic House 24/7"** (Monstercat Silk), and any
number of other radios can be added — each one lives in its own folder
under `radios/` with its own settings and song list.

Two independent ways of hearing what's playing:

- **`watch` (recommended, macOS)** — grabs one video frame every N seconds
  and reads the stream's on-screen "now playing" overlay using macOS's
  built-in OCR (the Vision framework — on-device, offline, free, no AI
  service and no API keys). Catches **every** song with its start time.
- **`log`** — captures the live chat with yt-dlp and parses the chat bot's
  track announcements (`@someone loves 'Toast' by Flexible Fire!`). Works
  on any OS, but it's sampled: the bot only speaks when a viewer types
  `!track` or `!love`, so quiet chat means gaps.

Both write the same **`radios/<name>/songs.csv`** — one row per song,
never duplicated, with a first-added date, a play counter, and a
last-played date that update whenever the song repeats. They can run at
the same time and cross-check each other.

## Quick start (new laptop)

Copy this folder, open a terminal, and run:

```bash
cd radio-tracklog
python3 radio_tracklog.py watch
```

That's everything. On first run the script sets itself up — no venv, no
pip, no manual installs, no questions:

- **yt-dlp**: downloaded automatically (standalone build, ~35 MB).
- **ffmpeg**: downloaded automatically (static build, ~30 MB).
- **OCR helper**: `ocr.swift` is compiled automatically (~30s). This needs
  Apple's Command Line Tools — if `swiftc` is missing, run
  `xcode-select --install` once and re-run.
- **radios/monstercat-silk/**: created with a default `config.json`.

The same self-setup keeps things working over time: when YouTube breaks
an old yt-dlp (it regularly does), the script notices the repeated
failures and re-downloads the latest build by itself.

On Windows/Linux only the chat-based `log` mode works (`watch` uses
macOS-only OCR); install ffmpeg/yt-dlp via your package manager if the
auto-download doesn't cover your platform.

## Radios and their settings

Each radio is a folder: `radios/<name>/` containing `config.json` and
`songs.csv`. With a single radio, commands need no arguments; with
several, name the one you mean: `python3 radio_tracklog.py watch chill`.

`config.json` parameters:

```json
{
  "url": "https://www.youtube.com/watch?v=WsDyRAPFBC8",
  "capture_interval_seconds": 60,
  "ocr_region": {"x": [0.12, 0.75], "y": [0.02, 0.4]}
}
```

- **`url`** — the YouTube live stream to follow.
- **`capture_interval_seconds`** — `watch` mode: how often to grab a frame
  and read the overlay. 60 is a good default (songs run 3–5 minutes).
- **`ocr_region`** — `watch` mode: where the now-playing overlay sits in
  the frame, as fractions of width/height **measured from the bottom-left
  corner**. The default matches Monstercat's bottom-left overlay while
  excluding the cover art and the social handle in the top corner. Adjust
  per radio if a stream draws its overlay elsewhere.

**Adding a radio**: run `python3 radio_tracklog.py watch my-radio` — the
folder and a default `config.json` are created — then put the stream's
URL into that `config.json` and run it again.

## Run

### 1. Start watching (macOS)

```bash
python3 radio_tracklog.py watch
```

Prints one line per song change; between changes it prints compact
progress marks so you can see it's alive:

```
[2026-08-22 13:20] NEW song added: Arnie Way & Toutounji — Somebody  (2024)  https://...
....
[2026-08-22 13:24] NEW song added: Dokho — Finding Solane  (2026)  https://...
..?.
```

- `.` — same song still playing (nothing counted, on purpose)
- `?` — frame captured but the overlay couldn't be read
- `x` — capture hiccup (network/stream); recovers by itself

Stop with `Ctrl+C` (prints the stats summary on exit).

### Alternative/extra: chat-based logging

```bash
python3 radio_tracklog.py log
```

Same output format, driven by the chat bot instead of the screen. Useful
on non-macOS machines, or alongside `watch` — both update the same
`songs.csv` without double counting (a song re-announced within 12
minutes counts as the same spin, and songs are matched
case-insensitively across the two sources).

### 2. Get the result — one row per song, no duplicates

```bash
python3 radio_tracklog.py list    # oldest first
python3 radio_tracklog.py stats   # most played first
```

```
first added  plays  last played  year  song
2026-08-21       1  2026-08-21   2026  Enviado Vida — Touch This Feeling
2026-08-21       3  2026-08-24   2024  Flexible Fire feat. Fractures — Toast
```

`first added` never changes; `plays` and `last played` update every time
the song repeats. The same data lives in **`radios/<name>/songs.csv`**
(columns: `first_added,plays,last_played,artist,title,youtube,year`),
kept up to date live — open that file if you just want the playlist.

### Optional: fill in missing YouTube links and years

```bash
python3 radio_tracklog.py enrich
```

New songs get their YouTube link and release year automatically the
moment they're added; `enrich` is the repair tool for rows where that
live lookup failed. Run it anytime — it only touches incomplete rows.

## Artist-name casing (`radios/<name>/artist-casing.txt`)

The on-screen overlay prints everything in CAPITALS, so `watch`
normalizes names to Title Case (`ARNIE WAY & TOUTOUNJI` → `Arnie Way &
Toutounji`, `SOMEBODY` → `Somebody`). Some artists' names really are
uppercase (or lowercase) on purpose — list them in the radio's own
`artist-casing.txt`, one per line with their exact spelling, and the
script keeps that casing. Each radio has its own file (created
automatically) since every station has its own artist roster; the
Monstercat one comes pre-filled with a few known names (PROFF, PRAANA,
zensei, …). When you spot a new all-caps artist in `songs.csv`, check how
they spell themselves (their YouTube/Spotify page) and add them to the
file. Names containing dots or digits (A.M.R) are left untouched
automatically.

## Good to know

- **`songs.csv` is the single source of truth** — to move a radio's
  history to another laptop, copy its folder under `radios/`; the script
  continues where it left off (the newest `last_played` date stops it
  from re-counting the chat backlog after a restart). Only per-song
  totals are kept, not the time of every individual play.
- **The binaries are disposable** — `yt-dlp`, `ffmpeg`, and `.ocr` in
  this folder are auto-downloaded/compiled; they don't need to be copied
  to another machine (but copying them saves the first-run downloads).
- `chat-*.json*` and `.frame.jpg` files inside a radio's folder are
  transient transport files; they're cleaned up automatically, and are
  safe to delete if a crash ever leaves them behind.
- **Chat sampling can be helped**: open the stream in a browser and type
  `!track` in the chat — the `log` mode will catch the bot's answer.
- **Other chat bots**: `log` mode is tuned to Monstercat's bot; edit
  `BOT_AUTHORS` / `TRACK_RE` at the top of the script for other bots.
  `watch` mode has no such dependency — just set `url` and, if needed,
  `ocr_region`.
- The full official rotation of the Monstercat Silk stream is also
  published as a Spotify playlist: https://monster.cat/chillhouse — the
  script tells you what actually played and when; the playlist tells you
  everything that *can* play.
