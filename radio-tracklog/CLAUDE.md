# radio-tracklog — notes for Claude

## RULE: fix the code before fixing the data
When a bad row shows up in `radios/*/songs.csv` (OCR junk, duplicate,
wrong casing), ALWAYS fix the cause in `radio_tracklog.py` (or
`ocr.swift` / `artist-casing.txt`) FIRST, and only then repair the CSV.
A repaired CSV without a code fix means the same junk returns on the
next capture. After code changes, remind Marcel to restart his running
`watch`/`log` process — it doesn't pick up code edits until restarted.

## HISTORY.md — keep it current
`HISTORY.md` is the project's memory inside git (Marcel's request,
2026-11-11): his intentions, decisions and their reasons, experiments,
what worked and what didn't, radios considered, test results. Claude's
own memory folder does not move with the repository, so anything a
future session on another machine (the Windows box) would need goes
there. After any session that decides something, tries something, or
learns something non-obvious, add a dated entry — in plain language
Marcel can read, not code notes (those stay in this file).

## Config reference
`radios/CONFIG.md` explains every config.json key for Marcel (one page for
all radios; README only points to it). When adding or changing a key,
update it there AND in the DEFAULT_CONFIG comments.

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
of `no track name on screen` in between are not a bug; a new song is
confirmed by a second read inside that window). Set `youtube_lookup: false` on stations whose
tracks aren't on YouTube — the search returns junk and blocks the loop
~40 s per new song. One `watch` process per radio; commands need the radio name.
Bare `watch` (no name) = `watch_all()` supervisor (added 2026-09-16): spawns
`watch <name>` as a child (own session, so it gets SIGINT only from us) for
every radio with top-level `"enabled": true` in config.json, prefixes each
output line with `[name]` (switching writer mid-line forces a newline; the
watches print whole lines only since 2026-11-13), tees everything with a timestamp into
`watch.log` (gitignored), restarts a child that dies after >60 s, leaves one
that dies at once. Per-radio `.watch.lock` still prevents double watches.

## Console output: one line per read (2026-11-13)
Marcel wants the console to say what every radio plays at any moment,
not only when a song starts. So all three watch loops print exactly one
line per read: `record_spin()`'s line when a spin counts (`NEW song
added` / `play #N`), otherwise `Housekeeping.status()` — `still
playing: A — T`, `unconfirmed (n of N reads): A — T`, `Shazam has no
match`, `track name not readable`, `could not capture the stream (…)`.
`radiorecord` prints `still playing` with the newest play when a poll
brings nothing new. The old one-character progress marks (`.` `+` `?`
`x` `♪`) are gone — don't bring them back, and give any new branch of a
watch loop its own status line. Status lines never touch songs.csv.
`watch.log` grows by an estimated 0.5 MB a day with four radios (it was
0.18 MB on 2026-11-12, with the marks); there is no rotation yet.

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

## Shazam source (`source.type: shazam`, added 2026-11-11)
For YouTube streams with no overlay and no chat bot (Gentleman Radio,
radios/gentleman). `watch` dispatches to `watch_shazam()`: every
capture_interval_seconds `grab_audio()` takes the newest
`source.clip_seconds` (15) of the AUDIO_FORMAT HLS stream (via `newest_segments()`,
shared with `grab_frame()`) as 16 kHz mono WAV, and `shazam_read()` runs
`shazam_read.py` in `.venv` (one subprocess per read; JSON line out).
`ensure_shazam()` pip-installs shazamio into `.venv` on first use (creates
the venv with the running Python if missing). shazamio 0.9 / shazamio-core
2.0 work on Python 3.14 and 3.15 (an older core segfaulted on 3.14).
Rules, from the 2026-11-06 prototype: when Shazam doesn't know a track it
returns a *different* famous song on nearly every read, so EVERY song
needs `source.confirm_reads` (2) consecutive agreeing reads — no "known song counts at once"
shortcut as in OCR watch, and no "1 of the last 2" rule (a wrong answer
came back with one read in between). Any failed or no-match read resets
the pair. A song unheard for > 3 intervals (min 3 min) must be re-confirmed; the
12-minute same-spin window in `add_spin()` keeps that from double
counting. Names keep Shazam's casing (`_recase()` with
artist-casing.txt only, never `normalize_name()`'s SHOUTING fix).
Shazam errors (`ShazamError`) keep the manifest and print their reason;
capture errors reset the manifest. Every raw read
(answer / NO MATCH / ERROR / CAPTURE FAILED) is appended to
`radios/<name>/.shazam-reads.tsv` (gitignored) — check it before
judging a run of `unconfirmed` lines or a doubtful song. Since 2026-11-12 each line also
carries tab-separated `name=value` fields: `clip_start` (stream time of
the clip's first segment from `hls_tail()`: PROGRAM-DATE-TIME as Unix
time, else media sequence x target duration), `shazam_s` (lookup time;
rises when Shazam throttles) and, for a match, `offset` (seconds into
the track), `timeskew`, `freqskew`, `matches` (candidate count) from
`shazam_read.py`. Older lines have only time + answer. On a true match
`offset` grows by exactly the growth of `clip_start` (measured: within
0.02 s) and both skews are ~0.0001; a wrong answer seen once had skews
of 0.007-0.05. These fields are RECORDED ONLY so far — the plan is to
require offset progress before a song counts, after checking a day of
data against known wrong songs (see HISTORY.md, 2026-11-12). The helper
runs per read, so a running watch picks up shazam_read.py edits at once
(keep its JSON backward compatible); radio_tracklog.py edits need a
restart. One read per
minute was never throttled; bursts of ~20 requests were (≈30 s each).

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
Two lists per radio, same format, merged by `load_ignore()`: the radio's
`radios/<name>/ignore.txt` and the shared `global_ignore.txt` next to the
script (`GLOBAL_IGNORE_FILE`, created on first run, added 2026-09-15).
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
