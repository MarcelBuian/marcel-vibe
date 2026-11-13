"""Identify the song in one audio clip with Shazam.

Helper for radio_tracklog.py: `watch` runs it for radios whose config.json
says "source": {"type": "shazam"}. It needs the shazamio package, which
radio_tracklog.py installs into the project's .venv on first use (see
ensure_shazam there) — run it with that Python, not the system one.

usage: .venv/bin/python shazam_read.py <clip.wav>

Prints one JSON line, or {} when Shazam has no match:
  {"artist": "...", "title": "...",
   "offset": 261.48,          seconds into the track where the clip starts
   "timeskew": 0.00003,       how much the clip's tempo deviates from the track
   "frequencyskew": -0.001,   how much its pitch deviates
   "matches": 1}              how many candidate matches Shazam had
The last four describe HOW it matched (taken from the first candidate) and
may be null. On a true match the offset moves forward with the music from
one read to the next and both skews are near zero.
Exits with code 1 (reason on stderr) when the lookup itself failed —
network, throttling, an unreadable clip.
"""
import asyncio
import json
import sys

from shazamio import Shazam


async def recognize(path):
    async with Shazam() as shazam:  # closes its HTTP session on the way out
        reply = await shazam.recognize(path)
    track = reply.get("track") or {}
    artist, title = (track.get("subtitle") or "").strip(), (track.get("title") or "").strip()
    if not (artist and title):
        return {}
    matches = [m for m in (reply.get("matches") or []) if isinstance(m, dict)]
    best = matches[0] if matches else {}
    return {"artist": artist, "title": title, "offset": best.get("offset"),
            "timeskew": best.get("timeskew"), "frequencyskew": best.get("frequencyskew"),
            "matches": len(matches)}


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: shazam_read.py <clip.wav>")
    try:
        result = asyncio.run(recognize(sys.argv[1]))
    except Exception as e:  # noqa: BLE001 — any failure is just "this read failed"
        print(f"{type(e).__name__}: {e}"[:300], file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result), flush=True)  # ASCII-escaped: safe on any console encoding


if __name__ == "__main__":
    main()
