#!/usr/bin/env python3
"""
Order a genre's tracks light -> aggressive from analysis.csv and (optionally) apply it.

    .venv/bin/python order_genre.py <GenreFolder>            # print proposed order
    .venv/bin/python order_genre.py <GenreFolder> --apply    # move all mp3s into the genre root as
                                                             # "010 - ", "020 - ", ... (step 10) + tracklist.txt + .m3u

Energy score = weighted z-scores inside the genre:
  0.35 loudness (rms_db) + 0.20 punch (rms_p90_db) + 0.20 percussive density (onset)
  + 0.15 brightness (centroid) + 0.10 BPM.
Manual overrides: <GenreFolder>/order-overrides.txt with lines "<substring of filename> = <score>"
(e.g. "Sangiuliano = 99" to force it last, "Cassian = -5" to push it early).
"""
import csv
import re
import shutil
import sys
from pathlib import Path

import numpy as np

STEP = 10
PREFIX = re.compile(r"^\d{2,3} - ")
W = dict(rms_db=0.35, rms_p90_db=0.20, onset=0.20, centroid_hz=0.15, bpm=0.10)


def z(v):
    v = np.asarray(v, dtype=float)
    return (v - v.mean()) / (v.std() + 1e-9)


def load(root):
    rows = list(csv.DictReader((root / "analysis.csv").open(encoding="utf-8")))
    rows = [r for r in rows if not r.get("error")]
    for k in W:
        col = z([float(r[k]) for r in rows])
        for r, val in zip(rows, col):
            r["z_" + k] = float(val)
    for r in rows:
        r["score"] = sum(W[k] * r["z_" + k] for k in W)
        if float(r["bpm"]) and float(r["bpm"]) < 100:      # half-time detection slipped through the fold
            r["bpm"] = str(round(float(r["bpm"]) * 2, 1))
        m = re.match(r"^(\d{2,3}) - ", Path(r["path"]).name)
        r["cur"] = m.group(1) if m else "---"
    ov = root / "order-overrides.txt"
    if ov.exists():
        for l in ov.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.strip().startswith("#"):
                key, val = [x.strip() for x in l.split("=", 1)]
                for r in rows:
                    if key.lower() in Path(r["path"]).name.lower():
                        r["score"] = float(val)
    rows.sort(key=lambda r: r["score"])
    return rows


def main():
    root = Path(sys.argv[1])
    apply = "--apply" in sys.argv
    rows = load(root)
    print(f"{'cur':>4} {'score':>6} {'bpm':>5} {'rms':>6} {'group':<16} file")
    for r in rows:
        print(f"{r['cur']:>4} {r['score']:6.2f} {float(r['bpm']):5.1f} {float(r['rms_db']):6.1f} {r['group'][:16]:<16} {PREFIX.sub('', Path(r['path']).name)[:95]}")
    if not apply:
        return
    lines = ["# number | bpm | energy score | source | file"]
    m3u = []
    for i, r in enumerate(rows, 1):
        src = Path(r["path"])
        if not src.is_absolute():
            src = root.parent / src
        bare = PREFIX.sub("", src.name)
        dst = root / f"{i*STEP:03d} - {bare}"
        if src.resolve() != dst.resolve():
            if dst.exists():
                dst.unlink()
            shutil.move(str(src), str(dst))
        lines.append(f"{i*STEP:03d} | {float(r['bpm']):.0f} bpm | {r['score']:+.2f} | {r['group']} | {bare}")
        m3u.append(str(dst))
    (root / "tracklist.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for old in root.rglob("*.m3u"):
        old.unlink()
    (root / f"{root.name}.m3u").write_text("\n".join(m3u) + "\n", encoding="utf-8")
    # clean up now-empty audio subfolders (keep folders that still hold txt notes)
    for d in sorted(root.iterdir()):
        if d.is_dir() and not any(p.suffix.lower() in (".mp3", ".m4a") for p in d.iterdir()):
            for junk in d.glob("archive.txt"):
                junk.unlink()
            if not any(d.iterdir()):
                d.rmdir()
    print(f"\napplied: {len(rows)} files numbered {STEP:03d}..{len(rows)*STEP:03d} in {root}/ (tracklist.txt written)")


if __name__ == "__main__":
    main()
