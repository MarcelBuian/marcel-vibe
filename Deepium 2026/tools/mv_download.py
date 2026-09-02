#!/usr/bin/env python3
"""
Incremental downloader for the Marcel Vibe archive.
Loops sessions 01..27: downloads every resolved-but-not-yet-downloaded track into MarcelVibe/NN/
(plain "Artist - Title - Year.mp3"), then repeats while the resolver is still adding links.
Writes MarcelVibe/NN/tracklist.txt (set order + status) and MarcelVibe/_work/unavailable.txt.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "MarcelVibe"
WORK = OUT / "_work"
YTDLP = ROOT.parent / "radio-tracklog" / "yt-dlp"
FFMPEG = ROOT.parent / "radio-tracklog"
sys.path.insert(0, str(ROOT / "tools"))
from build_marcelvibe import key  # noqa: E402


def resolved():
    res = {}
    for l in (WORK / "all_out.txt").read_text(encoding="utf-8").splitlines():
        if "watch?v=" in l and "SEARCH LINK" not in l:
            head = l.split(" - https")[0]
            parts = head.split(" - ")
            if len(parts) < 3:
                continue
            m = re.search(r"watch\?v=([A-Za-z0-9_-]{11})", l)
            res[key(parts[0], " - ".join(parts[1:-1]))] = (m.group(1), parts[-1].strip())
    return res


def resolver_running():
    log = (WORK / "resolve.log")
    return not (log.exists() and "MV_RESOLVE_DONE" in log.read_text(encoding="utf-8", errors="ignore")) \
        and subprocess.run(["pgrep", "-f", "resolve_links.py"], capture_output=True).returncode == 0


def archived(folder):
    a = folder / "archive.txt"
    return {l.split()[-1] for l in a.read_text().splitlines() if l.strip()} if a.exists() else set()


def unavailable_ids():
    f = WORK / "unavailable.txt"
    return {l.split()[0] for l in f.read_text().splitlines() if l.strip()} if f.exists() else set()


def download(folder, ids, sess):
    folder.mkdir(parents=True, exist_ok=True)
    cmd = [str(YTDLP), "--js-runtimes", "node", "--ffmpeg-location", str(FFMPEG), "--ignore-errors",
           "--sleep-requests", "1", "--sleep-interval", "1", "--max-sleep-interval", "3",
           "--retry-sleep", "http:exp=2:60", "--extractor-retries", "2",
           "-f", "bestaudio/best", "-x", "--audio-format", "mp3", "--audio-quality", "0",
           "--embed-thumbnail", "--convert-thumbnails", "jpg", "--embed-metadata",
           "--output", f"{folder}/%(artist&{{}} - |)s%(title)s - %(release_year,upload_date>%Y)s.%(ext)s",
           "--download-archive", str(folder / "archive.txt"), "--no-overwrites", "--no-mtime",
           "--batch-file", "-"]
    p = subprocess.run(cmd, input="\n".join(f"https://www.youtube.com/watch?v={i}" for i in ids) + "\n",
                       capture_output=True, text=True)
    log = p.stdout + p.stderr
    with (WORK / "download.log").open("a", encoding="utf-8") as f:
        f.write(f"\n===== {folder.name} ({sess['name']}) {time.strftime('%H:%M:%S')}\n{log}")
    bad = re.findall(r"ERROR: \[youtube\] ([A-Za-z0-9_-]{11}): (.*)", log)
    if bad:
        with (WORK / "unavailable.txt").open("a", encoding="utf-8") as f:
            for vid, why in bad:
                f.write(f"{vid} {folder.name} {why.strip()}\n")
    return len(bad)


def write_tracklist(folder, sess, res, arch):
    lines = [f"# {sess['name']} - tracks in set order"]
    for t in sess["tracks"]:
        r = res.get(t["key"])
        if not r:
            st = "not found on YouTube (yet)"
        elif r[0] in arch:
            st = "downloaded"
        else:
            st = "unavailable from this IP (geo-block?) - retry with VPN" if r[0] in unavailable_ids() else "pending"
        lines.append(f"{t['artist']} - {t['title']}{' - ' + r[1] if r else ''} | {st}")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "tracklist.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    sessions = json.loads((WORK / "sessions.json").read_text(encoding="utf-8"))
    skip = {int(x) for x in os.environ.get("SKIP", "21,22").split(",") if x.strip()}   # #21/#22 = Melodic sets, already in MelodicHouse/
    sessions = [s for s in sessions if s["num"] not in skip]
    prio = [int(x) for x in os.environ.get("PRIORITY", "").split(",") if x.strip()]
    sessions.sort(key=lambda s: (prio.index(s["num"]) if s["num"] in prio else len(prio), s["num"]))
    rounds = 0
    while True:
        rounds += 1
        res = resolved()
        did = 0
        for s in sessions:
            folder = OUT / f"{s['num']:02d}"
            arch = archived(folder)
            skip = unavailable_ids()
            todo = [res[t["key"]][0] for t in s["tracks"] if t["key"] in res and res[t["key"]][0] not in arch and res[t["key"]][0] not in skip]
            todo = list(dict.fromkeys(todo))
            if todo:
                print(f"[round {rounds}] {folder.name}: downloading {len(todo)}", flush=True)
                download(folder, todo, s)
                did += len(todo)
            write_tracklist(folder, s, res, archived(folder))
        total = sum(len(list((OUT / f"{s['num']:02d}").glob("*.mp3"))) for s in sessions)
        print(f"[round {rounds}] done, {did} attempted this round, {total} mp3 on disk, resolver running: {resolver_running()}", flush=True)
        if not resolver_running() and did == 0:
            break
        if did == 0:
            time.sleep(120)
    print("MV_DOWNLOAD_DONE", flush=True)


if __name__ == "__main__":
    main()
