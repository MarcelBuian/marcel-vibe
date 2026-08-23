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
