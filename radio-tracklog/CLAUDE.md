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
left-aligned); aegean-lounge is title on top over "Aegean Lounge
Official", centered; bassport-deep-techno is a "NOW PLAYING" label
(ignored) + one title line with default_artist "Bassport Music". Aegean
only shows its overlay for the first 25 s and last 15 s of a track, hence
its 10 s capture interval and `always_visible: false` (runs of `.` in
between are not a bug). A new song there is confirmed by the second read
inside the 25 s window. Neither new station has a usable chat: `watch`
only. Both have `youtube_lookup: false` — their tracks aren't on YouTube;
the search returns junk and blocks the loop ~40 s per new song. One `watch` process per radio; commands need the radio name.

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
