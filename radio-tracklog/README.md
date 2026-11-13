# Radio Tracklog

Logs the songs played on YouTube 24/7 radio streams and tells you which
songs repeat and **when each song was heard for the first time**. Ships
configured for **"Deep & Melodic House 24/7"** (Monstercat Silk) and
**"Aegean Lounge Late Night Radio"**, and any number of other radios can
be added — each one lives in its own folder under `radios/` with its own
settings and song list.

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

## Quick start (new laptop — Mac or Windows)

Copy this folder, open a terminal, and run:

```bash
cd radio-tracklog
python3 radio_tracklog.py watch        # macOS — all enabled radios in one terminal
python radio_tracklog.py watch         # Windows (Python 3.9+ from python.org or the Store)
```

That's everything. On first run the script sets itself up — no venv, no
pip, no manual installs, no questions:

- **yt-dlp**: downloaded automatically (standalone build, ~35 MB).
- **ffmpeg**: downloaded automatically (static build, ~30 MB).
- **OCR helper**: on macOS `ocr.swift` is compiled automatically (~30s;
  needs Apple's Command Line Tools — if `swiftc` is missing, run
  `xcode-select --install` once and re-run). On Windows `ocr.ps1` uses
  the OCR engine built into Windows 10/11 through the stock PowerShell —
  nothing to compile or install (it needs a Windows language pack with
  OCR, which English and most others include).
- **radios/monstercat-silk/**: created with a default `config.json`.
- **Shazam helper** (only for radios with `"source": {"type": "shazam"}`):
  `shazam_read.py` needs the `shazamio` package, so on first use the
  script creates `.venv` (if it doesn't exist yet) and pip-installs
  `shazamio` into it — one-time, ~20 s.

The same self-setup keeps things working over time: when YouTube breaks
an old yt-dlp (it regularly does), the script notices the repeated
failures and re-downloads the latest build by itself.

Everything works the same on both systems; the `radios/` folder is
portable between them (copy it, keep the same `timezone`). On Linux only
the chat-based `log` mode works (no built-in OCR); install ffmpeg via your
package manager there.

## Radios and their settings

Each radio is a folder: `radios/<name>/` containing `config.json` and
`songs.csv`. With a single radio, commands need no arguments; with
several, name the one you mean: `python3 radio_tracklog.py watch chill`.

**Every `config.json` setting is explained in
[radios/CONFIG.md](radios/CONFIG.md)** — one reference for all radios:
what each key does, its default, and which kind of radio uses it.

The short version: `source.type` decides how a radio learns what's
playing — `youtube` reads the on-screen track name with OCR,
`radiorecord` asks a Radio Record station's tracklist service, `shazam`
identifies the stream's sound when nothing is shown on screen. The rest
decides what happens with each new song (`youtube_lookup`,
`download_mp3`, `save_to_yt_playlist`). Songs to skip go in the radio's
`ignore.txt` or the shared `global_ignore.txt` (formats explained in
those files' headers); `python3 radio_tracklog.py ignore <radio>` shows
which logged songs the lists match and deletes their mp3s (`--check`
only lists).

The included radios:

- **`monstercat-silk`** — Monstercat Silk "Deep & Melodic House 24/7".
  The overlay is always on screen: artist on top, title below,
  left-aligned in the bottom-left corner.
- **`record-organic`** — Radio Record "Organic" (organic house, "in the
  style of Tim Green and Sebastien Leger"), via the `radiorecord` source.
  Commercial releases, so YouTube lookup and mp3 downloads are on; the
  API spells artists `LOST DESERT/HERMANEZ` — the script turns that into
  `Lost Desert & Hermanez` (and `rmx` into `Remix`).
- **`record-ibiza`** — Radio Record "Innocence" (techno, minimal, deep,
  "sound like Solomun, Boris Brejcha and Nina Kraviz"); `ibiza` is the
  station's URL name on radiorecord.ru. Same `radiorecord` source and
  settings as record-organic.
- **`gentleman`** — Gentleman Radio, deep house (its own GNTLMN label plus
  well-known house), via the `shazam` source: the stream shows no track
  names and has live chat off. A 2-hour test (2026-11-06) confirmed 19
  songs, 1 of them doubtful. mp3 downloads on; no YouTube playlist set
  yet.

**One terminal for all radios**: `python3 radio_tracklog.py watch` with no
name runs every radio whose `config.json` has `"enabled": true`, each as
its own process, with every output line tagged `[radio-name]`. The same
output (plus a timestamp per line) is appended to `watch.log` next to the
script. Ctrl+C stops all of them; a radio that dies after running for a
while is restarted automatically, one that fails right at start stays
down so a config mistake is visible. Set `"enabled": false` in a radio's
`config.json` to leave it out; `python3 radio_tracklog.py watch <name>`
still runs that radio on its own regardless of the flag.

Other commands still need the radio's name when several exist
(`python3 radio_tracklog.py ignore record-organic`), except `download`,
which also does every radio with `download_mp3` on when run bare.

**Adding a radio**: run `python3 radio_tracklog.py watch my-radio` — the
folder and a default `config.json` are created — then put the stream's
URL into that `config.json` and run it again.

## Run

### 1. Start watching (macOS / Windows)

```bash
python3 radio_tracklog.py watch
```

Every read prints one line, so the newest line of a radio always says
what it is playing:

```
[2026-11-13 14:59] still playing: Approaching Black — What You Need
[2026-11-13 15:00] play #76: Flexible Fire — Costa Serena
[2026-11-13 15:01] still playing: Flexible Fire — Costa Serena
[2026-11-13 15:04] unconfirmed (1 of 2 reads): Dokho — Finding Solane
[2026-11-13 15:05] NEW song added: Dokho — Finding Solane  (2026)  https://...
```

- `NEW song added` / `play #N` — a song started and was counted. Only
  these lines change `songs.csv`.
- `still playing` — the same song as on the read before (nothing
  counted, on purpose).
- `unconfirmed (1 of 2 reads)` — a name never seen before; the script
  waits for a second identical read before adding it (one-frame OCR
  misreads die here, real new songs just get logged one capture later).
- `track name not readable` — frame captured but the overlay couldn't be
  read.
- `could not capture the stream …` — network/stream hiccup; recovers by
  itself.
- `mp3 saved: …` — a background mp3 download finished (with
  `download_mp3` on, new songs get a `[mp3 downloading...]` tag on their
  line; a failed download prints `mp3 download FAILED` so you know to
  backfill later).

On a `shazam` radio the lines mean the same, except: `unconfirmed` is
printed for **every** song's first read (even one already in the list — a
single Shazam answer is never trusted), so many `unconfirmed` lines with
changing names mean Shazam doesn't know the track that is playing.
`Shazam has no match` means it gave no answer for the clip; if the lookup
itself fails (network, throttling), the reason is printed. Every raw
Shazam answer is also kept in `radios/<name>/.shazam-reads.tsv`.

On a `radiorecord` radio every poll prints the songs that started since
the last poll, or `still playing` with the newest one when there are none.

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

How a song gets its link: the script searches YouTube and accepts a result
only if the song title is a whole segment of the video title (not just words
inside a longer headline), the artist appears in the title or channel — or
the channel is YouTube's auto-generated `… - Topic` for that release — and
the video is track-length (1–20 min, so never a DJ set). Official/Topic
uploads win over re-uploads; a one-letter difference in a long title
(`Lost Dream`/`Lost Dreams`) is tolerated, remix names in brackets may
differ. Nothing convincing → the song stays without a link (and without an
mp3) rather than getting a wrong one; `enrich` retries those later.
`python3 radio_tracklog.py verify <radio>` re-checks all stored links the
same way and clears the wrong ones (`--check` only lists), after which
`enrich` and `download` redo them.


```bash
python3 radio_tracklog.py enrich
```

New songs get their YouTube link and release year automatically the
moment they're added; `enrich` is the repair tool for rows where that
live lookup failed. Run it anytime — it only touches incomplete rows.

### Optional: backfill missing mp3s

```bash
python3 radio_tracklog.py download            # all radios with download_mp3 on
python3 radio_tracklog.py download my-radio   # this radio, even if it's off
```

Downloads a best-quality mp3 for every logged song that isn't in the
radio's `mp3/` folder yet — songs logged before `download_mp3` was
turned on, or whose live download failed. Rerun-safe: existing files are
never downloaded twice.

### Optional: mirror the songs into a YouTube playlist

Put a playlist link into the radio's `config.json`:

```json
  "save_to_yt_playlist": {"enabled": true, "link": "https://www.youtube.com/playlist?list=PL...", "use_ignore_file": true}
```

Adding videos to a playlist writes to your YouTube account, which Google
only allows through its official API after a one-time authorization
(~10 minutes in the Google Cloud console, done once per Google account):

1. **Project**: at https://console.cloud.google.com/ → project picker →
   "New project" → any name → Create (and make sure it's selected).
2. **Enable the API** (easy to miss — nothing works without it):
   *APIs & Services* → *Library* → search **"YouTube Data API v3"** →
   Enable.
3. **Consent screen**: the OAuth pages live under "Google Auth Platform",
   which is NOT in the products menu — get there via *APIs & Services* →
   *OAuth consent screen*, or directly:
   https://console.cloud.google.com/auth/overview. Run the wizard:
   app name + your email as support email → Audience: **External** →
   your email as contact → Finish → Create.
4. **Publish it** (otherwise Google expires the login every 7 days): the
   console requires a homepage and privacy-policy URL before it lets you
   publish — any page of yours works, e.g. your GitHub profile
   (`https://github.com/YOURNAME`) in both fields on the **Branding**
   page, plus `github.com` under **Authorized domains**; press **Save**
   (bottom of the page — the fields don't count until saved). Then on
   the **Audience** page press **"Publish app"**.
   *Can't publish? Fallback that works immediately: on the Audience page
   add yourself under **Test users** — everything works the same, you
   just re-authorize weekly (the script tells you when).*
5. **The client**: **Clients** page (sidebar) → "+ Create client" →
   Application type: **"TVs and Limited Input devices"** → Create. Copy
   `google-oauth.json.example` to `google-oauth.json` and paste the
   shown client id and secret into it.
6. Run `python3 radio_tracklog.py playlist` — it prints a google.com/device
   code to type once in your browser, then adds every logged song that's
   not in the playlist yet (rerun-safe; it reads the playlist first, so
   tracks that are already in it are never re-added). The "unverified
   app" warning during authorization is expected — it's your own app.

The sync also maintains two files in the radio's folder:

- `playlist-videos.txt` — a local mirror of what's in the playlist
  (video id + title). The live loggers check it before adding, which is
  what makes live additions duplicate-proof; run `playlist` once before
  relying on live adds, and rerun it whenever you edit the playlist by
  hand so the mirror stays truthful.
- `playlist-extra.txt` — tracks that are in the playlist but not in
  `songs.csv`, just to keep an eye on what got in from elsewhere.

From then on, the live `watch`/`log` adds each NEW song to the playlist
the moment it's logged (`[playlist ok]` on the song's line). Errors on a
single song are reported and skipped — they never block the rest.
Google's free API quota allows ~200 playlist additions per day; when
it's hit, the script notes the day and a running `watch` automatically
resumes the remaining additions the next day (a few per capture cycle),
no action needed. Both Google secret files are gitignored.

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

You don't have to guess: every logged song carries its YouTube link, and
the uploader's own spelling — the artist's name in the video title
(`Blue Haze - Amber Glow [Silk Music]`), in their channel name, or in a
`<Artist> - Topic` channel — is the reference. The `casing` command
checks all of them and fixes the file and `songs.csv` (mp3 file names
included):

```bash
python3 radio_tracklog.py casing --check   # report only
python3 radio_tracklog.py casing           # apply
```

It takes a majority across an artist's songs, so one odd upload cannot
flip a name, and it tells you which listed names no linked video could
confirm. Video titles are fetched once and cached in
`radios/<name>/.video-titles.txt`. Restart a running `watch` afterwards —
it loads the casing file at startup.

## Good to know

- **`songs.csv` is the single source of truth** — to move a radio's
  history to another laptop, copy its folder under `radios/`; the script
  continues where it left off (the newest `last_played` date stops it
  from re-counting the chat backlog after a restart). Only per-song
  totals are kept, not the time of every individual play.
- **Timestamps are wall-clock time in the configured `timezone`**, not
  the Mac's. If they still end up ahead of the clock (zone setting
  changed, Mac clock corrected), the script says so at startup; `watch`
  keeps counting, while `log` ignores chat until the clock has caught up
  with the newest row.
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
  `ocr_region` and `ocr_layout`.
- The full official rotation of the Monstercat Silk stream is also
  published as a Spotify playlist: https://monster.cat/chillhouse — the
  script tells you what actually played and when; the playlist tells you
  everything that *can* play.
