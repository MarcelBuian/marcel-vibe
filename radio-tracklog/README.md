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

## Requirements

- Python 3.9 or newer (`python3 --version` to check)
- Internet connection
- Nothing else — yt-dlp is installed into a local `.venv` folder in step 1

## Setup (one time, per laptop)

Open a terminal in this folder and run:

```bash
cd "$(dirname "$0")" 2>/dev/null; cd /path/to/MarcelVibe/radio-tracklog   # this folder
python3 -m venv .venv
.venv/bin/pip install yt-dlp
```

On **Windows** use instead:

```bat
py -m venv .venv
.venv\Scripts\pip install yt-dlp
```

## Run

### 1. Start logging

```bash
python3 radio_tracklog.py log
```

Leave it running (hours or days — the longer, the better the data).
Every detected spin is printed as it appears (`NEW` = first time ever seen):

```
[2026-08-22 12:24] NEW rshand — Unworthy
[2026-08-22 12:31]     Enviado Vida — Touch This Feeling
```

Stop with `Ctrl+C` (it prints the stats summary on exit).
If the stream or connection hiccups, the script reconnects by itself.

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

For every song that doesn't have them yet, this searches YouTube (via
yt-dlp) and fills the `youtube` and `year` columns in `songs.csv`. Run it
again anytime — it only looks up songs that are still missing info. The
chat bot itself only announces title + artist, so this lookup is how the
extra details get in.

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
