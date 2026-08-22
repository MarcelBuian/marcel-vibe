#!/usr/bin/env python3
"""Log the tracks played on YouTube 24/7 radio streams.

Two independent ways of hearing what's playing:

  watch  — grab one video frame every N seconds and read the stream's
           on-screen "now playing" overlay with macOS's built-in OCR
           (Vision framework — offline, free, no AI service involved).
           Catches every song. macOS only.
  log    — capture the stream's live chat with yt-dlp and parse the chat
           bot's track announcements ("@user loves 'Title' by Artist!").
           Works on any OS, but sampled: only songs someone asked about.

Each radio lives in its own folder under radios/<name>/ holding
config.json (YouTube URL, capture interval, OCR region) and songs.csv —
one row per song (never duplicated) with a first-added date, a play
counter, and a last-played date that update whenever the song repeats.

Usage:
  python3 radio_tracklog.py watch [radio]   # OCR the overlay (macOS)
  python3 radio_tracklog.py log [radio]     # chat-bot logger
  python3 radio_tracklog.py list [radio]    # songs by first-added date
  python3 radio_tracklog.py stats [radio]   # songs by play count
  python3 radio_tracklog.py enrich [radio]  # look up YouTube link + year

[radio] defaults to the only folder in radios/ (created on first run).
yt-dlp and ffmpeg download themselves on first use — see README.md.
"""

import argparse
import csv
import datetime as dt
import glob
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RADIOS_DIR = os.path.join(SCRIPT_DIR, "radios")
OCR_SWIFT = os.path.join(SCRIPT_DIR, "ocr.swift")
OCR_BIN = os.path.join(SCRIPT_DIR, ".ocr")
FIELDS = ["first_added", "plays", "last_played", "artist", "title", "youtube", "year"]

DEFAULT_RADIO = "monstercat-silk"
DEFAULT_URL = "https://www.youtube.com/watch?v=WsDyRAPFBC8"  # Monstercat Silk 24/7
DEFAULT_CONFIG = {
    # the YouTube live stream to follow
    "url": DEFAULT_URL,
    # watch mode: how often to grab a frame and read the overlay
    "capture_interval_seconds": 60,
    # watch mode: where the now-playing overlay sits in the frame, as
    # fractions of width/height measured from the BOTTOM-LEFT corner
    "ocr_region": {"x": [0.12, 0.75], "y": [0.02, 0.40]},
}

BOT_AUTHORS = {"@monstercatbot", "monstercatbot"}
# "@user loves 'Title' by Artist!"  /  "Now Playing: 'Title' by Artist"
TRACK_RE = re.compile(r"'(?P<title>[^']+)' by (?P<artist>.+?)[!.]?\s*$")
# Same track re-announced within this window counts as the same spin.
SAME_SPIN_SECONDS = 12 * 60

# yt-dlp dying this fast means it's broken (stale version), not a stream hiccup.
QUICK_FAIL_SECONDS = 60
# After this many quick failures in a row, download a fresh standalone yt-dlp.
UPDATE_AFTER_FAILURES = 3

YTDLP_ASSET = {"darwin": "yt-dlp_macos", "win32": "yt-dlp.exe"}.get(sys.platform, "yt-dlp")
YTDLP_LOCAL = os.path.join(SCRIPT_DIR, "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")
FFMPEG_LOCAL = os.path.join(SCRIPT_DIR, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")

# 720p is plenty for reading the overlay; prefer HLS video-only live formats.
STREAM_FORMAT = "bv*[height<=720]/b[height<=720]/bv*/b"


# ---------------------------------------------------------------- tools

def find_ytdlp(override=None):
    """Locate yt-dlp: --ytdlp flag, downloaded binary, .venv, or PATH."""
    candidates = [override] if override else []
    candidates += [
        YTDLP_LOCAL,  # standalone binary fetched by download_ytdlp()
        os.path.join(SCRIPT_DIR, ".venv", "bin", "yt-dlp"),
        os.path.join(SCRIPT_DIR, ".venv", "Scripts", "yt-dlp.exe"),  # Windows
        shutil.which("yt-dlp"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    got = download_ytdlp(YTDLP_LOCAL)  # fresh machine: fetch it and carry on
    if got:
        return got
    sys.exit(
        "yt-dlp not found and the download failed — retry with internet, "
        "or pass --ytdlp /path/to/yt-dlp (see README.md)."
    )


def download_ytdlp(current):
    """Fetch the latest standalone yt-dlp; returns the path to use, or None.

    YouTube regularly breaks old yt-dlp versions, and pip installs can be
    pinned to an old release by the Python version (e.g. macOS system 3.9).
    The standalone release binary bundles its own Python, so it always works.
    Overwrites `current` when it's ours (under this script's directory),
    otherwise leaves system/pip installs alone and saves next to the script.
    """
    dest = current if os.path.abspath(current).startswith(SCRIPT_DIR + os.sep) else YTDLP_LOCAL
    url = f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{YTDLP_ASSET}"
    print(f"Downloading latest yt-dlp to {dest} ...", flush=True)
    import urllib.request

    tmp = dest + ".new"
    try:
        with urllib.request.urlopen(url, timeout=300) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.chmod(tmp, 0o755)
        os.replace(tmp, dest)
    except OSError as e:
        print(f"Download failed ({e}); keeping current yt-dlp.", flush=True)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None
    return dest


def find_ffmpeg():
    """Locate ffmpeg (project folder or PATH); auto-download it on macOS."""
    for c in (FFMPEG_LOCAL, shutil.which("ffmpeg")):
        if c and os.path.exists(c):
            return c
    if sys.platform != "darwin":
        sys.exit("ffmpeg not found — install it and re-run (see README.md).")
    arch = {"arm64": "arm64", "x86_64": "amd64"}.get(platform.machine())
    if not arch:
        sys.exit(f"No static ffmpeg build known for {platform.machine()} — install ffmpeg manually.")
    url = f"https://ffmpeg.martin-riedl.de/redirect/latest/macos/{arch}/release/ffmpeg.zip"
    print(f"Downloading ffmpeg (one-time, ~30 MB) to {FFMPEG_LOCAL} ...", flush=True)
    import io
    import urllib.request
    import zipfile

    tmp = FFMPEG_LOCAL + ".new"
    try:
        with urllib.request.urlopen(url, timeout=600) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z, z.open("ffmpeg") as src, open(tmp, "wb") as f:
            shutil.copyfileobj(src, f)
        os.chmod(tmp, 0o755)
        os.replace(tmp, FFMPEG_LOCAL)
    except (OSError, zipfile.BadZipFile, KeyError) as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        sys.exit(f"ffmpeg download failed ({e}) — install it manually (see README.md).")
    return FFMPEG_LOCAL


def ensure_ocr():
    """Compile ocr.swift (macOS Vision text recognition) once; reuse after."""
    if not os.path.exists(OCR_SWIFT):
        sys.exit(f"{OCR_SWIFT} is missing — it ships with this project (see README.md).")
    if os.path.exists(OCR_BIN) and os.path.getmtime(OCR_BIN) >= os.path.getmtime(OCR_SWIFT):
        return OCR_BIN
    if not shutil.which("swiftc"):
        sys.exit(
            "swiftc not found — the OCR helper needs Apple's Command Line Tools.\n"
            "Install them with:  xcode-select --install   (one-time), then re-run."
        )
    print("Compiling the OCR helper (one-time, ~30s)...", flush=True)
    r = subprocess.run(["swiftc", "-O", "-o", OCR_BIN, OCR_SWIFT], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"OCR helper failed to compile:\n{r.stderr}")
    return OCR_BIN


# ---------------------------------------------------------------- radios

CASING_TEMPLATE = """\
# Exact artist-name casing for names that are not simple "Title Case",
# for this radio. The watch mode reads the stream's on-screen overlay,
# which prints everything in CAPITALS, so the script rewrites names to
# Title Case ("ARNIE WAY" -> "Arnie Way"). Any name listed here keeps
# the exact casing written below instead — use it for artists whose
# names are intentionally UPPERCASE, lowercase, or otherwise unusual.
#
# One name per line, matching is case-insensitive, '#' lines are comments.
# (Names containing dots or digits, like A.M.R, are already left alone.)
"""


class Radio:
    def __init__(self, name):
        self.name = name
        self.folder = os.path.join(RADIOS_DIR, name)
        self.songs_csv = os.path.join(self.folder, "songs.csv")
        self.config_path = os.path.join(self.folder, "config.json")
        self.casing_path = os.path.join(self.folder, "artist-casing.txt")
        self.cfg = None
        self.url = None


def resolve_radio(args):
    """Pick the radio folder, create/read its config.json, migrate old data."""
    os.makedirs(RADIOS_DIR, exist_ok=True)
    name = args.radio
    if not name:
        existing = sorted(
            d for d in os.listdir(RADIOS_DIR) if os.path.isdir(os.path.join(RADIOS_DIR, d))
        )
        if len(existing) > 1:
            sys.exit(
                "Several radios exist: " + ", ".join(existing)
                + f"\nPick one, e.g.:  python3 radio_tracklog.py {args.command} {existing[0]}"
            )
        name = existing[0] if existing else DEFAULT_RADIO
    radio = Radio(name)
    os.makedirs(radio.folder, exist_ok=True)
    # one-time migration from the old single-radio layout (tracklog/songs.csv)
    old = os.path.join(SCRIPT_DIR, "tracklog", "songs.csv")
    if name == DEFAULT_RADIO and os.path.exists(old) and not os.path.exists(radio.songs_csv):
        os.replace(old, radio.songs_csv)
        print(f"Moved existing songs.csv into {radio.folder}/", flush=True)
    if not os.path.exists(radio.config_path):
        with open(radio.config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
            f.write("\n")
        print(f"Created {radio.config_path} — adjust the parameters there.", flush=True)
    if not os.path.exists(radio.casing_path):
        with open(radio.casing_path, "w", encoding="utf-8") as f:
            f.write(CASING_TEMPLATE)
    cfg = dict(DEFAULT_CONFIG)
    with open(radio.config_path, encoding="utf-8") as f:
        cfg.update(json.load(f))
    radio.cfg = cfg
    radio.url = args.url or cfg["url"]
    return radio


# ------------------------------------------------------- name normalizing

# lowercase these mid-name when fixing SHOUTING text ("QUEEN OF HEARTS")
SMALL_WORDS = {
    "a", "an", "and", "at", "by", "de", "del", "for", "from", "in", "into",
    "of", "on", "or", "the", "to", "van", "von", "with",
}
# artist separators, kept (lowercased) while each side is normalized alone
SEP_RE = re.compile(
    r"\s*,\s+|\s+&\s+|\s+x\s+|\s+vs\.?\s+|\s+ft\.?\s+|\s+feat\.?\s+"
    r"|\s+featuring\s+|\s+pres\.?\s+|\s+presents\s+",
    re.IGNORECASE,
)


def load_artist_casing(radio):
    """The radio's artist-casing.txt: exact spellings that defy Title Case."""
    casing = {}
    if os.path.exists(radio.casing_path):
        with open(radio.casing_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    casing[line.lower()] = line
    return casing


def _cap(word):
    """Capitalize the first letter, lowercase the rest ('(REMIX)' -> '(Remix)')."""
    for i, c in enumerate(word):
        if c.isalpha():
            return word[:i] + c.upper() + word[i + 1:].lower()
    return word


def _title_chunk(chunk, casing):
    if chunk.lower() in casing:
        return casing[chunk.lower()]
    words = []
    for i, w in enumerate(chunk.split()):
        lw = w.lower()
        if lw in casing:
            words.append(casing[lw])
        elif "." in w or any(c.isdigit() for c in w):
            words.append(w)  # A.M.R, MK2, years — leave untouched
        elif i and lw in SMALL_WORDS:
            words.append(lw)
        else:
            words.append(_cap(w))
    return " ".join(words)


def normalize_name(text, casing):
    """Fix SHOUTING overlay text: 'ARNIE WAY & TOUTOUNJI' -> 'Arnie Way & Toutounji'.

    Text that isn't all-capitals is returned untouched (chat already has
    proper casing); artist-casing.txt pins names that should stay unusual
    (PROFF, zensei, ...).
    """
    text = " ".join(text.split())
    if not text or text != text.upper():
        return text
    if text.lower() in casing:
        return casing[text.lower()]
    out, pos = [], 0
    for m in SEP_RE.finditer(text):
        out += [_title_chunk(text[pos:m.start()], casing), m.group(0).lower()]
        pos = m.end()
    out.append(_title_chunk(text[pos:], casing))
    return "".join(out)


# --------------------------------------------------------------- songbook

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
    """songs.csv: one row per song; counter and last_played update on repeat.

    Songs are keyed case-insensitively so the chat bot ("zensei") and the
    on-screen overlay ("ZENSEI") never create duplicate rows.
    """

    def __init__(self, path):
        self.path = path
        self.dirty = False  # unsaved changes in memory
        self._mtime = None  # file mtime our in-memory state is based on
        self._load()

    def _load(self):
        self.songs = {}  # (artist.lower(), title.lower()) -> row dict
        self.max_last = None  # newest last_played; guards against chat backlog
        if not os.path.exists(self.path):
            return
        self._mtime = os.path.getmtime(self.path)
        with open(self.path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row = {k: row.get(k, "") for k in FIELDS}
                row["plays"] = int(row["plays"] or 1)
                self.songs[(row["artist"].lower(), row["title"].lower())] = row
                last = dt.datetime.fromisoformat(row["last_played"])
                if self.max_last is None or last > self.max_last:
                    self.max_last = last

    def refresh(self):
        """Pick up spins another process saved meanwhile (watch + log can
        run at the same time; syncing through the file before counting is
        what lets the same-spin window suppress cross-mode double counts)."""
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return
        if mtime != self._mtime:
            self._load()

    def add_spin(self, ts, title, artist):
        """Count one spin; returns 'new', 'repeat', or None (backlog / same spin)."""
        # chat backlog is re-sent on every (re)start — never re-count the past
        if self.max_last is not None and ts <= self.max_last:
            return None
        self.max_last = ts
        self.dirty = True
        iso = ts.isoformat(timespec="seconds")
        song = self.songs.get((artist.lower(), title.lower()))
        if song is None:
            self.songs[(artist.lower(), title.lower())] = {
                "first_added": iso, "plays": 1, "last_played": iso,
                "artist": artist, "title": title, "youtube": "", "year": "",
            }
            return "new"
        # a source finally delivered nicer casing than SHOUTING — keep it
        if song["artist"] == song["artist"].upper() and artist != artist.upper():
            song["artist"] = artist
        if song["title"] == song["title"].upper() and title != title.upper():
            song["title"] = title
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
        self._mtime = os.path.getmtime(self.path)
        self.dirty = False


def record_spin(book, ytdlp, ts, title, artist):
    """Count a spin, enrich+save new songs; returns the line to print, or None."""
    book.refresh()  # sync with a concurrently running watch/log process
    result = book.add_spin(ts, title, artist)
    if not result:
        if book.dirty:  # same-spin: last_played moved — persist it so the
            book.save()  # other process's same-spin window sees it too
        return None
    song = book.songs[(artist.lower(), title.lower())]
    if result == "new":
        song["youtube"], song["year"] = (
            v or "" for v in lookup_song(ytdlp, song["artist"], song["title"])
        )
    book.save()
    if result == "new":
        extra = f"  ({song['year'] or 'year?'})  {song['youtube'] or 'no link found'}"
        label = "NEW song added"
    else:
        extra, label = "", f"play #{song['plays']}"
    return f"[{ts:%Y-%m-%d %H:%M}] {label}: {song['artist']} — {song['title']}{extra}"


# ------------------------------------------------------------- chat mode

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


def remove_chat_dumps(folder, base=None):
    """Chat dumps are only a transport; delete them once a session is over."""
    pattern = (base + ".live_chat.json*") if base else os.path.join(folder, "chat-*.live_chat.json*")
    for fn in glob.glob(pattern):
        try:
            os.remove(fn)
        except OSError:
            pass


def _sigterm(*_):
    raise KeyboardInterrupt


def cmd_log(args):
    radio = resolve_radio(args)
    signal.signal(signal.SIGTERM, _sigterm)  # clean up on `kill` too, not just Ctrl+C
    remove_chat_dumps(radio.folder)  # leftovers from previous runs
    ytdlp = find_ytdlp(args.ytdlp)
    casing = load_artist_casing(radio)
    book = SongBook(radio.songs_csv)
    print(f"Logging tracks from {radio.url}", flush=True)
    print(f"Songs file: {radio.songs_csv}  (Ctrl+C to stop)", flush=True)

    proc = None
    quick_fails = 0
    try:
        while True:
            started = time.monotonic()
            session = os.path.join(
                radio.folder, "chat-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
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
                    radio.url,
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
                    title = normalize_name(track[0], casing)
                    artist = normalize_name(track[1], casing)
                    line = record_spin(book, ytdlp, ts, title, artist)
                    if line:
                        print(line, flush=True)
            remove_chat_dumps(radio.folder, session)
            if proc.returncode != 0 and time.monotonic() - started < QUICK_FAIL_SECONDS:
                quick_fails += 1
            else:
                quick_fails = 0
            if quick_fails >= UPDATE_AFTER_FAILURES:
                print(
                    f"yt-dlp failed {quick_fails} times in a row — "
                    "probably outdated, fetching the latest standalone build...",
                    flush=True,
                )
                fresh = download_ytdlp(ytdlp)
                if fresh:
                    ytdlp = fresh
                    quick_fails = 0
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
        remove_chat_dumps(radio.folder)
        if book.dirty:
            book.save()
    cmd_stats(args)


# ------------------------------------------------------------ watch mode

def resolve_manifest(ytdlp, url):
    """The stream's HLS playlist URL (expires after a few hours), or None."""
    try:
        r = subprocess.run(
            [ytdlp, "-g", "-f", STREAM_FORMAT, url],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return None
    lines = r.stdout.strip().splitlines()
    return lines[0] if lines and lines[0].startswith("http") else None


def http_get(url, timeout=20):
    import urllib.request

    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def grab_frame(ffmpeg, manifest_url, frame_path):
    """Newest HLS segment -> one JPEG frame. Raises OSError when anything fails."""
    playlist = http_get(manifest_url).decode("utf-8", "replace")
    segs = [ln for ln in playlist.splitlines() if ln and not ln.startswith("#")]
    if not segs:
        raise OSError("empty HLS playlist")
    seg = segs[-1]
    if not seg.startswith("http"):
        seg = manifest_url.rsplit("/", 1)[0] + "/" + seg
    seg_path = frame_path + ".seg.ts"
    with open(seg_path, "wb") as f:
        f.write(http_get(seg))
    try:
        r = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", seg_path,
             "-frames:v", "1", "-q:v", "2", "-y", frame_path],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0 or not os.path.exists(frame_path):
            raise OSError(f"ffmpeg: {r.stderr.strip()[:200]}")
    finally:
        try:
            os.remove(seg_path)
        except OSError:
            pass


def read_overlay(ocr_bin, frame_path, region):
    """OCR the frame; returns (title, artist) from the overlay or None.

    The overlay puts the artist on top and the title below it. The OCR
    helper prints one line per recognized text with its x/y position as
    fractions from the bottom-left; only text inside `region` is used.
    """
    r = subprocess.run([ocr_bin, frame_path], capture_output=True, text=True, timeout=120)
    rows = []
    for line in r.stdout.splitlines():
        try:
            coords, text = line.split("\t", 1)
            x, y = (float(v) for v in coords.split())
        except ValueError:
            continue
        if (region["x"][0] <= x <= region["x"][1]
                and region["y"][0] <= y <= region["y"][1] and text.strip()):
            rows.append((y, x, text.strip()))
    # group into visual lines (same height), left to right, top first
    rows.sort(key=lambda t: (-round(t[0], 2), t[1]))
    lines = []
    for y, _x, text in rows:
        if lines and abs(lines[-1][0] - y) < 0.025:
            lines[-1] = (lines[-1][0], lines[-1][1] + " " + text)
        else:
            lines.append((y, text))
    if len(lines) < 2:
        return None
    return lines[1][1], lines[0][1]  # (title, artist)


def cmd_watch(args):
    if sys.platform != "darwin":
        sys.exit(
            "watch mode reads the on-screen overlay with macOS's built-in OCR,\n"
            "so it only runs on a Mac — use the chat-based `log` mode instead."
        )
    radio = resolve_radio(args)
    signal.signal(signal.SIGTERM, _sigterm)
    ytdlp = find_ytdlp(args.ytdlp)
    ffmpeg = find_ffmpeg()
    ocr = ensure_ocr()
    casing = load_artist_casing(radio)
    book = SongBook(radio.songs_csv)
    interval = float(radio.cfg["capture_interval_seconds"])
    region = radio.cfg["ocr_region"]
    frame = os.path.join(radio.folder, ".frame.jpg")
    print(f"Watching {radio.name}: {radio.url}", flush=True)
    print(f"One frame every {interval:.0f}s -> {radio.songs_csv}  (Ctrl+C to stop)", flush=True)
    print("'.' = same song still playing, '?' = overlay unreadable, 'x' = capture hiccup", flush=True)

    manifest = None
    last = None
    pending_dots = False

    def note(sym):
        nonlocal pending_dots
        print(sym, end="", flush=True)
        pending_dots = True

    try:
        while True:
            t0 = time.monotonic()
            got = None
            try:
                if manifest is None:
                    manifest = resolve_manifest(ytdlp, radio.url)
                    if not manifest:
                        raise OSError("could not resolve the stream manifest")
                grab_frame(ffmpeg, manifest, frame)
                got = read_overlay(ocr, frame, region)
            except (OSError, subprocess.SubprocessError):
                manifest = None  # URL likely expired — resolve again next round
                note("x")
            else:
                if got is None:
                    note("?")
                else:
                    title = normalize_name(got[0], casing)
                    artist = normalize_name(got[1], casing)
                    if (artist.lower(), title.lower()) == last:
                        note(".")
                    else:
                        last = (artist.lower(), title.lower())
                        line = record_spin(book, ytdlp, dt.datetime.now(), title, artist)
                        if line:
                            if pending_dots:
                                print(flush=True)
                                pending_dots = False
                            print(line, flush=True)
                        else:
                            note(".")  # e.g. brief flap back to the previous song
            time.sleep(max(1.0, interval - (time.monotonic() - t0)))
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        try:
            os.remove(frame)
        except OSError:
            pass
        if book.dirty:
            book.save()
    cmd_stats(args)


# ----------------------------------------------------------- read-only

def load_book(radio):
    if not os.path.exists(radio.songs_csv):
        sys.exit(
            f"No songs logged yet for {radio.name} ({radio.songs_csv} missing). "
            "Run: radio_tracklog.py watch"
        )
    return SongBook(radio.songs_csv)


def print_songs(rows):
    print(f"{'first added':<12} {'plays':>5}  {'last played':<12} {'year':<5} song")
    for r in rows:
        print(
            f"{r['first_added'][:10]:<12} {r['plays']:>5}  {r['last_played'][:10]:<12} "
            f"{(r['year'] or '?'):<5} {r['artist']} — {r['title']}"
        )


def cmd_list(args):
    radio = resolve_radio(args)
    book = load_book(radio)
    print(f"\n{len(book.songs)} songs (no duplicates), oldest first — file: {radio.songs_csv}\n")
    print_songs(sorted(book.songs.values(), key=lambda r: r["first_added"]))


def cmd_stats(args):
    radio = resolve_radio(args)
    book = load_book(radio)
    total = sum(r["plays"] for r in book.songs.values())
    print(f"\n{total} spins counted, {len(book.songs)} distinct songs — most played first\n")
    print_songs(sorted(book.songs.values(), key=lambda r: -r["plays"]))


def cmd_enrich(args):
    """Fill in the youtube + year columns via a YouTube search per song."""
    radio = resolve_radio(args)
    ytdlp = find_ytdlp(args.ytdlp)
    book = load_book(radio)
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
    print(f"\nDone. Updated {radio.songs_csv}")


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "command", nargs="?", default="log",
        choices=["watch", "log", "list", "stats", "enrich"],
    )
    p.add_argument(
        "radio", nargs="?", default=None,
        help="radio folder name under radios/ (default: the only one there)",
    )
    p.add_argument("--url", default=None, help="override the radio's YouTube URL")
    p.add_argument("--ytdlp", default=None, help="path to yt-dlp (default: auto-detect)")
    args = p.parse_args()
    {
        "watch": cmd_watch, "log": cmd_log, "list": cmd_list,
        "stats": cmd_stats, "enrich": cmd_enrich,
    }[args.command](args)


if __name__ == "__main__":
    main()
