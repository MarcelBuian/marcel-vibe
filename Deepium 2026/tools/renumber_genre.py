#!/usr/bin/env python3
"""
One continuous 3-digit numbering per genre folder, across the root and its subfolders.

    python3 renumber_genre.py <GenreFolder> [<GenreFolder> ...]

Order: root mp3s (suggested mix order) -> _played-before -> other subfolders (alphabetical).
Inside each group the existing numeric prefix order is kept. Existing "NN - " / "NNN - "
prefixes are stripped first, so re-running is safe. Rebuilds <Genre>/<Genre>.m3u over everything.
"""
import re
import sys
from pathlib import Path

PREFIX = re.compile(r"^\d{2,3} - ")
AUDIO = (".mp3", ".m4a")


def group_files(d: Path):
    files = [p for p in d.iterdir() if p.suffix.lower() in AUDIO]
    def key(p):
        m = re.match(r"^(\d+) - ", p.name)
        return (0, int(m.group(1)), p.name) if m else (1, 0, p.name.lower())
    return sorted(files, key=key)


def main():
    for g in sys.argv[1:]:
        root = Path(g)
        subs = sorted(p for p in root.iterdir() if p.is_dir())
        subs.sort(key=lambda p: (p.name != "_played-before", p.name))
        groups = [root] + subs
        n = 0
        all_files = []
        for d in groups:
            for p in group_files(d):
                n += 1
                new = p.with_name(f"{n:03d} - {PREFIX.sub('', p.name)}")
                if new != p:
                    p.rename(new)
                all_files.append(new)
        (root / f"{root.name}.m3u").write_text("\n".join(str(p) for p in all_files) + "\n")
        for d in groups:   # drop per-subfolder m3u leftovers from the earlier numbering step
            for old in d.glob("*.m3u"):
                if old != root / f"{root.name}.m3u":
                    old.unlink()
        ranges = []
        i = 0
        for d in groups:
            k = len(group_files(d))
            if k:
                ranges.append(f"{d.relative_to(root.parent)}: {i+1:03d}-{i+k:03d}")
                i += k
        print(f"{root.name}: {n} files -> " + " | ".join(ranges))


if __name__ == "__main__":
    main()
