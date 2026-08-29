#!/usr/bin/env python3
"""Add a "P" after the number of every previously-played track: "010 - X.mp3" -> "010P - X.mp3".
Source of truth = the "source" column of <Genre>/tracklist.txt (_played-before). Idempotent; rewrites tracklist + m3u."""
import re
import sys
from pathlib import Path

for g in sys.argv[1:]:
    root = Path(g)
    tl = root / "tracklist.txt"
    out, n = [], 0
    for line in tl.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(\d{3})(P?) \| (.*?) \| (.*?) \| (.*)$", line)
        if not m:
            out.append(line); continue
        num, _, bpm, src, name = m.groups()
        played = src.strip() == "_played-before"
        tag = "P" if played else ""
        for cand in (root / f"{num} - {name}", root / f"{num}P - {name}"):
            if cand.exists():
                dst = root / f"{num}{tag} - {name}"
                if cand != dst:
                    cand.rename(dst); n += 1
                break
        else:
            print(f"!! file not found for {num} {name}")
        out.append(f"{num}{tag} | {bpm} | {src} | {name}")
    tl.write_text("\n".join(out) + "\n", encoding="utf-8")
    (root / f"{root.name}.m3u").write_text("\n".join(str(p) for p in sorted(root.glob("*.mp3"))) + "\n", encoding="utf-8")
    total = sum(1 for l in out if re.match(r"^\d{3}P ", l))
    print(f"{root.name}: {n} files renamed, {total} played-before total")
