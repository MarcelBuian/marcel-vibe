#!/usr/bin/env python3
"""
Prefix the mp3 files of a folder with "NN - " in the order of a tracklist file.

    python3 number_files.py <folder> <order.txt>

The order file is a suggestions-round1.txt / played-before.txt ("Artist - Title - Year - link"
lines, one per track, comments with #). Each mp3 is matched to the best line by artist+title
words; matched files get that line's position, unmatched files are appended at the end.
Idempotent: an existing "NN - " prefix is stripped before re-numbering, so it is safe to run
again after new downloads land. The folder's .m3u is rebuilt afterwards.
"""
import re
import sys
import unicodedata
from pathlib import Path

PREFIX = re.compile(r"^\d{2,3} - ")


def norm(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[\(\)\[\]\-_–—|:,.'\"!?&+/]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


STOP = {"the", "a", "of", "feat", "ft", "and", "x", "mix", "original", "extended", "remix", "edit"}


def toks(s):
    return {t for t in norm(s).split() if t not in STOP and not t.isdigit()}


def read_order(path):
    out = []
    for l in Path(path).read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        l = re.sub(r"^\+\s*", "", l)                 # "+ " like-marker
        head = l.split(" - https")[0]
        parts = head.split(" - ")
        artist, title = parts[0], " - ".join(parts[1:-1]) if len(parts) > 2 else (parts[1] if len(parts) > 1 else "")
        out.append((artist, title))
    return out


def main():
    folder, order = Path(sys.argv[1]), sys.argv[2]
    lines = read_order(order)
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".mp3", ".m4a"))
    bare = {p: PREFIX.sub("", p.name) for p in files}
    ftoks = {p: toks(bare[p].rsplit(".", 1)[0]) for p in files}

    # greedy best-match assignment: line -> file
    scored = []
    for i, (artist, title) in enumerate(lines):
        tt, at = toks(title), toks(artist)
        if not tt:
            continue
        for p in files:
            ft = ftoks[p]
            th = len(tt & ft) / len(tt)
            ah = len(at & ft) / len(at) if at else 0
            if th >= 0.6:
                scored.append((th * 10 + ah * 4, i, p))
    scored.sort(reverse=True)
    line_of, used = {}, set()
    for sc, i, p in scored:
        if i in line_of or p in used:
            continue
        line_of[i], used = p, used | {p}

    ordered = [line_of[i] for i in range(len(lines)) if i in line_of]
    leftovers = [p for p in files if p not in used]
    n = 0
    for p in ordered + leftovers:
        n += 1
        new = p.with_name(f"{n:02d} - {bare[p]}")
        if new != p:
            p.rename(new)
    m3u = folder / f"{folder.name}.m3u"
    m3u.write_text("\n".join(str(p) for p in sorted(folder.iterdir()) if p.suffix.lower() in (".mp3", ".m4a")) + "\n")
    print(f"{folder}: {len(ordered)} matched to tracklist, {len(leftovers)} unmatched appended at the end ({n} files)")
    for p in leftovers:
        print(f"   unmatched -> {bare[p]}")


if __name__ == "__main__":
    main()
