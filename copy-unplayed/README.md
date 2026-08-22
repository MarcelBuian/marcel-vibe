# Copy Unplayed

Copies all mp3s from a source folder to a destination folder, **skipping**
the songs listed in an "already played" text file.

Needs only Python 3 — no setup, no installs.

## Run

```bash
python3 copy_unplayed.py FOLDER_SOURCE FOLDER_DEST FILE_ALREADY_PLAYED
```

Example:

```bash
python3 copy_unplayed.py \
    ~/Music/yt-dlp/DeepAndMelodicHouse \
    ~/Music/yt-dlp/ToPlay-DeepAndMelodicHouse \
    ~/Music/yt-dlp/DeepAndMelodicHouse/"already played.txt"
```

## The already-played file

One song per line as `Artist - Title`, optionally with a timestamp in front
(tracklist style):

```
00:13:40 A.M.R - Voyager
Marsh - Belle
```

## Good to know

- Matching is fuzzy: case doesn't matter, and suffixes like
  `(Extended Mix)`, `[Silk Music]` or the year in the filename don't
  prevent a match. Every fuzzy match is printed so you can check it.
- Rerun-safe: run it again after the played list grows — it only copies
  what's new, never duplicates.
- At the end it lists played entries that matched no file, so you can
  spot typos or missing songs.
