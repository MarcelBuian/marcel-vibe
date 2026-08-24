================================================================================
 YouTube Music  ->  local DJ library  (rekordbox-ready)
================================================================================

Everything now runs through ./dl.sh instead of copy-pasting a 20-line command
per playlist.

    ./dl.sh --list                    # show known playlists
    ./dl.sh DeepAndMelodicHouse       # one playlist
    ./dl.sh YTDeepT DrumAndBass       # several
    ./dl.sh --all                     # all 27

Env overrides:
    AUDIO_MODE=mp3 ./dl.sh YTDeepT        # transcode to mp3 instead of copying m4a
    MAX_ERRORS=10  ./dl.sh YTDeepT        # allow more failures before bailing
    COOKIES=cookies.txt ./dl.sh YTDeepT   # only for private / age-gated lists

Layout:  script + this readme live in ~/Music/MarcelVibe/yt-dlp (git),
         the yt-dlp binary and the music live in ~/Music/yt-dlp.
To add a playlist: add one "Folder|PLAYLIST_ID|note" line to the table in dl.sh.

The original hand-written commands are archived verbatim in readme.old.txt,
as a reference for the raw yt-dlp invocation behind dl.sh.


--------------------------------------------------------------------------------
 WHY m4a AND NOT mp3  (the quality question)
--------------------------------------------------------------------------------
YouTube hands out exactly these audio formats, with or without a logged-in
account (checked 2026-08-22):

    140  m4a   AAC   130k  44.1kHz   <-- what we take
    251  webm  opus  138k  48kHz
    139  m4a   AAC    49k
    249  webm  opus   52k

There is nothing above 140/251. No Premium tier appears. Your old log line
"Downloading 1 format(s): 251" proves the cookies were buying you nothing --
same ceiling as an anonymous request.

The old command took 251 (opus 138k) and RE-ENCODED it to mp3 V0. That is
lossy -> lossy: opus artifacts get baked in, then mp3 artifacts get layered on
top, and the file doubles to ~245kbps for audio that is strictly worse than
the 138k source. You cannot add information back by raising the bitrate.

The new command takes 140 and copies the stream untouched:

    [ExtractAudio] Not converting audio; file is already in target format m4a

One lossy generation instead of two, ~8MB instead of ~16MB, and no ffmpeg
transcode so it runs much faster. rekordbox plays AAC/m4a natively.

Verified on a real track: AAC 128k, cover art embedded as mjpeg, tags
title/artist/album/date all present.

Mixed .mp3 and .m4a in one folder is fine -- rekordbox does not care, and the
generated .m3u picks up both. If you ever need mp3 anyway, AUDIO_MODE=mp3.


--------------------------------------------------------------------------------
 403 FORBIDDEN  (what actually happened on 2026-08-22)
--------------------------------------------------------------------------------
Symptom: metadata extracted fine, thumbnail downloaded fine, then every single
track died with

    ERROR: unable to download video data: HTTP Error 403: Forbidden

alongside

    WARNING: The provided YouTube account cookies are no longer valid.

ROOT CAUSE: a stale yt-dlp binary. 2026.07.04 was ~7 weeks old and the player
clients it used had been blocked by YouTube. Updating to 2026.08.19 fixed it
immediately, with no cookies at all.

The cookie warning was a RED HERRING. Proof: the exact same 403 reproduced with
--cookies-from-browser removed entirely. Chasing the cookies would have wasted
an afternoon.

IT WAS NOT RATE LIMITING EITHER. Rate limiting returns 429, is intermittent,
and hits metadata extraction too. This was 100% failure on the media stream
only, while metadata and thumbnails kept working -- the signature of a rejected
stream URL, not of throttling. Adding a delay would only have made it fail
more slowly.

DIAGNOSTIC ORDER when 403s come back:
  1. ./yt-dlp -U            <-- fixes it ~90% of the time. dl.sh does this
                                automatically before every run.
  2. ./yt-dlp -F "<any track url>"      does format listing still work?
       - works, but downloads 403  -> stream URLs rejected, keep going
       - listing itself fails      -> network / IP-level problem
  3. Try a different player client:
       --extractor-args "youtube:player_client=web_embedded"
     (web_embedded was the only client still working on the old binary.
      ios/mweb asked for a PO token, web/web_safari lost format 140,
      tv said "the page needs to be reloaded".)
  4. Only then think about cookies.

The old binary is kept at ~/Music/yt-dlp/yt-dlp.bak-2026-07-04 in case an
update ever regresses. Safe to delete once the new one has proven itself.


--------------------------------------------------------------------------------
 COOKIES: OFF BY DEFAULT, ON PURPOSE
--------------------------------------------------------------------------------
--cookies-from-browser chrome reads cookies LIVE out of Chrome's database.
YouTube rotates session cookies as a security measure, so yt-dlp and Chrome
fight over the same session and invalidate each other. That is where the
"cookies are no longer valid" warning comes from.

Tested without cookies: same formats AND same metadata --
    artist=Simon Vuarambon | album=1996 / Quimera | year=2022
identical to the cookied run. So cookies cost reliability and buy nothing.

If you ever DO need them (private or age-gated playlist), do not read them from
a live browser. Freeze a set instead:
    1. open a private/incognito window
    2. log into YouTube
    3. go to https://www.youtube.com/robots.txt   (stops the player refreshing
       the session)
    4. export cookies with a cookies.txt extension
    5. close the private window immediately -- do NOT log out
    6. COOKIES=cookies.txt ./dl.sh <Folder>


--------------------------------------------------------------------------------
 WHAT CHANGED FROM THE OLD COMMANDS
--------------------------------------------------------------------------------
--skip-playlist-after-errors 5
      Native yt-dlp flag: skip the rest of the playlist after 5 failures
      instead of grinding through 200 more doomed items. 5 rather than 1
      because a single 403 can be one genuinely deleted or region-blocked
      track, and one dead video should not kill a 379-item run.

--retry-sleep http:exp=2:120
      Exponential backoff on HTTP errors, 2s doubling up to 120s. This is the
      "add a delay on 403" you asked for. It will not help against a stale
      binary, but it is the right response to genuine throttling.

--sleep-requests 1 / --sleep-interval 2 / --max-sleep-interval 6
      Randomised pacing so a 379-item run does not look like a scraper.
      Adds roughly 35-40 min across the biggest playlist. Worth it.

-U before every run
      The single highest-value change. See the 403 section above.

--convert-thumbnails jpg
      Cover art was being embedded as webp. Converting to jpg first means
      artwork actually shows up reliably in rekordbox.

--download-archive on EVERY playlist
      Previously only DeepAndMelodicHouse had it, so the DrumAndBass runs
      re-checked all 70 tracks from scratch every time. Now every folder gets
      <folder>/archive.txt and reruns are near-instant.

BUG: --parse-metadata was writing literal "NA" tags
      The three identity mappings (artist:artist, album:album,
      release_year:release_date) did nothing useful on tracks that HAVE music
      metadata -- verified byte-identical tags with and without them. But on a
      plain YouTube video with no music metadata they wrote the string "NA"
      into the artist and album tags, so those tracks showed up in rekordbox
      with Artist = "NA". Removed. --embed-metadata alone gets it right, and
      falls back to the channel name instead of "NA".

BUG: "NA - <title> - NA" filenames
      Same root cause, in the output template. Now:
          %(artist&{} - |)s%(title)s - %(release_year,upload_date>%Y)s
      - artist present -> "Simon Vuarambon - Quimera - 2022.m4a"  (unchanged)
      - artist missing -> "SWEET DISPOSITION ... - 2021.m4a"      (no NA prefix)
      - year always falls back to the upload year, so never NA.
      Existing files keep their names and are protected by archive.txt --
      nothing gets re-downloaded or renamed.

BUG: "&& find ... > playlist.m3u"
      With &&, a failed run meant the .m3u silently never regenerated and went
      stale. dl.sh always rebuilds it, whatever the exit code.

BUG: orphaned thumbnails
      When audio 403s after the thumbnail lands, the image is left behind with
      no audio file. dl.sh removes thumbs that have no matching .m4a/.mp3
      (and only those, so hand-added art survives).

.m3u files are now sorted
      find returns filesystem order, not alphabetical. Piped through sort now.

Dropped --playlist-start 1
      That is the default; it was noise.

Deduplicated
      There were three near-identical commands, two of them the same
      DrumAndBass playlist with slightly different flags. One code path now.


--------------------------------------------------------------------------------
 HOW --download-archive WORKS  (no seeding needed)
--------------------------------------------------------------------------------
- yt-dlp already skips songs whose audio file exists ("has already been
  downloaded") AND records their ID into archive.txt while doing so.
- So the FIRST run with --download-archive takes the usual time (it still
  checks each song's metadata, but downloads nothing you already have) and
  fills archive.txt by itself, with normal progress output in the console.
- Every run AFTER that is instant: songs in archive.txt are skipped before any
  metadata is fetched ("has already been recorded in the archive", ~0.2s each).
- Because of this, an aborted run costs nothing: rerun and it resumes exactly
  where it stopped.
