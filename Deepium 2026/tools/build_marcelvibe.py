#!/usr/bin/env python3
"""
Step 1 of the MarcelVibe archive: parse MarcelVibe/Playlists.txt into sessions, reuse every link already
verified in this project, and write the resolver input/output seed.

    python3 build_marcelvibe.py prepare   -> MarcelVibe/_work/all_in.txt (+ seeded all_out.txt), sessions.json
    python3 build_marcelvibe.py folders   -> per-session folder + tracklist.txt + batch file (after resolving)
"""
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # Deepium 2026
PLAYLISTS = ROOT.parent / "MarcelVibe" / "Playlists.txt"
OUT = ROOT / "MarcelVibe"
WORK = OUT / "_work"
SCRATCH = Path("/private/tmp/claude-501/-Users-marcelbuian-projects-mb-personal/a186669b-c80b-4262-ad33-6bc96072e12b/scratchpad")


def norm(s):
    s = unicodedata.normalize("NFKD", html.unescape(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[\(\)\[\]\-_–—|:,.'\"!?&+/]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def key(artist, title):
    return norm(artist + " " + title)


def parse_sessions():
    sessions, cur = [], None
    for raw in PLAYLISTS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^#(\d+)\s*-\s*(.*)$", line)
        if m:
            head = m.group(2).split("->")[0].strip().rstrip(",")
            head = re.sub(r"\s+", " ", head).replace("/", "-")
            cur = {"num": int(m.group(1)), "name": f"#{m.group(1)} - {head}", "tracks": []}
            sessions.append(cur)
            continue
        m = re.match(r"^(?:\[R\]\s*)?[\d:]+\s*-?\s*(.+)$", line)
        if not m or cur is None:
            continue
        body = m.group(1).strip()
        if " - " not in body:
            continue
        artist, title = body.split(" - ", 1)
        artist, title = artist.strip(), title.strip()
        if not artist or not title:
            continue
        k = key(artist, title)
        if any(t["key"] == k for t in cur["tracks"]):
            continue                       # same track played twice in one set
        cur["tracks"].append({"artist": artist, "title": title, "key": k})
    return sessions


def cache_lines():
    """All 'Artist - Title - Year - https://music.youtube.com/watch?v=..' lines we already verified."""
    files = list(SCRATCH.glob("*_out.txt")) + list(ROOT.glob("*/suggestions*.txt")) + list(ROOT.glob("*/_played-before/*.txt")) \
        + list(ROOT.glob("*/_played-before/replacements.txt"))
    seen = {}
    for f in files:
        for l in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            l = re.sub(r"^\+\s*", "", l.strip())
            if "watch?v=" not in l or "SEARCH LINK" in l or l.startswith("#"):
                continue
            head = l.split(" - https")[0]
            parts = head.split(" - ")
            if len(parts) < 3:
                continue
            artist, title = parts[0], " - ".join(parts[1:-1])
            seen.setdefault(key(artist, title), l.split("   #")[0].strip())
    return seen


def prepare():
    WORK.mkdir(parents=True, exist_ok=True)
    sessions = parse_sessions()
    (WORK / "sessions.json").write_text(json.dumps(sessions, ensure_ascii=False, indent=1), encoding="utf-8")
    cache = cache_lines()
    uniq, seeded = {}, []
    for s in sessions:
        for t in s["tracks"]:
            if t["key"] not in uniq:
                uniq[t["key"]] = t
                if t["key"] in cache:
                    seeded.append(cache[t["key"]])
    (WORK / "all_in.txt").write_text("\n".join(f"{t['artist']} | {t['title']} | ? | archive" for t in uniq.values()) + "\n", encoding="utf-8")
    (WORK / "all_out.txt").write_text("\n".join(seeded) + "\n", encoding="utf-8")
    print(f"{len(sessions)} sessions, {sum(len(s['tracks']) for s in sessions)} track slots, {len(uniq)} unique tracks, "
          f"{len(seeded)} already have verified links, {len(uniq) - len(seeded)} to resolve")


def folders():
    sessions = json.loads((WORK / "sessions.json").read_text(encoding="utf-8"))
    resolved = {}
    for l in (WORK / "all_out.txt").read_text(encoding="utf-8").splitlines():
        if "watch?v=" in l and "SEARCH LINK" not in l:
            head = l.split(" - https")[0]
            parts = head.split(" - ")
            artist, title = parts[0], " - ".join(parts[1:-1])
            m = re.search(r"watch\?v=([A-Za-z0-9_-]{11})", l)
            resolved[key(artist, title)] = (m.group(1), parts[-1].strip())
    total_ok = total = 0
    for s in sessions:
        d = OUT / s["name"]
        d.mkdir(parents=True, exist_ok=True)
        lines, batch = [f"# {s['name']} - tracks in set order. Missing = not found on YouTube."], []
        n = 0
        for t in s["tracks"]:
            total += 1
            r = resolved.get(t["key"])
            if r:
                n += 1; total_ok += 1
                lines.append(f"{n:02d} | {t['artist']} - {t['title']} - {r[1]} | https://music.youtube.com/watch?v={r[0]}")
                batch.append(f"https://www.youtube.com/watch?v={r[0]}")
            else:
                lines.append(f"-- | {t['artist']} - {t['title']} | MISSING on YouTube")
        (d / "tracklist.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (WORK / f"batch_{s['num']:02d}.txt").write_text("\n".join(batch) + "\n", encoding="utf-8")
        print(f"{s['name']}: {n}/{len(s['tracks'])} resolved")
    print(f"TOTAL {total_ok}/{total} track slots resolved")


if __name__ == "__main__":
    {"prepare": prepare, "folders": folders}[sys.argv[1]]()
