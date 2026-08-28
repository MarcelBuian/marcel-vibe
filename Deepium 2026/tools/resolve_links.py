#!/usr/bin/env python3
"""
Resolve "Artist | Title | Year | note" lines to YouTube Music links.

    python3 resolve_links.py in.txt out.txt

Each input line:   Artist | Title | YYYY | vibe note
Each output line:  Artist - Title - YYYY - https://music.youtube.com/watch?v=ID   # note
If no confident match is found the link becomes a music.youtube.com SEARCH link
and the line is suffixed with  [SEARCH LINK - not verified].

Uses yt-dlp's "ytsearch" (flat, no downloads) and picks the best candidate:
prefers official "- Topic" auto-generated channels (that is what YouTube Music
serves), then the artist's own channel, sane track duration, and a title that
contains the requested track title. Skips DJ sets / podcasts / full albums.
"""
import html
import os
import re
import signal
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus
from pathlib import Path

HERE = Path(__file__).resolve().parent
YTDLP = HERE.parent.parent / "radio-tracklog" / "yt-dlp"
N_RESULTS = 8
WORKERS = int(os.environ.get("WORKERS", "2"))   # keep low: YouTube slows down hard above ~4 parallel searches

BAD_WORDS = ["dj set", "live set", "podcast", "radio show", "full album", "mixtape",
             "boiler room", "tracklist", "1 hour", "hour mix", "continuous mix",
             "essential mix", "live at", "live @", "b2b", "mix 20", "episode", "ep.",
             "house mix", "techno mix", "minimal mix", "chill mix", "chillout", "vibes mix",
             "summer mix", "sunset mix", "playlist", "best of", "top 10", "top 20"]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[\(\)\[\]\-_–—|:,.'\"!?&+/]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str):
    return [t for t in norm(s).split() if t not in {"the", "a", "of", "feat", "ft", "and", "x"}]


def run(cmd, timeout=90) -> str:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                            start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return out
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        return ""


def search(query: str):
    cmd = [str(YTDLP), f"ytsearch{N_RESULTS}:{query}", "--flat-playlist", "--no-download",
           "--no-warnings", "--print", "%(id)s\t%(title)s\t%(channel,uploader)s\t%(duration)s\t%(release_year,upload_date>%Y)s"]
    out = run(cmd)
    res = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        vid, title, channel, dur, yr = parts
        try:
            dur = int(float(dur))
        except ValueError:
            dur = 0
        res.append((vid, title, channel, dur, yr))
    return res


def fetch_year(vid: str) -> str:
    cmd = [str(YTDLP), f"https://www.youtube.com/watch?v={vid}", "--no-download", "--no-warnings",
           "--print", "%(release_year,upload_date>%Y)s"]
    out = run(cmd).strip()
    return out.splitlines()[-1] if out and out != "NA" else "?"


def score(cand, artist, title):
    vid, vtitle, channel, dur, _yr = cand
    nt, nc = norm(vtitle), norm(channel)
    s = 0.0
    ttoks = tokens(title)
    hit = sum(1 for t in ttoks if t in nt)
    if not ttoks or hit / len(ttoks) < 0.6:
        return -100
    s += 10 * hit / len(ttoks)
    atoks = tokens(artist)
    ahit = sum(1 for t in atoks if t in nt or t in nc)
    s += 6 * (ahit / len(atoks) if atoks else 0)
    if nc.endswith("topic"):
        s += 5           # official audio, what YouTube Music serves
    if any(w in nt for w in BAD_WORDS):
        s -= 20
    if dur and not (120 <= dur <= 780):
        s -= 15
    # requested a remix -> title must mention it; requested original -> avoid remixes
    want_remix = "remix" in norm(title) or "edit" in norm(title) or "rework" in norm(title)
    has_remix = "remix" in nt or "edit" in nt or "rework" in nt or "bootleg" in nt
    if has_remix and not want_remix:
        s -= 8
    if want_remix and not has_remix:
        s -= 8
    if "extended" in nt:
        s += 1
    return s


def resolve(line: str):
    raw = html.unescape(line).strip()
    if not raw or raw.startswith("#"):
        return None
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 3:
        return f"# could not parse: {raw}"
    artist, title, year = parts[0], parts[1], parts[2]
    note = parts[3] if len(parts) > 3 else ""
    query = f"{artist} {title}"
    cands = search(query)
    best, best_s = None, -1e9
    for c in cands:
        sc = score(c, artist, title)
        if sc > best_s:
            best, best_s = c, sc
    tail = f"   # {note}" if note else ""
    if best and best_s >= 12:
        if year in ("?", ""):          # unknown year -> ask YouTube (flat search has no dates)
            year = fetch_year(best[0])
        link = f"https://music.youtube.com/watch?v={best[0]}"
        return f"{artist} - {title} - {year} - {link}{tail}"
    link = f"https://music.youtube.com/search?q={quote_plus(query)}"
    return f"{artist} - {title} - {year} - {link}   [SEARCH LINK - not verified]{tail}"


def key_of(line: str) -> str:
    """'Artist | Title | ...' or 'Artist - Title - ...' -> 'artist title' for resume matching."""
    raw = html.unescape(line)
    parts = [p.strip() for p in (raw.split("|") if "|" in raw else raw.split(" - "))]
    return norm(" ".join(parts[:2])) if len(parts) >= 2 else norm(raw)


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    lines = [l for l in src.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    done = set()
    if dst.exists():   # resume: skip tracks already resolved to a real link (search links are retried)
        for l in dst.read_text(encoding="utf-8").splitlines():
            if l.strip() and "SEARCH LINK" not in l:
                done.add(key_of(l))
    todo = [l for l in lines if key_of(l) not in done]
    print(f"{src.name}: {len(lines)} tracks, {len(done)} already resolved, {len(todo)} to do", flush=True)
    kept = [l for l in dst.read_text(encoding="utf-8").splitlines() if l.strip() and "SEARCH LINK" not in l] if dst.exists() else []
    with dst.open("w", encoding="utf-8") as f:
        for l in kept:
            f.write(l + "\n")
        f.flush()
        with ThreadPoolExecutor(WORKERS) as ex:
            for r in ex.map(resolve, todo):
                if r:
                    f.write(r + "\n")
                    f.flush()
                    print(("  ok   " if "SEARCH LINK" not in r else "  MISS ") + r.split(" - https")[0], flush=True)
    out = [l for l in dst.read_text(encoding="utf-8").splitlines() if l.strip()]
    unresolved = sum(1 for r in out if "SEARCH LINK" in r)
    print(f"{len(out)} lines in {dst}  ({unresolved} unresolved -> search links)", flush=True)


if __name__ == "__main__":
    main()
