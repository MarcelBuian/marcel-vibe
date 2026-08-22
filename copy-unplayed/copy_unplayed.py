#!/usr/bin/env python3
"""Copy songs from a folder, skipping the ones listed in an already-played file.

Usage:
  python3 copy_unplayed.py FOLDER_SOURCE FOLDER_DEST FILE_ALREADY_PLAYED

Example:
  python3 copy_unplayed.py \
      ~/Music/yt-dlp/DeepAndMelodicHouse \
      ~/Music/yt-dlp/ToPlay-DeepAndMelodicHouse \
      ~/Music/yt-dlp/DeepAndMelodicHouse/"already played.txt"

The already-played file has one song per line as "Artist - Title", with an
optional timestamp in front (tracklist style), e.g.:
  00:13:40 A.M.R - Voyager

Matching against mp3 filenames ("Artist - Title - Year.mp3") is fuzzy:
case-insensitive, and suffixes like "(Extended Mix)", "[Silk Music]" or a
different year don't prevent a match. Every fuzzy match is printed so you
can check it. Rerun-safe: files already in the destination are not copied
again.
"""

import argparse
import os
import re
import shutil
import sys
import unicodedata


def norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).strip().lower())


def load_played(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = re.sub(r"^\d{1,2}:\d{2}(:\d{2})?\s+", "", line)  # drop timestamp
            entry = entry.lstrip("- ").strip()
            if entry:
                entries.append(norm(entry))
    return entries


def match_played(stem, played):
    """Return the played-entry contained in this filename stem, else None."""
    s = norm(stem)
    for entry in played:
        i = s.find(entry)
        if i == -1:
            continue
        end = i + len(entry)
        if end == len(s) or not s[end].isalnum():  # no cut mid-word
            return entry
    return None


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("folder_source", help="folder with the mp3 files")
    p.add_argument("folder_dest", help="folder to copy not-yet-played songs into")
    p.add_argument("file_already_played", help="text file listing played songs")
    args = p.parse_args()

    src = os.path.expanduser(args.folder_source)
    dst = os.path.expanduser(args.folder_dest)
    played_file = os.path.expanduser(args.file_already_played)
    if not os.path.isdir(src):
        sys.exit(f"source folder not found: {src}")
    if not os.path.isfile(played_file):
        sys.exit(f"already-played file not found: {played_file}")
    os.makedirs(dst, exist_ok=True)

    played = load_played(played_file)
    copied = already_there = 0
    skipped, fuzzy, matched = [], [], set()

    for fn in sorted(os.listdir(src)):
        if not fn.lower().endswith(".mp3"):
            continue
        stem = re.sub(r"\s+-\s+(\d{4}|NA)\.mp3$", "", fn, flags=re.I)
        entry = match_played(stem, played)
        if entry:
            skipped.append(fn)
            matched.add(entry)
            if norm(stem) != entry:
                fuzzy.append((entry, fn))
        elif os.path.exists(os.path.join(dst, fn)):
            already_there += 1
        else:
            shutil.copy2(os.path.join(src, fn), os.path.join(dst, fn))
            copied += 1

    print(f"copied {copied} new, {already_there} were already in destination, "
          f"skipped {len(skipped)} already-played")
    if fuzzy:
        print("\nfuzzy matches (check these look right):")
        for entry, fn in fuzzy:
            print(f"  '{entry}'  ->  {fn}")
    missing = sorted(set(e for e in played if e not in matched))
    if missing:
        print(f"\n{len(missing)} played entries matched no file in the source folder:")
        for e in missing:
            print("  -", e)


if __name__ == "__main__":
    main()
