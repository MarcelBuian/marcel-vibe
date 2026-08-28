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
  python3 radio_tracklog.py download [radio] # backfill missing mp3s
  python3 radio_tracklog.py playlist [radio] # sync songs into the YouTube playlist
  python3 radio_tracklog.py casing [radio]   # verify artist casing against YouTube titles

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
import unicodedata

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
    # every date/time the script writes (songs.csv, lock, quota marker) is
    # in THIS zone, whatever zone the Mac is set to — so travelling never
    # shifts the log. IANA name ("Europe/Malta", "UTC") or a fixed offset
    # ("+02:00"). Malta observes DST, hence the name rather than "+02".
    "timezone": "Europe/Malta",
    # watch mode: how often to grab a frame and read the overlay
    "capture_interval_seconds": 60,
    # enabled: download every logged song as a best-quality mp3 into
    # radios/<name>/mp3/ (see also the `download` command for backfilling).
    # prefer: bias the YouTube search that picks THE link for a song
    # (csv + playlist + mp3), e.g. "extended mix" or "radio edit".
    # use_ignore_file: skip songs listed in the radio's ignore.txt.
    "download_mp3": {"enabled": False, "prefer": "", "use_ignore_file": True},
    # enabled + link: add every logged song to this YouTube playlist
    # (needs the one-time Google authorization — see README and the
    # `playlist` command). use_ignore_file: skip songs from ignore.txt.
    "save_to_yt_playlist": {"enabled": False, "link": "", "use_ignore_file": True},
    # watch mode: where the now-playing overlay sits in the frame, as
    # fractions of width/height measured from the BOTTOM-LEFT corner
    "ocr_region": {"x": [0.12, 0.75], "y": [0.02, 0.40]},
}

BOT_AUTHORS = {"@monstercatbot", "monstercatbot"}
# "@user loves 'Title' by Artist!"  /  "Now Playing: 'Title' by Artist"
TRACK_RE = re.compile(r"'(?P<title>[^']+)' by (?P<artist>.+?)[!.]?\s*$")
# Same track re-announced within this window counts as the same spin.
SAME_SPIN_SECONDS = 12 * 60

# The zone all timestamps are expressed in; set from config.json by
# resolve_radio(). Until then (module import, tests) the Mac's zone is used.
TZ = None


def parse_timezone(name):
    """'Europe/Malta' / 'UTC' / '+02:00' / '-0530' -> tzinfo, or raise ValueError."""
    name = (name or "").strip()
    m = re.fullmatch(r"(?:UTC|GMT)?([+-])(\d{1,2})(?::?(\d{2}))?", name)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        delta = dt.timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0))
        return dt.timezone(sign * delta, name)
    if name.upper() == "UTC":
        return dt.timezone.utc
    try:
        import zoneinfo

        return zoneinfo.ZoneInfo(name)
    except Exception as e:  # unknown key or no zoneinfo module (Python < 3.9)
        raise ValueError(f"unknown timezone {name!r} ({e})") from None


def now():
    """Current wall-clock time in the configured zone, naive (as stored in songs.csv)."""
    return dt.datetime.now(TZ).replace(tzinfo=None)


def today():
    return now().date()


def from_epoch(seconds):
    """Unix time -> naive datetime in the configured zone."""
    return dt.datetime.fromtimestamp(seconds, TZ).replace(tzinfo=None)

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


def find_ffmpeg(optional=False):
    """Locate ffmpeg (project folder or PATH); auto-download it on macOS.

    With optional=True a missing ffmpeg returns None instead of exiting
    (mp3 downloads are then skipped rather than killing the logger).
    """
    for c in (FFMPEG_LOCAL, shutil.which("ffmpeg")):
        if c and os.path.exists(c):
            return c
    if sys.platform != "darwin":
        if optional:
            return None
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


IGNORE_TEMPLATE = """\
# ignore.txt — songs this radio should SKIP.
#
# The logger still records every song it hears in songs.csv (the history
# stays complete); this list only stops the two follow-up actions:
#   - downloading the song as an mp3        (download_mp3.use_ignore_file)
#   - adding the song to the YouTube playlist (save_to_yt_playlist.use_ignore_file)
# Each action obeys this list only while its use_ignore_file flag in
# config.json is true.
#
# One entry per line, in either form:
#
#   https://www.youtube.com/watch?v=dQw4w9WgXcQ     a YouTube link
#   dQw4w9WgXcQ                                     ...or just the video id
#   Some Artist - Some Song                         artist - title
#
# Artist - Title entries match case- and accent-insensitively (SOME
# ARTIST / Söme Ärtist all count). Lines starting with # are comments.
# Changes are picked up when a logger starts — restart a running watch
# after editing.
"""


class Radio:
    def __init__(self, name):
        self.name = name
        self.folder = os.path.join(RADIOS_DIR, name)
        self.songs_csv = os.path.join(self.folder, "songs.csv")
        self.config_path = os.path.join(self.folder, "config.json")
        self.casing_path = os.path.join(self.folder, "artist-casing.txt")
        self.ignore_path = os.path.join(self.folder, "ignore.txt")
        self.cfg = None
        self.url = None
        self.ignore = None  # parsed ignore.txt
        self.prefer = ""  # search bias, e.g. "extended mix"


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
    if not os.path.exists(radio.ignore_path):
        with open(radio.ignore_path, "w", encoding="utf-8") as f:
            f.write(IGNORE_TEMPLATE)
    with open(radio.config_path, encoding="utf-8") as f:
        raw = json.load(f)
    cfg = {}
    for k, v in DEFAULT_CONFIG.items():  # defaults + one level of nesting
        rv = raw.get(k)
        cfg[k] = {**v, **(rv if isinstance(rv, dict) else {})} if isinstance(v, dict) \
            else raw.get(k, v)
    # Migrate older config layouts. Old values only ever overwrite when they
    # actually carry something — an old process re-adding its empty defaults
    # must never blank out values a newer layout already holds.
    legacy_keys = {"download", "youtube_playlist", "ignore", "playlist", "save_to_playlist"}
    dl, pl = cfg["download_mp3"], cfg["save_to_yt_playlist"]
    if isinstance(raw.get("download_mp3"), bool):  # the original flat toggle
        dl["enabled"] = raw["download_mp3"]
    if isinstance(raw.get("download"), dict):
        d = raw["download"]
        dl["enabled"] = d.get("mp3", dl["enabled"])
        dl["prefer"] = d.get("prefer") or dl["prefer"]
        dl["use_ignore_file"] = d.get("use_ignore_file", d.get("ignore", dl["use_ignore_file"]))
    if raw.get("youtube_playlist"):
        pl["link"] = raw["youtube_playlist"]
    if isinstance(raw.get("ignore"), dict):
        dl["use_ignore_file"] = raw["ignore"].get("apply_to_downloads", True)
        pl["use_ignore_file"] = raw["ignore"].get("apply_to_playlist", True)
    for old in ("playlist", "save_to_playlist"):  # short-lived earlier names
        if isinstance(raw.get(old), dict):
            p = raw[old]
            pl["link"] = p.get("link") or pl["link"]
            pl["use_ignore_file"] = p.get("use_ignore_file", p.get("ignore", pl["use_ignore_file"]))
    if "enabled" not in (raw.get("save_to_yt_playlist") or {}):
        pl["enabled"] = bool(pl["link"])  # flag is new — on when a link exists
    dl.pop("mp3", None)
    dl.pop("ignore", None)
    pl.pop("ignore", None)
    for k, v in raw.items():  # keep unknown keys a user may have added
        if k not in cfg and k not in legacy_keys:
            cfg[k] = v
    if cfg != raw:
        with open(radio.config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        print(f"Upgraded {radio.config_path} to the current settings layout.", flush=True)
    radio.cfg = cfg
    global TZ
    try:
        TZ = parse_timezone(cfg["timezone"])
    except ValueError as e:
        sys.exit(f'{radio.config_path}: "timezone" — {e}. Use an IANA name like '
                 f'"Europe/Malta" or an offset like "+02:00".')
    radio.url = args.url or cfg["url"]
    radio.prefer = (cfg["download_mp3"].get("prefer") or "").strip()
    radio.ignore = load_ignore(radio)
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
    r"|\s+featuring\s+|\s+pres\.?\s+|\s+presents\s+|\s+w/\s+",
    re.IGNORECASE,
)


def fold(text):
    """Accent-insensitive form of a name — OCR reads NŌPI as NÖPI/NÓPI/NOPI
    depending on the frame, so all matching happens on the folded form."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.translate(str.maketrans({
        "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
        "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
    }))


def song_key(artist, title):
    """Case- and accent-insensitive identity of a song."""
    return (fold(artist).lower(), fold(title).lower())


def load_artist_casing(radio):
    """The radio's artist-casing.txt: exact spellings that defy Title Case.

    Keys are folded, so one entry ("Nōpi") covers every diacritic variant
    OCR may produce for it. A line "Wrong -> Right" additionally maps an
    OCR misspelling to the correct name (e.g. "Rasim -> Ra5im", because
    the overlay's 5 reads as an S).
    """
    casing = {}
    if os.path.exists(radio.casing_path):
        with open(radio.casing_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "->" in line:
                    wrong, right = (p.strip() for p in line.split("->", 1))
                    if wrong and right:
                        casing[fold(wrong).lower()] = right
                else:
                    casing[fold(line).lower()] = line
    return casing


def _cap(word):
    """Capitalize the first letter, lowercase the rest ('(REMIX)' -> '(Remix)')."""
    for i, c in enumerate(word):
        if c.isalpha():
            return word[:i] + c.upper() + word[i + 1:].lower()
    return word


def _title_chunk(chunk, casing):
    if fold(chunk).lower() in casing:
        return casing[fold(chunk).lower()]
    words = []
    for i, w in enumerate(chunk.split()):
        lw = w.lower()
        if fold(w).lower() in casing:
            words.append(casing[fold(w).lower()])
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
    if not text:
        return text
    if fold(text).lower() in casing:
        return casing[fold(text).lower()]
    if text != text.upper():
        # already cased (chat) — only enforce the pinned spellings, so a
        # chat "Oracle & Jeans" can't undo a verified "ORACLE & JEANS"
        return _recase(text, casing)
    out, pos = [], 0
    for m in SEP_RE.finditer(text):
        out += [_title_chunk(text[pos:m.start()], casing), m.group(0).lower()]
        pos = m.end()
    out.append(_title_chunk(text[pos:], casing))
    return "".join(out)


# --------------------------------------------------------------- songbook

def _yt_search(ytdlp, query, n):
    """yt-dlp search: list of (url, year_or_None, video_title)."""
    try:
        out = subprocess.run(
            [
                ytdlp,
                "--skip-download",
                "--print",
                "%(webpage_url)s\t%(release_year,upload_date>%Y)s\t%(title)s",
                f"ytsearch{n}:{query}",
            ],
            capture_output=True, text=True, timeout=90,
        ).stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return []
    results = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("http"):
            results.append((parts[0], parts[1] if parts[1].isdigit() else None, parts[2]))
    return results


def lookup_song(ytdlp, artist, title, prefer=""):
    """Search YouTube for the song; returns (url, year) — either may be None.

    With prefer (e.g. "extended mix"), results whose video title contains
    that phrase win; otherwise it falls back to the plain best match.
    """
    if prefer:
        # strict phrase match: "Cola (ARTBAT Extended Remix)" must NOT count
        # as the extended mix of "Cola" — better the plain original than a
        # different version by someone else
        for url, year, vtitle in _yt_search(ytdlp, f"{artist} {title} {prefer}", 8):
            if fold(prefer).lower() in fold(vtitle).lower():
                return url, year
    results = _yt_search(ytdlp, f"{artist} {title}", 1)
    return results[0][:2] if results else (None, None)


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
        self.songs = {}  # song_key(artist, title) -> row dict
        self.max_last = None  # newest last_played; guards against chat backlog
        if not os.path.exists(self.path):
            return
        self._mtime = os.path.getmtime(self.path)
        with open(self.path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row = {k: row.get(k, "") for k in FIELDS}
                row["plays"] = int(row["plays"] or 1)
                key = song_key(row["artist"], row["title"])
                if key in self.songs:  # rows written before key folding — merge
                    m = self.songs[key]
                    m["plays"] += row["plays"]
                    m["first_added"] = min(m["first_added"], row["first_added"])
                    m["last_played"] = max(m["last_played"], row["last_played"])
                    m["youtube"] = m["youtube"] or row["youtube"]
                    m["year"] = m["year"] or row["year"]
                    self.dirty = True
                else:
                    self.songs[key] = row
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

    def add_spin(self, ts, title, artist, guard_backlog=True):
        """Count one spin; returns 'new', 'repeat', or None (backlog / same spin).

        guard_backlog: the chat logger gets the chat history re-sent on
        every (re)start, so anything not newer than the newest row is
        skipped. A live OCR read is never a backlog — `watch` passes False;
        otherwise a clock that moved back (config "timezone" changed, Mac
        clock corrected) would drop every song until it catches up with the CSV.
        """
        if guard_backlog and self.max_last is not None and ts <= self.max_last:
            return None
        if self.max_last is None or ts > self.max_last:
            self.max_last = ts
        self.dirty = True
        iso = ts.isoformat(timespec="seconds")
        song = self.songs.get(song_key(artist, title))
        if song is None:
            self.songs[song_key(artist, title)] = {
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
        # abs(): a last_played more than 12 min in the *future* means the
        # clock/timezone moved back — that's a real new spin, not the same one
        same_spin = abs((ts - last).total_seconds()) < SAME_SPIN_SECONDS
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


def mp3_path(radio, song):
    """radios/<name>/mp3/Artist - Title - Year.mp3 (year only when known)."""
    name = f"{song['artist']} - {song['title']}"
    if song.get("year"):
        name += f" - {song['year']}"
    safe = re.sub(r'[\\/:*?"<>|]', "_", name)
    return os.path.join(radio.folder, "mp3", safe + ".mp3")


def download_mp3(radio, ytdlp, song, wait=False):
    """Download a song's YouTube link as best-quality mp3 into radios/<name>/mp3/.

    wait=False (the live loggers) runs yt-dlp in the background so the
    capture loop keeps its rhythm; wait=True (the `download` command)
    blocks and returns True/False.
    """
    url = song.get("youtube")
    dest = mp3_path(radio, song)
    if not url or os.path.exists(dest):
        return None
    ffmpeg = find_ffmpeg(optional=True)
    if not ffmpeg:
        return None  # mp3 conversion impossible; logging goes on regardless
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    import shlex

    # clean ID3 tags from our own (normalized) data, not the YouTube title
    tags = f"-metadata {shlex.quote('artist=' + song['artist'])} " \
           f"-metadata {shlex.quote('title=' + song['title'])}"
    if song.get("year"):
        tags += f" -metadata date={song['year']}"
    cmd = [
        ytdlp, "-f", "bestaudio", "-x", "--audio-format", "mp3",
        "--audio-quality", "0", "--ffmpeg-location", ffmpeg,
        "--embed-thumbnail", "--convert-thumbnails", "jpg",  # cover art in the file
        "--postprocessor-args", f"ExtractAudio+ffmpeg:{tags}",
        "--no-progress", "-o", dest[: -len(".mp3")] + ".%(ext)s", url,
    ]
    if wait:
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode == 0 and os.path.exists(dest)
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def finished_downloads(downloads):
    """Yield (song, ok) for background mp3 downloads that have finished."""
    for item in downloads[:]:
        proc, song, dest = item
        if proc.poll() is None:
            continue
        downloads.remove(item)
        yield song, proc.returncode == 0 and os.path.exists(dest)


def warn_clock_skew(book, mode):
    """Say so when songs.csv holds timestamps from the future.

    Happens when the Mac's clock or timezone moved back (e.g. travelling
    west: the zone switch turns 12:44 into 11:44). Timestamps are local
    wall-clock time, so the CSV keeps a one-hour discontinuity there; the
    loggers keep working, but the chat logger's backlog guard skips songs
    until the clock has caught up.
    """
    ts = now()
    if book.max_last is None or book.max_last <= ts + dt.timedelta(minutes=1):
        return
    ahead = int((book.max_last - ts).total_seconds() // 60)
    msg = (f"note: the newest last_played in songs.csv ({book.max_last:%Y-%m-%d %H:%M}) is "
           f"{ahead} min ahead of the current time in {TZ} ({ts:%H:%M}) — was the "
           f'"timezone" in config.json changed, or is the Mac\'s clock off?')
    if mode == "log":
        msg += f" Chat announcements are ignored until {book.max_last:%H:%M}."
    print(msg, flush=True)


def record_spin(book, ytdlp, ts, title, artist, radio=None, downloads=None, live=False):
    """Count a spin, enrich+save new songs; returns the line to print, or None.

    live=True marks a spin observed right now (OCR frame) rather than read
    from a chat dump that may contain history — see SongBook.add_spin.
    """
    book.refresh()  # sync with a concurrently running watch/log process
    result = book.add_spin(ts, title, artist, guard_backlog=not live)
    if not result:
        if book.dirty:  # same-spin: last_played moved — persist it so the
            book.save()  # other process's same-spin window sees it too
        return None
    song = book.songs[song_key(artist, title)]
    if result == "new":
        song["youtube"], song["year"] = (
            v or "" for v in lookup_song(
                ytdlp, song["artist"], song["title"], radio.prefer if radio else ""
            )
        )
    book.save()
    notes = ""
    if result == "new" and radio and radio.cfg["download_mp3"]["enabled"]:
        if radio.cfg["download_mp3"].get("use_ignore_file") and is_ignored(radio, song):
            notes += "  [mp3: on the ignore list]"
        else:
            proc = download_mp3(radio, ytdlp, song)  # in the background; loop keeps going
            if proc is not None:
                notes += "  [mp3 downloading...]"
                if downloads is not None:
                    downloads.append((proc, song, mp3_path(radio, song)))
    if result == "new" and radio and playlist_enabled(radio):
        vid = video_id(song["youtube"])
        cache = read_playlist_cache(radio)
        if not vid:
            pass
        elif radio.cfg["save_to_yt_playlist"].get("use_ignore_file") and is_ignored(radio, song):
            notes += "  [playlist: on the ignore list]"
        elif cache is None:
            notes += "  [playlist: run `radio_tracklog.py playlist` once first]"
        elif song_in_playlist(song, cache):
            notes += "  [already in playlist]"
        elif quota_blocked_today(radio):
            notes += "  [playlist: daily quota reached — auto-resumes tomorrow]"
        else:
            token = google_access_token()  # silent: None until the one-time auth ran
            if not token:
                notes += "  [playlist: authorize once with: radio_tracklog.py playlist]"
            else:
                ok, reason = playlist_insert(token, playlist_id(radio), vid)
                if ok:
                    append_playlist_cache(radio, vid, song["title"], song["artist"])
                    notes += "  [playlist ok]"
                elif reason == "quotaExceeded":
                    mark_quota(radio)
                    notes += "  [playlist: daily quota reached — auto-resumes tomorrow]"
                else:
                    notes += f"  [playlist: {reason}]"
    if result == "new":
        extra = f"  ({song['year'] or 'year?'})  {song['youtube'] or 'no link found'}"
        label = "NEW song added"
    else:
        extra, label = "", f"play #{song['plays']}"
    return f"[{ts:%Y-%m-%d %H:%M}] {label}: {song['artist']} — {song['title']}{extra}{notes}"


# -------------------------------------------------- youtube playlist sync

GOOGLE_OAUTH_FILE = os.path.join(SCRIPT_DIR, "google-oauth.json")
GOOGLE_TOKEN_FILE = os.path.join(SCRIPT_DIR, ".google-token.json")
YT_SCOPE = "https://www.googleapis.com/auth/youtube"


def http_json(url, data=None, headers=None, timeout=30):
    """POST (form dict / json bytes) or GET a URL; returns the parsed JSON,
    including Google's error responses instead of raising on HTTP errors."""
    import urllib.error
    import urllib.parse
    import urllib.request

    if isinstance(data, dict):
        data = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except ValueError:
            return {"error": f"HTTP {e.code}"}


def playlist_id(radio):
    """The playlist id from save_to_yt_playlist.link (or a bare id)."""
    link = (radio.cfg["save_to_yt_playlist"].get("link") or "").strip()
    if not link:
        return None
    m = re.search(r"[?&]list=([\w-]+)", link)
    return m.group(1) if m else link


def playlist_enabled(radio):
    """Playlist saving is on: enabled in config AND a link is set."""
    return bool(radio.cfg["save_to_yt_playlist"].get("enabled") and playlist_id(radio))


def video_id(url):
    m = re.search(r"[?&]v=([\w-]{6,})", url or "")
    return m.group(1) if m else None


def load_ignore(radio):
    """Parse ignore.txt into video ids and folded 'artist - title' names."""
    ids, names = set(), set()
    if os.path.exists(radio.ignore_path):
        with open(radio.ignore_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                vid = video_id(line) or (line if re.fullmatch(r"[\w-]{11}", line) else None)
                if vid:
                    ids.add(vid)
                else:
                    names.add(fold(" ".join(line.split())).lower())
    return {"ids": ids, "names": names}


def is_ignored(radio, song):
    vid = video_id(song.get("youtube"))
    if vid and vid in radio.ignore["ids"]:
        return True
    return fold(f"{song['artist']} - {song['title']}").lower() in radio.ignore["names"]


# Local mirror of the playlist's content: "video_id<TAB>title<TAB>channel"
# per line. Refreshed from the real playlist by `playlist`; consulted (and
# appended) by the live loggers so nothing is ever added twice. Its absence
# means we don't know the membership yet — then the live loggers refuse to
# add. Matching against it is per SONG, not per upload: a hand-added copy
# of a track (different video id) still counts as "already in playlist".
def playlist_cache_path(radio):
    return os.path.join(radio.folder, "playlist-videos.txt")


def read_playlist_cache(radio):
    """List of (video_id, title, channel) rows, or None if never synced."""
    if not os.path.exists(playlist_cache_path(radio)):
        return None
    rows = []
    with open(playlist_cache_path(radio), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                parts = (line.rstrip("\n").split("\t") + ["", ""])[:3]
                rows.append((parts[0].strip(), parts[1], parts[2]))
    return rows


def write_playlist_cache(radio, rows):
    with open(playlist_cache_path(radio), "w", encoding="utf-8") as f:
        for vid, title, channel in rows:
            f.write(f"{vid}\t{title}\t{channel}\n")


def append_playlist_cache(radio, vid, title, channel):
    with open(playlist_cache_path(radio), "a", encoding="utf-8") as f:
        f.write(f"{vid}\t{title}\t{channel}\n")


# Same-song version suffixes — "Belle (Extended Mix)" IS "Belle"; a remix
# by someone else is NOT, so only these exact words are stripped.
_VERSION_RE = re.compile(
    r"\s*[(\[]\s*(?:extended|radio|original|club)\s+(?:mix|edit|version)\s*[)\]]\s*$"
    r"|\s*[(\[]\s*extended\s*[)\]]\s*$",
    re.IGNORECASE,
)


def _title_key(text):
    return _VERSION_RE.sub("", fold(text)).lower().strip()


def song_in_playlist(song, cache_rows):
    """Is this song already in the playlist — under ANY upload?

    Exact video-id match, or a playlist entry whose (folded) video title
    equals the song title — version suffixes like "(Extended Mix)"
    ignored — and whose channel looks like the song's artist (music
    uploads sit on "<Artist> - Topic" channels). A title match with no
    channel information also counts.
    """
    vid = video_id(song.get("youtube"))
    t = _title_key(song["title"])
    a = fold(song["artist"]).lower()
    artist_parts = [p.strip() for p in re.split(r"[&,]|\bx\b|feat\.?", a) if p.strip()]
    for row_vid, row_title, row_channel in cache_rows:
        if vid and row_vid == vid:
            return True
        if _title_key(row_title) != t:
            continue
        ch = fold(row_channel).lower().replace("- topic", "").strip()
        if not ch or ch in a or any(p in ch or ch in p for p in artist_parts):
            return True
    return False


# The day the YouTube API quota ran out, so every playlist writer backs
# off until the next day (the watcher then resumes automatically).
def quota_path(radio):
    return os.path.join(radio.folder, ".playlist-quota")


def quota_blocked_today(radio):
    try:
        with open(quota_path(radio), encoding="utf-8") as f:
            return f.read().strip() == today().isoformat()
    except OSError:
        return False


def mark_quota(radio):
    with open(quota_path(radio), "w", encoding="utf-8") as f:
        f.write(today().isoformat())


def playlist_pending(radio, book, cache_rows):
    """Songs (with their video ids) not yet in the playlist, oldest first."""
    out, queued = [], set()
    apply_ignore = radio.cfg["save_to_yt_playlist"].get("use_ignore_file")
    for s in sorted(book.songs.values(), key=lambda r: r["first_added"]):
        vid = video_id(s["youtube"])
        if (vid and vid not in queued
                and not song_in_playlist(s, cache_rows)
                and not (apply_ignore and is_ignored(radio, s))):
            out.append((s, vid))
            queued.add(vid)  # two songs can share a search-found link
    return out


def google_access_token(interactive=False):
    """An access token for the YouTube API, or None when not set up.

    Uses the refresh token saved in .google-token.json. With
    interactive=True and no saved token, runs Google's device flow once
    (visit a URL, type a short code) and saves the refresh token.
    """
    if not os.path.exists(GOOGLE_OAUTH_FILE):
        if interactive:
            sys.exit(
                f"{GOOGLE_OAUTH_FILE} is missing.\n"
                'Create it with your Google OAuth client as\n'
                '  {"client_id": "...", "client_secret": "..."}\n'
                "— one-time setup, see README.md (YouTube playlist section)."
            )
        return None
    with open(GOOGLE_OAUTH_FILE, encoding="utf-8") as f:
        client = json.load(f)
    cid, secret = client.get("client_id"), client.get("client_secret")
    if os.path.exists(GOOGLE_TOKEN_FILE):
        with open(GOOGLE_TOKEN_FILE, encoding="utf-8") as f:
            refresh = json.load(f).get("refresh_token")
        if refresh:
            r = http_json("https://oauth2.googleapis.com/token", {
                "client_id": cid, "client_secret": secret,
                "refresh_token": refresh, "grant_type": "refresh_token",
            })
            if r.get("access_token"):
                return r["access_token"]
    if not interactive:
        return None
    d = http_json("https://oauth2.googleapis.com/device/code",
                  {"client_id": cid, "scope": YT_SCOPE})
    if "verification_url" not in d:
        sys.exit(f"Google authorization failed: {d}")
    print(f"\nOne-time authorization: open  {d['verification_url']}")
    print(f"and enter the code:  {d['user_code']}\n(waiting...)", flush=True)
    while True:
        time.sleep(d.get("interval", 5))
        r = http_json("https://oauth2.googleapis.com/token", {
            "client_id": cid, "client_secret": secret,
            "device_code": d["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
        if r.get("access_token"):
            with open(GOOGLE_TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump({"refresh_token": r["refresh_token"]}, f)
            print("Authorized — token saved next to the script.", flush=True)
            return r["access_token"]
        if r.get("error") not in ("authorization_pending", "slow_down"):
            sys.exit(f"Google authorization failed: {r.get('error', r)}")


def playlist_insert(token, pl, vid):
    """Add one video to the playlist; returns (ok, error_reason)."""
    body = json.dumps({"snippet": {
        "playlistId": pl,
        "resourceId": {"kind": "youtube#video", "videoId": vid},
    }}).encode()
    r = http_json(
        "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet",
        body, {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    if "id" in r:
        return True, ""
    err = r.get("error", {})
    reason = (err.get("errors") or [{}])[0].get("reason") or err.get("message") or "failed"
    return False, reason


def playlist_items(token, pl):
    """Everything in the playlist: [{'item', 'vid', 'title', 'channel'}, ...]
    ('item' is the playlist-entry id, needed to delete an entry)."""
    items, page = [], ""
    while True:
        url = ("https://www.googleapis.com/youtube/v3/playlistItems"
               f"?part=snippet&maxResults=50&playlistId={pl}")
        if page:
            url += "&pageToken=" + page
        r = http_json(url, headers={"Authorization": "Bearer " + token})
        if "items" not in r:
            sys.exit(f"Could not read the playlist: {r.get('error', {}).get('message', r)}")
        for i in r["items"]:
            sn = i["snippet"]
            items.append({
                "item": i["id"],
                "vid": sn["resourceId"].get("videoId"),
                "title": sn.get("title", ""),
                "channel": sn.get("videoOwnerChannelTitle", ""),
            })
        page = r.get("nextPageToken", "")
        if not page:
            return items


def cmd_playlist(args):
    """Sync songs.csv into the configured playlist (and refresh the caches)."""
    radio = resolve_radio(args)
    pl = playlist_id(radio)
    if not pl:
        sys.exit(f'Put the playlist link into "save_to_yt_playlist"."link" in {radio.config_path} first.')
    if not radio.cfg["save_to_yt_playlist"].get("enabled"):
        sys.exit(f'Playlist saving is off — set "save_to_yt_playlist"."enabled" to true in {radio.config_path}.')
    token = google_access_token(interactive=True)
    book = load_book(radio)
    existing = playlist_items(token, pl)
    rows = sorted(((i["vid"], i["title"], i["channel"]) for i in existing),
                  key=lambda r: r[1].lower())
    write_playlist_cache(radio, rows)

    # report: playlist entries that match none of our songs — keep an eye on
    songs = list(book.songs.values())
    extra = [i for i in existing
             if not any(song_in_playlist(s, [(i["vid"], i["title"], i["channel"])])
                        for s in songs)]
    report = os.path.join(radio.folder, "playlist-extra.txt")
    with open(report, "w", encoding="utf-8") as f:
        f.write("# In the YouTube playlist but matching no song in songs.csv "
                "(regenerated by `playlist`)\n")
        for i in sorted(extra, key=lambda i: i["title"].lower()):
            # music uploads carry the artist in the channel, not the title
            artist = re.sub(r"\s*-\s*Topic$", "", i["channel"]).strip()
            name = f"{artist} — {i['title']}" if artist else i["title"]
            f.write(f"{name}  https://www.youtube.com/watch?v={i['vid']}\n")

    todo = playlist_pending(radio, book, rows)
    print(f"{radio.name}: {len(existing)} videos in the playlist, "
          f"{len(extra)} of them match no logged song (see {os.path.basename(report)}), "
          f"{len(todo)} songs to add")
    for i, (s, v) in enumerate(todo, 1):
        ok, reason = playlist_insert(token, pl, v)
        print(f"  [{i}/{len(todo)}] {s['artist']} — {s['title']}  ->  {'ok' if ok else reason}",
              flush=True)
        if ok:
            append_playlist_cache(radio, v, s["title"], s["artist"])
        elif reason == "quotaExceeded":
            mark_quota(radio)
            print("Daily YouTube API quota reached — a running `watch` resumes by itself "
                  "tomorrow, or rerun this command.")
            break
    print("Done.")


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
        ts = from_epoch(int(usec) / 1e6) if usec else now()
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


def acquire_single_instance(radio, mode):
    """One `watch`/`log` per radio: exit with a warning when one already runs.

    Uses an OS-level lock on radios/<name>/.<mode>.lock held for the whole
    process lifetime — released automatically by the OS on any kind of
    exit, so a crash never leaves a stale lock behind. The returned file
    handle must stay referenced by the caller.
    """
    try:
        import fcntl
    except ImportError:  # Windows: no flock — run unguarded
        return None
    path = os.path.join(radio.folder, f".{mode}.lock")
    f = open(path, "a+", encoding="utf-8")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.seek(0)
        holder = f.read().strip() or "unknown pid"
        sys.exit(
            f"A `{mode}` for radio '{radio.name}' is already running ({holder}) — "
            "closing this second copy."
        )
    f.seek(0)
    f.truncate()
    f.write(f"pid {os.getpid()}, started {now():%Y-%m-%d %H:%M:%S}\n")
    f.flush()
    return f


def cmd_log(args):
    radio = resolve_radio(args)
    _lock = acquire_single_instance(radio, "log")  # noqa: F841 — held until exit
    signal.signal(signal.SIGTERM, _sigterm)  # clean up on `kill` too, not just Ctrl+C
    remove_chat_dumps(radio.folder)  # leftovers from previous runs
    ytdlp = find_ytdlp(args.ytdlp)
    casing = load_artist_casing(radio)
    book = SongBook(radio.songs_csv)
    warn_clock_skew(book, "log")
    print(f"Logging tracks from {radio.url}", flush=True)
    print(f"Songs file: {radio.songs_csv}  (Ctrl+C to stop)", flush=True)

    proc = None
    quick_fails = 0
    downloads = []  # background mp3 downloads still running
    try:
        while True:
            started = time.monotonic()
            session = os.path.join(
                radio.folder, "chat-" + now().strftime("%Y%m%d-%H%M%S")
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
                for song, ok in finished_downloads(downloads):
                    state = "mp3 saved" if ok else "mp3 download FAILED"
                    print(f"{state}: {song['artist']} — {song['title']}", flush=True)
                for ts, author, text in tail_session(session, offsets, seen):
                    track = parse_track(author, text)
                    if not track:
                        continue
                    title = normalize_name(track[0], casing)
                    artist = normalize_name(track[1], casing)
                    line = record_spin(book, ytdlp, ts, title, artist, radio, downloads)
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
        still = [i for i in downloads if i[0].poll() is None]
        if still:
            print(f"{len(still)} mp3 download(s) still finishing in the background.", flush=True)
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


def clean_ocr_text(text):
    """Trim OCR junk from a name's edges and close unbalanced parentheses.

    One-frame misreads produce things like "• Finding Mero", "Focus*",
    "Sound Therapy -" or "Silver Lining (Intro Mix" — trailing periods are
    kept (some titles really end in "Inc.").
    """
    text = text.strip(" \t'\"`•·|*®™-–—")
    if text.count("(") > text.count(")"):
        text += ")"
    return text


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
            x, y, w = (float(v) for v in coords.split())
        except ValueError:
            continue
        text = text.strip()
        # timers ("1:11"), waveform numbers, photo junk: no letters, no name
        if not any(c.isalpha() for c in text):
            continue
        if (region["x"][0] <= x <= region["x"][1]
                and region["y"][0] <= y <= region["y"][1]):
            rows.append((y, x, w, text))
    # group into visual lines (same height), left to right, top first —
    # joining only fragments that sit right next to each other
    rows.sort(key=lambda t: (-round(t[0], 2), t[1]))
    lines = []  # [y, x_start, x_end, text]
    for y, x, w, text in rows:
        if lines and abs(lines[-1][0] - y) < 0.025 and x - lines[-1][2] < 0.05:
            lines[-1][2] = max(lines[-1][2], x + w)
            lines[-1][3] += " " + text
        else:
            lines.append([y, x, x + w, text])
    if not lines:
        return None
    # the overlay block is left-aligned: artist and title share their left
    # edge — anything starting further right is background junk, not a line
    left = min(ln[1] for ln in lines)
    lines = [ln for ln in lines if ln[1] - left < 0.04]
    if len(lines) < 2:
        return None
    title, artist = clean_ocr_text(lines[1][3]), clean_ocr_text(lines[0][3])
    if not title or not artist:
        return None
    return title, artist


def cmd_watch(args):
    if sys.platform != "darwin":
        sys.exit(
            "watch mode reads the on-screen overlay with macOS's built-in OCR,\n"
            "so it only runs on a Mac — use the chat-based `log` mode instead."
        )
    radio = resolve_radio(args)
    _lock = acquire_single_instance(radio, "watch")  # noqa: F841 — held until exit
    signal.signal(signal.SIGTERM, _sigterm)
    ytdlp = find_ytdlp(args.ytdlp)
    ffmpeg = find_ffmpeg()
    ocr = ensure_ocr()
    casing = load_artist_casing(radio)
    book = SongBook(radio.songs_csv)
    warn_clock_skew(book, "watch")
    interval = float(radio.cfg["capture_interval_seconds"])
    region = radio.cfg["ocr_region"]
    frame = os.path.join(radio.folder, ".frame.jpg")
    print(f"Watching {radio.name}: {radio.url}", flush=True)
    print(f"One frame every {interval:.0f}s -> {radio.songs_csv}  (Ctrl+C to stop)", flush=True)
    print(
        "'.' = same song still playing, '+' = new name, awaiting a confirming read, "
        "'♪' = mp3 saved, '?' = overlay unreadable, 'x' = capture hiccup",
        flush=True,
    )

    manifest = None
    last = None
    pending = None  # unseen name waiting for a second identical read
    pending_dots = False
    downloads = []  # background mp3 downloads still running
    pl_pending = None  # playlist catch-up queue; None = recompute when possible

    def note(sym):
        nonlocal pending_dots
        print(sym, end="", flush=True)
        pending_dots = True

    def show(line):
        nonlocal pending_dots
        if pending_dots:
            print(flush=True)
            pending_dots = False
        print(line, flush=True)

    try:
        while True:
            t0 = time.monotonic()
            for song, ok in finished_downloads(downloads):
                if ok:
                    note("♪")
                else:
                    show(
                        f"mp3 download FAILED: {song['artist']} — {song['title']}"
                        "  (backfill later with: radio_tracklog.py download)"
                    )
            # playlist catch-up: work off songs still missing from the
            # playlist, a few per cycle, resuming the day after a quota block
            if playlist_enabled(radio) and not quota_blocked_today(radio):
                cache = read_playlist_cache(radio)
                if cache is not None:
                    if pl_pending is None:
                        pl_pending = playlist_pending(radio, book, cache)
                        if pl_pending:
                            show(f"playlist catch-up: {len(pl_pending)} song(s) to add")
                    if pl_pending:
                        token = google_access_token()
                        if not token:
                            pl_pending = []  # not authorized (yet) — leave it be
                        added = 0
                        while pl_pending and added < 5:
                            s, vid = pl_pending[0]
                            ok, reason = playlist_insert(token, playlist_id(radio), vid)
                            if ok:
                                pl_pending.pop(0)
                                append_playlist_cache(radio, vid, s["title"], s["artist"])
                                added += 1
                            elif reason == "quotaExceeded":
                                mark_quota(radio)
                                show(f"playlist: daily quota reached — "
                                     f"{len(pl_pending)} song(s) wait for tomorrow")
                                pl_pending = None  # recompute once the day passes
                                break
                            else:
                                show(f"playlist: {s['artist']} — {s['title']} "
                                     f"failed ({reason}) — skipped")
                                pl_pending.pop(0)
                        if added and not pl_pending:
                            show("playlist catch-up complete")
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
                    key = song_key(artist, title)
                    if key == last:
                        note(".")
                        pending = None
                    elif key not in book.songs and key != pending:
                        # a name never seen before: one-frame OCR misreads
                        # look exactly like this, so ask for a second opinion
                        pending = key
                        note("+")
                    else:
                        pending = None
                        last = key
                        line = record_spin(
                            book, ytdlp, now(), title, artist, radio, downloads,
                            live=True,
                        )
                        if line:
                            show(line)
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
        still = [i for i in downloads if i[0].poll() is None]
        if still:
            print(f"{len(still)} mp3 download(s) still finishing in the background.", flush=True)
    cmd_stats(args)


# ----------------------------------------------------------------- casing

def _artist_parts(name):
    """'A.M.R & Cornelius SA' -> ['A.M.R', 'Cornelius SA'] (split on SEP_RE)."""
    return [p.strip() for p in SEP_RE.split(name) if p and p.strip()]


def _find_cased(name, text):
    """How `name` is written inside `text` (case/accent-insensitive, whole words), or None."""
    if not name or not text:
        return None
    ft, fn = fold(text).lower(), fold(name).lower()
    if len(ft) != len(text):  # folding changed the length (ß -> ss): offsets unusable
        return None
    for m in re.finditer(re.escape(fn), ft):
        s, e = m.span()
        if (s == 0 or not ft[s - 1].isalnum()) and (e == len(ft) or not ft[e].isalnum()):
            return text[s:e]
    return None


def video_titles_path(radio):
    return os.path.join(radio.folder, ".video-titles.txt")


def load_video_titles(radio):
    """{video_id: (title, channel)} already known locally — from the playlist
    sync cache and from earlier `casing` runs — so yt-dlp only fetches the rest."""
    titles = {}
    for vid, title, channel in read_playlist_cache(radio) or []:
        if vid:
            titles[vid] = (title, channel)
    if os.path.exists(video_titles_path(radio)):
        with open(video_titles_path(radio), encoding="utf-8") as f:
            for line in f:
                parts = (line.rstrip("\n").split("\t") + ["", ""])[:3]
                if parts[0]:
                    titles[parts[0]] = (parts[1], parts[2])
    return titles


def fetch_video_titles(ytdlp, radio, vids):
    """Ask YouTube for title + channel of these video ids (one yt-dlp call per
    batch), remember them in .video-titles.txt, return {vid: (title, channel)}."""
    got = {}
    batch = 15
    for i in range(0, len(vids), batch):
        chunk = vids[i:i + batch]
        try:
            r = subprocess.run(
                [ytdlp, "--skip-download", "--ignore-errors", "--no-warnings",
                 "--print", "%(id)s\t%(channel)s\t%(title)s"]
                + [f"https://www.youtube.com/watch?v={v}" for v in chunk],
                capture_output=True, text=True, timeout=60 + 30 * len(chunk),
            )
            out = r.stdout
        except (subprocess.TimeoutExpired, OSError):
            out = ""
        with open(video_titles_path(radio), "a", encoding="utf-8") as f:
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) == 3 and parts[0] in chunk:
                    got[parts[0]] = (parts[2], parts[1])
                    f.write(f"{parts[0]}\t{parts[2]}\t{parts[1]}\n")
        print(f"  fetched {min(i + batch, len(vids))}/{len(vids)} video titles", flush=True)
    return got


def _recase(name, decided):
    """Rewrite each artist inside a credit line to its decided casing, keeping separators."""
    out, pos = [], 0
    for m in SEP_RE.finditer(name):
        chunk = name[pos:m.start()]
        out += [decided.get(fold(chunk.strip()).lower(), chunk), m.group(0)]
        pos = m.end()
    chunk = name[pos:]
    out.append(decided.get(fold(chunk.strip()).lower(), chunk))
    return "".join(out)


def cmd_casing(args):
    """Check every artist's casing against the YouTube videos linked in songs.csv.

    The uploader's own spelling — the artist's name as written in the video
    title, or in the "<Artist> - Topic" channel name — is taken as the truth.
    Names spelled differently from plain Title Case go into artist-casing.txt;
    songs.csv (and the mp3 file names) are rewritten to the verified casing.
    --check only reports.
    """
    radio = resolve_radio(args)
    book = load_book(radio)
    casing = load_artist_casing(radio)
    titles = load_video_titles(radio)
    missing = sorted({video_id(r["youtube"]) for r in book.songs.values()
                      if video_id(r["youtube"]) and video_id(r["youtube"]) not in titles})
    if missing:
        print(f"{len(missing)} video title(s) not cached yet — asking YouTube...", flush=True)
        titles.update(fetch_video_titles(find_ytdlp(args.ytdlp), radio, missing))

    # votes[artist key] = {casing as seen: count}
    votes, stored = {}, {}
    no_link, unread = [], []
    for r in book.songs.values():
        vid = video_id(r["youtube"])
        if not vid:
            no_link.append(r)
            continue
        if vid not in titles:
            unread.append(r)
            continue
        title, channel = titles[vid]
        # evidence, best first: the video title ("Artist - Title [Silk Music]"),
        # then the channel name — the artist's own channel or "<Artist> - Topic"
        for part in _artist_parts(r["artist"]):
            key = fold(part).lower()
            stored.setdefault(key, part)
            seen = _find_cased(part, title) or _find_cased(part, channel)
            if seen:
                votes.setdefault(key, {}).setdefault(seen, 0)
                votes[key][seen] += 1

    decided, unusual, conflicts = {}, [], []
    for key, seen in sorted(votes.items()):
        best = max(seen.items(), key=lambda kv: (kv[1], kv[0] == stored[key]))[0]
        decided[key] = best
        plain = normalize_name(best.upper(), {})  # what Title Case would make of it
        if best != plain or key in casing:
            unusual.append(key)
            if key in casing and casing[key] != best:
                conflicts.append((casing[key], best))
    # plain entries (not "Wrong -> Right" mappings) that no linked video backs up
    unverified = [v for k, v in casing.items() if k not in votes and fold(v).lower() == k]

    print(f"\n{len(votes)} artists checked against {len(titles)} YouTube titles:")
    for key in unusual:
        mark = "conflict" if any(c[1] == decided[key] for c in conflicts) else \
               ("ok" if key in casing else "NEW")
        print(f"  {mark:8} {decided[key]}   (seen {votes[key][decided[key]]}x"
              + ("" if len(votes[key]) == 1 else f", also {sorted(set(votes[key]) - {decided[key]})}")
              + ")")
    for old, new in conflicts:
        print(f"  artist-casing.txt says {old!r} but YouTube writes {new!r} — updating")
    if unverified:
        print(f"  no YouTube evidence for: {', '.join(sorted(unverified))} (kept as listed)")
    for r in no_link:
        print(f"  no YouTube link: {r['artist']} — {r['title']}  (run `enrich` first)")
    for r in unread:
        print(f"  video unreadable: {r['artist']} — {r['title']}  {r['youtube']}")

    rows_changed = [r for r in book.songs.values()
                    if _recase(r["artist"], decided) != r["artist"]]
    new_entries = [decided[k] for k in unusual if k not in casing]
    if args.check:
        print(f"\n--check: {len(new_entries)} new casing entr{'y' if len(new_entries) == 1 else 'ies'}, "
              f"{len(conflicts)} correction(s), {len(rows_changed)} songs.csv row(s) would change.")
        return

    if new_entries or conflicts:
        with open(radio.casing_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        fixed = {old: new for old, new in conflicts}
        lines = [fixed.get(ln.strip(), ln) for ln in lines]
        if new_entries:
            lines += ["# verified from the linked YouTube videos (radio_tracklog.py casing)"]
            lines += sorted(new_entries, key=str.lower)
        tmp = radio.casing_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, radio.casing_path)
        print(f"\nartist-casing.txt: {len(new_entries)} added, {len(conflicts)} corrected.")
    if rows_changed:
        for r in rows_changed:
            old_mp3 = mp3_path(radio, r)
            r["artist"] = _recase(r["artist"], decided)
            new_mp3 = mp3_path(radio, r)
            if os.path.exists(old_mp3) and old_mp3 != new_mp3 and (
                    not os.path.exists(new_mp3) or os.path.samefile(old_mp3, new_mp3)):
                os.rename(old_mp3, new_mp3)  # samefile: case-only change on macOS's FS
        book.dirty = True
        book.save()
        print(f"songs.csv: {len(rows_changed)} row(s) re-cased (mp3 files renamed to match).")
    if not (new_entries or conflicts or rows_changed):
        print("\nEverything already matches — nothing to change.")
    elif not args.check:
        print("Restart a running `watch`/`log` so it picks up the new casing.")


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
        url, year = lookup_song(ytdlp, r["artist"], r["title"], radio.prefer)
        if url:
            r["youtube"] = r["youtube"] or url
            if year:
                r["year"] = r["year"] or year
            book.save()
            print(f"  {query}  ->  {r['year'] or '?'}  {r['youtube']}", flush=True)
        else:
            print(f"  {query}  ->  not found", flush=True)
    print(f"\nDone. Updated {radio.songs_csv}")


def cmd_download(args):
    """Backfill missing mp3s. One radio when named; otherwise every radio
    that has download_mp3 enabled in its config.json."""
    os.makedirs(RADIOS_DIR, exist_ok=True)
    explicit = bool(args.radio)  # a named radio downloads even when the setting is off
    names = [args.radio] if explicit else sorted(
        d for d in os.listdir(RADIOS_DIR) if os.path.isdir(os.path.join(RADIOS_DIR, d))
    )
    if not names:
        sys.exit("No radios yet — run the watch/log command first.")
    ytdlp = find_ytdlp(args.ytdlp)
    find_ffmpeg()  # resolve (or fetch) it up front, once
    for name in names:
        args.radio = name
        radio = resolve_radio(args)
        if not explicit and not radio.cfg["download_mp3"]["enabled"]:
            print(f"{name}: download_mp3.enabled is false in config.json — skipping")
            continue
        if not os.path.exists(radio.songs_csv):
            print(f"{name}: no songs logged yet — skipping")
            continue
        book = SongBook(radio.songs_csv)
        apply_ignore = radio.cfg["download_mp3"].get("use_ignore_file")
        todo, ignored = [], 0
        for s in book.songs.values():
            if apply_ignore and is_ignored(radio, s):
                ignored += 1
            elif not os.path.exists(mp3_path(radio, s)):
                todo.append(s)
        done = len(book.songs) - len(todo) - ignored
        print(f"{name}: {done} mp3s present, {len(todo)} missing"
              + (f", {ignored} on the ignore list" if ignored else ""))
        for i, song in enumerate(sorted(todo, key=lambda s: s["first_added"]), 1):
            label = f"{song['artist']} — {song['title']}"
            if not song["youtube"]:  # never found on YouTube; try once more
                song["youtube"], song["year"] = (
                    v or "" for v in
                    lookup_song(ytdlp, song["artist"], song["title"], radio.prefer)
                )
                if song["youtube"]:
                    book.save()
                else:
                    print(f"  [{i}/{len(todo)}] {label}  ->  no YouTube link found, skipped", flush=True)
                    continue
            ok = download_mp3(radio, ytdlp, song, wait=True)
            print(f"  [{i}/{len(todo)}] {label}  ->  {'ok' if ok else 'FAILED'}", flush=True)
    print("Done.")


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "command", nargs="?", default="log",
        choices=["watch", "log", "list", "stats", "enrich", "download", "playlist", "casing"],
    )
    p.add_argument(
        "radio", nargs="?", default=None,
        help="radio folder name under radios/ (default: the only one there)",
    )
    p.add_argument("--url", default=None, help="override the radio's YouTube URL")
    p.add_argument("--ytdlp", default=None, help="path to yt-dlp (default: auto-detect)")
    p.add_argument("--check", action="store_true",
                   help="casing: only report, change nothing")
    args = p.parse_args()
    {
        "watch": cmd_watch, "log": cmd_log, "list": cmd_list,
        "stats": cmd_stats, "enrich": cmd_enrich, "download": cmd_download,
        "playlist": cmd_playlist, "casing": cmd_casing,
    }[args.command](args)


if __name__ == "__main__":
    main()
