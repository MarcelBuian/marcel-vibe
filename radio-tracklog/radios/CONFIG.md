# config.json — what every setting does

Every radio has its own `radios/<name>/config.json`. This page explains
each setting once, for all radios.

Three rules apply to every setting:

- **A setting you leave out uses its default.** A Radio Record or Shazam
  radio can skip the OCR settings entirely.
- **Changes take effect when the radio's `watch` starts.** After editing
  a config, stop the running `watch` (Ctrl+C) and start it again.
- **Old layouts are upgraded automatically** on the next run.

## Which settings a radio uses

How a radio finds out what's playing is set by `source.type`. Each type
uses its own group of settings; the rest are ignored.

| Setting | `youtube` (OCR) | `radiorecord` | `shazam` |
|---|---|---|---|
| `enabled`, `timezone` | yes | yes | yes |
| `url` | yes | not used (a note for you) | yes |
| `capture_interval_seconds` | yes | no | yes |
| `source.station`, `source.poll_interval_seconds` | no | yes | no |
| `source.clip_seconds`, `source.confirm_reads` | no | no | yes |
| `ocr_region`, `ocr_layout` | yes | no | no |
| `youtube_lookup`, `download_mp3`, `save_to_yt_playlist` | yes | yes | yes |

## General

### `enabled`
`true` or `false`. Default `true`.

Whether `python3 radio_tracklog.py watch` (with no radio name) includes
this radio. With `false` the radio is skipped there, but
`python3 radio_tracklog.py watch <name>` still runs it on its own.

### `url`
The YouTube live stream to follow. Used by the `youtube` and `shazam`
sources. For a `radiorecord` radio the script doesn't read it; keep the
station's page there as a note.

### `timezone`
Default `"Europe/Malta"`.

The zone every date and time is written in (`songs.csv`, lock and quota
files), whatever zone the computer is set to, so travelling never shifts
the log. Use a zone name (`"Europe/Malta"`, `"UTC"`) or a fixed offset
(`"+02:00"`). Changing it later does not rewrite rows already saved.

## Where the track names come from — `source`

### `source.type`
One of:

- **`"youtube"`** (default) — the stream draws the artist and title on
  screen. The script grabs one video frame per interval and reads that
  text with the computer's built-in OCR. macOS and Windows only.
- **`"radiorecord"`** — a [Radio Record](https://www.radiorecord.ru/)
  station. The script asks the station's public tracklist service
  instead of looking at a stream: exact play times, no misreads, and
  about 28 hours of history, so whatever played while the script was off
  is filled in on the next check.
- **`"shazam"`** — a YouTube live stream that shows no track names at
  all. The script records a short piece of the stream's sound per
  interval and asks Shazam what it is. Tracks Shazam doesn't know are
  missed. Needs the `shazamio` package, which the script installs into
  `.venv` by itself on the first run.

### `source.station` — `radiorecord` only
The station's name as written at the end of its address:
`radiorecord.ru/station/organic` → `"organic"`.

### `source.poll_interval_seconds` — `radiorecord` only
Default `300`. How often, in seconds, to ask the station for its recent
plays. No need to go lower: the station keeps about 28 hours of history.

### `source.clip_seconds` — `shazam` only
Default `15`. How many seconds of sound each read sends to Shazam. The
stream arrives in 5-second pieces, so the real length is rounded up to
the next multiple of 5. Longer clips give Shazam more to work with but
blur two songs together more often around a transition.

### `source.confirm_reads` — `shazam` only
Default `2`. How many reads in a row must name the same song before the
song is logged.

When Shazam doesn't know a track, it often answers with some unrelated
song instead, a different one on almost every read. Requiring two
matching reads in a row keeps those out of `songs.csv`. With `1` every
answer is trusted and wrong songs get logged (and downloaded). With `3`
fewer wrong songs get through, but short tracks are missed more often.

A song has to be heard `confirm_reads` times while it plays, so this
setting works together with `capture_interval_seconds`: a 3-minute track
read every 60 seconds gives about 3 chances, read every 30 seconds about 6.

## How often to read — `capture_interval_seconds`
Default `60`. Used by `youtube` and `shazam`.

Seconds between two reads (one video frame for `youtube`, one sound clip
for `shazam`). 60 suits radios whose songs run 3–5 minutes. Use a
shorter value when a stream shows its track name only briefly, or when
a Shazam radio misses short tracks. For Shazam, one read per minute was
never slowed down by Shazam in testing; much faster rates can be.

## What happens with each new song

### `youtube_lookup`
`true` or `false`. Default `true`.

Look every new song up on YouTube to fill the link and year columns of
`songs.csv`. The mp3 download and the playlist both need that link. Set
`false` for radios whose music isn't on YouTube: the search then finds
only unrelated videos and holds up the radio for about 40 seconds per
new song. The `enrich` command follows this setting too.

### `download_mp3`
- **`enabled`** (default `false`) — download every newly logged song as
  a best-quality mp3 into `radios/<name>/mp3/`, named
  `Artist - Title - Year.mp3`, with cover art and clean artist/title/year
  tags. Downloads run in the background. Backfill missing files anytime
  with `python3 radio_tracklog.py download <name>`.
- **`prefer`** (default `""`) — words that steer which YouTube upload is
  picked for a song, e.g. `"extended mix"` or `"radio edit"`. This
  decides the song's one link (csv, playlist and mp3 all use it) and
  only affects songs logged after you set it.
- **`use_ignore_file`** (default `true`) — skip songs listed in the
  radio's `ignore.txt` and in the shared `global_ignore.txt`. The song is
  still logged in `songs.csv`; only the download is skipped.

### `save_to_yt_playlist`
- **`enabled`** (default `false`) and **`link`** — add every newly
  logged song to the YouTube playlist at `link`. Needs the one-time
  Google authorization described in the main README ("mirror the songs
  into a YouTube playlist").
- **`use_ignore_file`** (default `true`) — skip songs listed in
  `ignore.txt` / `global_ignore.txt`, as for mp3 downloads.

## Reading the on-screen text — `youtube` source only

### `ocr_region`
Default `{"x": [0.12, 0.75], "y": [0.02, 0.4]}`.

Where the "now playing" text sits in the video frame. `x` is the
left-to-right range and `y` the bottom-to-top range, each as fractions
of the frame's width and height, **measured from the bottom-left
corner**. Text outside this box is ignored. The default fits
Monstercat's bottom-left text and leaves out the cover art.

### `ocr_layout`
How that text is arranged:

- **`artist_line`** — `"top"` (artist above the title, the default) or
  `"bottom"` (title above the artist). A single line is read as
  `Artist - Title`.
- **`align`** — `"left"` (both lines start at the same left edge, the
  default) or `"center"` (the lines are centered on each other). Text
  that doesn't line up is treated as background and dropped.
- **`ignore`** — label texts inside the region that are not names, e.g.
  `["NOW PLAYING"]`.
- **`default_artist`** — the artist to use when the stream shows only a
  title.
- **`always_visible`** — `true` (default) when the text is always on
  screen. Set `false` for streams that show it only briefly per track;
  frames without text then print `no track name on screen` instead of
  `track name not readable`. Pair it with a
  `capture_interval_seconds` short enough to land inside that window.

## Examples

A stream with on-screen names (`monstercat-silk`):

```json
{
  "enabled": true,
  "url": "https://www.youtube.com/watch?v=WsDyRAPFBC8",
  "source": {"type": "youtube"},
  "capture_interval_seconds": 60,
  "download_mp3": {"enabled": true, "prefer": "", "use_ignore_file": true},
  "ocr_region": {"x": [0.12, 0.75], "y": [0.02, 0.4]}
}
```

A Radio Record station (`record-organic`):

```json
{
  "enabled": true,
  "url": "https://www.radiorecord.ru/station/organic/",
  "source": {"type": "radiorecord", "station": "organic", "poll_interval_seconds": 300},
  "download_mp3": {"enabled": true, "prefer": "", "use_ignore_file": true}
}
```

A stream with no names, identified by sound (`gentleman`):

```json
{
  "enabled": true,
  "url": "https://www.youtube.com/watch?v=nBQaYt1FjZs",
  "source": {"type": "shazam", "clip_seconds": 15, "confirm_reads": 2},
  "capture_interval_seconds": 60,
  "download_mp3": {"enabled": true, "prefer": "", "use_ignore_file": true}
}
```
