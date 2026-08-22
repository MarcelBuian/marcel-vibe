#!/usr/bin/env python3
"""Log the tracks played on a YouTube 24/7 radio stream via its chat bot.

The Monstercat Silk stream (and similar 24/7 radios) run a chat bot that
names the currently playing track whenever a viewer types !track / !love,
e.g.:  @someone loves 'Toast' by Flexible Fire feat. Fractures!

This script uses yt-dlp to capture the live chat, extracts those bot
messages, and maintains tracklog/songs.csv next to this script — one row
per song (never duplicated) with a first-added date, a play counter, and
a last-played date that update whenever the song repeats.

Usage:
  python3 radio_tracklog.py log      # run the logger (Ctrl+C to stop)
  python3 radio_tracklog.py list     # songs by first-added date
  python3 radio_tracklog.py stats    # songs by play count
  python3 radio_tracklog.py enrich   # look up YouTube link + year per song

See README.md for setup. Chat only reveals a track when someone interacts
with the bot, so the log is a sampled history — counts are a lower bound,
but over hours/days the repeats become obvious.
"""

import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_URL = "https://www.youtube.com/watch?v=WsDyRAPFBC8"  # Monstercat Silk 24/7
DATA_DIR = os.path.join(SCRIPT_DIR, "tracklog")
SONGS_CSV = os.path.join(DATA_DIR, "songs.csv")
FIELDS = ["first_added", "plays", "last_played", "artist", "title", "youtube", "year"]

BOT_AUTHORS = {"@monstercatbot", "monstercatbot"}
# "@user loves 'Title' by Artist!"  /  "Now Playing: 'Title' by Artist"
TRACK_RE = re.compile(r"'(?P<title>[^']+)' by (?P<artist>.+?)[!.]?\s*$")
# Same track re-announced within this window counts as the same spin.
SAME_SPIN_SECONDS = 12 * 60


def find_ytdlp(override=None):
    """Locate yt-dlp: --ytdlp flag, .venv next to this script, or PATH."""
    candidates = [override] if override else []
    candidates += [
        os.path.join(SCRIPT_DIR, ".venv", "bin", "yt-dlp"),
        os.path.join(SCRIPT_DIR, ".venv", "Scripts", "yt-dlp.exe"),  # Windows
        shutil.which("yt-dlp"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    sys.exit(
        "yt-dlp not found. Set it up next to this script:\n"
        "  python3 -m venv .venv && .venv/bin/pip install yt-dlp\n"
        "(see README.md), or pass --ytdlp /path/to/yt-dlp"
    )


def lookup_song(ytdlp, artist, title):
    """Search YouTube for the song; returns (url, year) — either may be None."""
    try:
        out = subprocess.run(
            [
                ytdlp,
                "--skip-download",
                "--print",
                "%(webpage_url)s\t%(release_year,upload_date>%Y)s",
                f"ytsearch1:{artist} {title}",
            ],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return None, None
    parts = out.split("\t")
    if len(parts) == 2 and parts[0].startswith("http"):
        return parts[0], (parts[1] if parts[1].isdigit() else None)
    return None, None


class SongBook:
    """songs.csv: one row per song; counter and last_played update on repeat."""

    def __init__(self, path):
        self.path = path
        self.songs = {}  # (artist, title) -> row dict
        self.max_last = None  # newest last_played; guards against chat backlog
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    row = {k: row.get(k, "") for k in FIELDS}
                    row["plays"] = int(row["plays"] or 1)
                    self.songs[(row["artist"], row["title"])] = row
                    last = dt.datetime.fromisoformat(row["last_played"])
                    if self.max_last is None or last > self.max_last:
                        self.max_last = last

    def add_spin(self, ts, title, artist):
        """Count one spin; returns 'new', 'repeat', or None (backlog / same spin)."""
        # chat backlog is re-sent on every (re)start — never re-count the past
        if self.max_last is not None and ts <= self.max_last:
            return None
        self.max_last = ts
        iso = ts.isoformat(timespec="seconds")
        song = self.songs.get((artist, title))
        if song is None:
            self.songs[(artist, title)] = {
                "first_added": iso, "plays": 1, "last_played": iso,
                "artist": artist, "title": title, "youtube": "", "year": "",
            }
            return "new"
        last = dt.datetime.fromisoformat(song["last_played"])
        same_spin = (ts - last).total_seconds() < SAME_SPIN_SECONDS
        song["last_played"] = iso
        if same_spin:
            return None
        song["plays"] += 1
        return "repeat"

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for row in sorted(self.songs.values(), key=lambda r: r["first_added"]):
                w.writerow(row)
        os.replace(tmp, self.path)


def iter_chat_messages(raw_line):
    """Yield (timestamp, author, text) from one line of a yt-dlp live_chat file."""
    try:
        d = json.loads(raw_line)
    except (ValueError, TypeError):
        return
    if not isinstance(d, dict):
        return
    actions = d.get("replayChatItemAction", {}).get("actions") or [d]
    for a in actions:
        if not isinstance(a, dict):
            continue
        r = a.get("addChatItemAction", {}).get("item", {}).get("liveChatTextMessageRenderer")
        if not r:
            continue
        author = r.get("authorName", {}).get("simpleText", "")
        runs = r.get("message", {}).get("runs", [])
        text = "".join(x.get("text", "") for x in runs if isinstance(x, dict))
        usec = r.get("timestampUsec")
        ts = dt.datetime.fromtimestamp(int(usec) / 1e6) if usec else dt.datetime.now()
        yield ts, author, text


def parse_track(author, text):
    if author.lower() not in BOT_AUTHORS:
        return None
    m = TRACK_RE.search(text)
    if not m:
        return None
    return m.group("title").strip(), m.group("artist").strip()


def tail_session(base, offsets, seen):
    """Read new complete lines from the session's live_chat files; yield messages."""
    for fn in sorted(glob.glob(base + ".live_chat.json*")):
        try:
            size = os.path.getsize(fn)
        except OSError:
            continue
        pos = offsets.get(fn, 0)
        if size <= pos:
            continue
        with open(fn, "rb") as f:
            f.seek(pos)
            chunk = f.read(size - pos)
        # only consume up to the last complete line
        nl = chunk.rfind(b"\n")
        if nl == -1:
            continue
        offsets[fn] = pos + nl + 1
        for raw in chunk[: nl + 1].splitlines():
            for ts, author, text in iter_chat_messages(raw.decode("utf-8", "replace")):
                key = (ts.isoformat(), author, text)
                if key in seen:
                    continue
                seen.add(key)
                yield ts, author, text


def remove_chat_dumps(base=None):
    """Chat dumps are only a transport; delete them once a session is over."""
    pattern = (base + ".live_chat.json*") if base else os.path.join(DATA_DIR, "chat-*.live_chat.json*")
    for fn in glob.glob(pattern):
        try:
            os.remove(fn)
        except OSError:
            pass


def _sigterm(*_):
    raise KeyboardInterrupt


def cmd_log(args):
    os.makedirs(DATA_DIR, exist_ok=True)
    signal.signal(signal.SIGTERM, _sigterm)  # clean up on `kill` too, not just Ctrl+C
    remove_chat_dumps()  # leftovers from previous runs
    ytdlp = find_ytdlp(args.ytdlp)
    book = SongBook(SONGS_CSV)
    print(f"Logging tracks from {args.url}", flush=True)
    print(f"Songs file: {SONGS_CSV}  (Ctrl+C to stop)", flush=True)

    proc = None
    try:
        while True:
            session = os.path.join(
                DATA_DIR, "chat-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            )
            proc = subprocess.Popen(
                [
                    ytdlp,
                    "--skip-download",
                    "--write-subs",
                    "--sub-langs",
                    "live_chat",
                    "-o",
                    session,
                    args.url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            offsets, seen = {}, set()
            while proc.poll() is None:
                time.sleep(5)
                for ts, author, text in tail_session(session, offsets, seen):
                    track = parse_track(author, text)
                    if not track:
                        continue
                    result = book.add_spin(ts, *track)
                    if result:
                        title, artist = track
                        song = book.songs[(artist, title)]
                        if result == "new":
                            song["youtube"], song["year"] = (
                                v or "" for v in lookup_song(ytdlp, artist, title)
                            )
                        book.save()
                        if result == "new":
                            extra = f"  ({song['year'] or 'year?'})  {song['youtube'] or 'no link found'}"
                            label = "NEW song added"
                        else:
                            extra = ""
                            label = f"play #{song['plays']}"
                        print(f"[{ts:%Y-%m-%d %H:%M}] {label}: {artist} — {title}{extra}", flush=True)
            remove_chat_dumps(session)
            print("yt-dlp exited (stream hiccup?), restarting in 30s...", flush=True)
            time.sleep(30)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        if proc and proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
        remove_chat_dumps()
        book.save()
    cmd_stats(args)


def load_book():
    if not os.path.exists(SONGS_CSV):
        sys.exit(f"No songs logged yet ({SONGS_CSV} missing). Run: radio_tracklog.py log")
    return SongBook(SONGS_CSV)


def print_songs(rows):
    print(f"{'first added':<12} {'plays':>5}  {'last played':<12} {'year':<5} song")
    for r in rows:
        print(
            f"{r['first_added'][:10]:<12} {r['plays']:>5}  {r['last_played'][:10]:<12} "
            f"{(r['year'] or '?'):<5} {r['artist']} — {r['title']}"
        )


def cmd_list(args):
    book = load_book()
    print(f"\n{len(book.songs)} songs (no duplicates), oldest first — file: {SONGS_CSV}\n")
    print_songs(sorted(book.songs.values(), key=lambda r: r["first_added"]))


def cmd_stats(args):
    book = load_book()
    total = sum(r["plays"] for r in book.songs.values())
    print(f"\n{total} spins counted, {len(book.songs)} distinct songs — most played first\n")
    print_songs(sorted(book.songs.values(), key=lambda r: -r["plays"]))


def cmd_enrich(args):
    """Fill in the youtube + year columns via a YouTube search per song."""
    ytdlp = find_ytdlp(args.ytdlp)
    book = load_book()
    todo = [r for r in book.songs.values() if not r["youtube"] or not r["year"]]
    if not todo:
        print("All songs already have a YouTube link and year.")
        return
    print(f"Looking up {len(todo)} songs on YouTube (a few seconds each)...", flush=True)
    for r in todo:
        query = f"{r['artist']} {r['title']}"
        url, year = lookup_song(ytdlp, r["artist"], r["title"])
        if url:
            r["youtube"] = r["youtube"] or url
            if year:
                r["year"] = r["year"] or year
            book.save()
            print(f"  {query}  ->  {r['year'] or '?'}  {r['youtube']}", flush=True)
        else:
            print(f"  {query}  ->  not found", flush=True)
    print(f"\nDone. Updated {SONGS_CSV}")


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("command", nargs="?", default="log", choices=["log", "list", "stats", "enrich"])
    p.add_argument("--url", default=DEFAULT_URL, help="YouTube live stream URL")
    p.add_argument("--ytdlp", default=None, help="path to yt-dlp (default: auto-detect)")
    args = p.parse_args()
    {"log": cmd_log, "list": cmd_list, "stats": cmd_stats, "enrich": cmd_enrich}[args.command](args)


if __name__ == "__main__":
    main()
