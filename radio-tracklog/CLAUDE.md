# radio-tracklog — notes for Claude

## RULE: fix the code before fixing the data
When a bad row shows up in `radios/*/songs.csv` (OCR junk, duplicate,
wrong casing), ALWAYS fix the cause in `radio_tracklog.py` (or
`ocr.swift` / `artist-casing.txt`) FIRST, and only then repair the CSV.
A repaired CSV without a code fix means the same junk returns on the
next capture. After code changes, remind Marcel to restart his running
`watch`/`log` process — it doesn't pick up code edits until restarted.

## Known OCR junk patterns (already defended in code)
The `watch` mode OCRs a video frame; one-frame misreads produce:
leading/trailing junk chars (`• Name`, `Name*`, `Name -`, `Name®`),
unbalanced parens (`Song (Remix`), and transition-frame garbage where
artist/title are nonsense. Defenses live in `clean_ocr_text()`,
`read_overlay()` (adjacency + left-edge + letterless filters), and the
two-consecutive-reads confirmation for never-seen songs in `cmd_watch()`.
Extend those, don't bypass them.

## Per-radio overlay layout
`read_overlay()` takes the radio's `ocr_layout` (`artist_line`
top/bottom, `align` left/center, `ignore` labels, `default_artist`,
`always_visible`) next to `ocr_region` — add options there, never
station-specific code. monstercat-silk is the default (artist on top,
left-aligned). The options exist for stations whose overlay differs:
`artist_line: bottom` + `align: center` for title-over-artist layouts,
`ignore` for label texts like "NOW PLAYING", `default_artist` for
single-line overlays, and `always_visible: false` (with a short capture
interval) for stations that only show the name briefly per track (runs
of `.` in between are not a bug; a new song is confirmed by a second
read inside that window). Set `youtube_lookup: false` on stations whose
tracks aren't on YouTube — the search returns junk and blocks the loop
~40 s per new song. One `watch` process per radio; commands need the radio name.

## Artist name casing
The overlay is ALL CAPS; `normalize_name()` title-cases it. Artists with
intentional unusual casing go in the radio's `artist-casing.txt`. Never
guess a casing: verify against the linked YouTube video title
(`./yt-dlp --skip-download --print "%(title)s" <url>`) before adding.

## Concurrency
`watch` and `log` may run at the same time; they sync through the CSV
(`SongBook.refresh()` + the 12-minute same-spin window). When editing
`songs.csv` while a logger runs, keep the write atomic (tmp + replace)
— the running process picks the file up on its next spin.

## Clock / timezone changes
Timestamps are naive local time. On 2026-08-28 the Mac's zone switched
(UTC+3 -> Europe/Malta) at 11:45 and the wall clock fell back an hour;
the old `add_spin()` backlog guard (`ts <= max_last`) then dropped every
`watch` spin for an hour, printed as a long row of `.`. Fixed: `watch`
passes `live=True` (no backlog guard), same-spin uses `abs()`, and
`warn_clock_skew()` announces future-dated rows at startup. Don't
reintroduce a "newest row wins" check on the live OCR path.
All times now go through `now()`/`today()`/`from_epoch()`, which use the
`timezone` from config.json (default Europe/Malta) — never call
`dt.datetime.now()` / `date.today()` / `fromtimestamp()` directly.
Rows stamped 2026-08-26 16:00 .. 2026-08-28 12:44 were written in +0300
and have been shifted -1h to Malta time.

## macOS and Windows
`watch` runs on both. The OCR helper is `ocr.swift` (Vision) on macOS and
`ocr.ps1` (Windows.Media.Ocr via Windows PowerShell 5.1) on Windows;
`ensure_ocr()` returns the command prefix, `read_overlay()` parses the
same "x y w<TAB>text" lines from either. Keep the two helpers' output
format identical (fractions from the BOTTOM-LEFT, y = bottom edge of the
text box). ffmpeg auto-downloads on both (martin-riedl.de for macOS,
BtbN GitHub builds for Windows); the single-instance lock uses fcntl on
macOS and msvcrt on Windows. Only macOS can be tested from this machine —
Windows changes need a run on a real Windows box.

## Radio Record source (`source.type: radiorecord`)
`watch` dispatches to `watch_radiorecord()`: it polls
`radiorecord.ru/api/station/history/?id=<id>` (400 plays, ~28 h, unix
times, `noShow` = jingles) and feeds each play through `record_spin()`
with `live=False`, so the chat-backlog rule ("not newer than the newest
row = already counted") is what makes re-polling idempotent — keep it.
`record_names()` maps the API's `A/B` artist joins to `A & B` and `rmx`
to `Remix` before `normalize_name()`. Replies are gzipped regardless of
headers (`record_api()` inflates). Between-reads bookkeeping (progress
marks, background mp3s, playlist catch-up) lives in `Housekeeping`,
shared by both watch paths — don't re-inline it.

## yt-dlp speed on this Mac
The standalone yt-dlp binary (yt-dlp_macos) has a ~77 s cold start here
(even `--version`), because it unpacks its bundled Python every launch —
crippling for enrich/download across hundreds of songs. Fix in place: a
`.venv` built with Homebrew python3.14 holding the current yt-dlp
(`.venv/bin/pip install -U yt-dlp`), which `find_ytdlp()` now prefers over
the standalone (still the fallback + auto-repair target). Refresh it with
pip if YouTube extraction ever breaks. `record_spin()` caps concurrent
background mp3 downloads at MAX_PARALLEL_DOWNLOADS so a Radio Record
backfill can't spawn hundreds of yt-dlp processes at once.

## ignore.txt matching
`load_ignore()` accepts tracklist lines (`[R] 01:02:30 - A, B - Title`);
`is_ignored()` matches by video id, exact folded name, or
`song_signature()` (same base title + ≥1 shared artist, version suffixes
and country tags like "(CH)"/"(BR)" stripped — 2026-09-05: "Marc Samuel
(CH)" failed to match "Marc Samuel"). A bare line without " - " is a
title-only entry (any artist). `ignore` command = apply the list to
existing mp3s. Marcel
pastes the tracklists of sets he already played into a radio's ignore.txt
so repeats are neither downloaded nor added to the playlist.

## YouTube link matching (2026-09-05)
14 of 316 record-organic songs had got a news clip, a game video, an Oracle
DB tutorial, a Twitch DJ set, a podcast… because `lookup_song()` took the
first search hit. Now `_yt_search()` is a cheap `--flat-playlist` search
(8 results: title, channel, duration) and `video_matches()` gates every
candidate: `_core(title)` must equal (or `_same_name()`-nearly equal) a
`_title_segments()` part of the video title; an artist must be in the title
or channel, or the channel must be a `- Topic` auto-channel ("Release -
Topic" has no artist); 1–20 min; artist-only-in-title needs ≤ 6 leftover
words. Topic +4, own channel +3. Regression cases (real search results) are in `tests_video_matches.py` —
run it before touching the matcher, and never go back to "first hit wins". `verify` re-checks stored links
via oEmbed (`video_info()`, no yt-dlp) and clears wrong ones; then `enrich`
+ `download`. Watches load the code at start — restart them after edits.
