# Radio Tracklog

Logs the songs played on the YouTube 24/7 radio stream
**"Deep & Melodic House 24/7: Relaxing Music • Chill Study Music"** (Monstercat Silk)
and tells you which songs repeat and **when each song was heard for the first time**.

How it works: the stream's chat bot (`@monstercatbot`) names the currently
playing track whenever a viewer types `!track` or `!love` in the live chat, e.g.

> @someone loves 'Toast' by Flexible Fire feat. Fractures!

This script captures the live chat with yt-dlp, extracts those bot messages,
and maintains **`tracklog/songs.csv`** — one row per song, never duplicated,
with a first-added date, a play counter, and a last-played date that update
whenever the song repeats. It can also look up each song's YouTube link and
release year.

## Quick start (new laptop)

Copy this folder (without `.venv`, if present), open a terminal, and run:

```bash
cd radio-tracklog
python3 -m venv .venv
.venv/bin/pip install yt-dlp
python3 radio_tracklog.py log
```

That's everything — the first two `.venv` lines are one-time setup, the
last line starts the logger. Details below.

On **Windows** the setup lines are instead:

```bat
py -m venv .venv
.venv\Scripts\pip install yt-dlp
py radio_tracklog.py log
```

## Requirements

- Python 3.9 or newer (`python3 --version` to check)
- Internet connection
- Nothing else — yt-dlp is installed into a local `.venv` folder by the
  setup lines above

## Run

### 1. Start logging

```bash
python3 radio_tracklog.py log
```

Leave it running (hours or days — the longer, the better the data).
Every detected spin is printed as it happens — either a brand-new song or
a counter increment:

```
[2026-08-22 12:24] NEW song added: rshand — Unworthy  (2025)  https://www.youtube.com/watch?v=vc_WFWM9XGc
[2026-08-22 12:31] play #2: Enviado Vida — Touch This Feeling
```

New songs are looked up on YouTube right away, so their link and year land
in `songs.csv` (and on screen) the moment they are added.

Stop with `Ctrl+C` (it prints the stats summary on exit).
If the stream or connection hiccups, the script reconnects by itself.

If yt-dlp keeps failing right after starting (YouTube regularly breaks old
yt-dlp versions), the script downloads the latest standalone yt-dlp build
from GitHub into this folder automatically and carries on with that — no
manual updating needed.

### 2. Get the result — one row per song, no duplicates

```bash
python3 radio_tracklog.py list
```

```
first added  plays  last played  year  song
2026-08-21       1  2026-08-21   2026  Enviado Vida — Touch This Feeling
2026-08-21       3  2026-08-24   2024  Flexible Fire feat. Fractures — Toast
```

Oldest first. `first added` never changes; `plays` and `last played` are
updated every time the song repeats. This is the same data as
**`tracklog/songs.csv`** (columns:
`first_added,plays,last_played,artist,title,youtube,year`), which is kept up
to date live while the logger runs — open that file if you just want the
playlist.

### Optional: add YouTube links and release years

```bash
python3 radio_tracklog.py enrich
```

New songs get their YouTube link and year automatically while logging, so
normally you won't need this. It exists as a repair tool: for every song
still missing that info (e.g. the live lookup failed, or rows from before
this feature), it searches YouTube via yt-dlp and fills the `youtube` and
`year` columns in `songs.csv`. Run it anytime — it only touches songs with
missing info. The chat bot itself only announces title + artist, so these
lookups are how the extra details get in.

### 3. See which songs repeat the most

```bash
python3 radio_tracklog.py stats
```

```
plays  first seen       last seen        track
    7  2026-08-21T14:42 2026-08-24T09:10 Enviado Vida — Touch This Feeling
    3  2026-08-21T15:29 2026-08-23T22:01 Flexible Fire feat. Fractures — Toast
```

## Good to know

- **`tracklog/songs.csv` is the single source of truth** — one row per
  song, no duplicates. To move your history to another laptop, copy that
  one file; the script continues where it left off (the newest
  `last_played` date is what stops it from re-counting YouTube's chat
  backlog after a restart). Note: only per-song totals are kept, not the
  time of every individual play.
- **The log is sampled.** The bot only names the track when someone in chat
  asks it, so quiet periods leave gaps. Counts are a lower bound. Bonus: on
  every start YouTube sends a backlog of recent chat, so you also get some
  history from before you started the script.
- **You can help the sampling**: open the stream in a browser and type
  `!track` in the chat yourself — the script will catch the bot's answer.
- `tracklog/chat-*.json*` files are raw chat dumps — just the transport the
  script reads from while logging. They are deleted automatically when a
  session ends; if you ever see leftovers (e.g. after a crash), they are
  safe to delete.
- **Other streams**: `python3 radio_tracklog.py log --url <youtube-live-url>`
  works for any 24/7 stream whose bot announces tracks as `'Title' by Artist`
  (edit `BOT_AUTHORS` / `TRACK_RE` at the top of the script for other bots).
- The full official rotation of this stream is also published as a Spotify
  playlist: https://monster.cat/chillhouse — the script tells you what
  actually played and when; the playlist tells you everything that *can* play.
