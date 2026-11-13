# Radio Tracklog — history and decisions

What this project is for, what was decided and why, what worked and what
didn't. It travels with the git repository so the reasoning is available
on any machine. Newest entries are at the bottom of each section.

How this file relates to the others:

- `README.md` — how to use the script.
- `radios/CONFIG.md` — what every `config.json` setting does.
- `CLAUDE.md` — technical rules and pitfalls for whoever edits the code.
- `WEBSITE_PLAN.md` — the plan for turning this into a website.
- `HISTORY.md` (this file) — intentions, decisions, experiments, results.

## Why this exists

Marcel is a DJ (the "Marcel Vibe" sets, Deepium 2026). He listens to 24/7
radio streams to find music he can play. The script logs every song a
radio plays, tells which ones repeat and when each was first heard, finds
each song on YouTube, downloads it as an mp3 and can add it to a YouTube
playlist. Songs he already played in a set go on an ignore list so they
are not fetched again.

Standing wishes from Marcel:

- **Real released music only.** A radio is added only after checking it
  plays real songs, not AI-generated filler (see "Radios considered").
- **Fix the code before the data.** When a bad row shows up in a
  `songs.csv`, fix what produced it first, then repair the file.
- **No manual setup.** Copy the folder to a new machine, run one
  command, and the script fetches what it needs.
- **Record decisions here**, so the history moves with the project
  (asked 2026-11-11).

## Timeline

- **2026-08-22** — First version: `log` (reads the stream's chat bot) and
  `watch` (reads the on-screen track name with the computer's built-in
  text reader). One folder per radio. yt-dlp and ffmpeg download
  themselves. First radio: Monstercat Silk.
- **2026-08-23** — mp3 downloads; names matched without accents.
- **2026-08-25** — YouTube playlist sync (Google authorization set up).
- **2026-08-26** — Ignore lists.
- **2026-08-28** — All times written in a fixed
  zone (`timezone`, Europe/Malta) after the Mac's zone change on
  2026-08-28 made an hour of songs disappear.
- **2026-08-29** — Windows support added (`ocr.ps1`). Whether it was
  then run on a real Windows machine is not recorded.
- **2026-09-05** — Radio Record stations added through their public
  tracklist service (`record-organic`, later `record-ibiza`). YouTube
  link matching rewritten after 14 of 316 songs got wrong videos. A
  `.venv` with yt-dlp added because the standalone yt-dlp took ~77 s to
  start on Marcel's Mac.
- **2026-09-15/16** — Shared `global_ignore.txt`. One `watch` command
  runs all enabled radios in one terminal and writes `watch.log`.
- **2026-10-06** — Candidate radios vetted for real music (see below).
- **2026-11-06** — Shazam prototype on Gentleman Radio (115 minutes).
- **2026-11-11** — Shazam built in as a third kind of radio
  (`source.type: shazam`), Gentleman Radio added, `radios/CONFIG.md`
  written, website planned.
- **2026-11-12** — First day of Gentleman Radio reviewed; every Shazam
  read now also records where in the track it matched.
- **2026-11-13** — The console prints the song name on every read
  instead of `.` and `+` marks.

## Decisions and their reasons

### Three ways to learn what a radio plays
- **On-screen text (`youtube`)** — for streams that show artist and
  title. Reads one video frame per minute. Catches every song.
- **Station tracklist (`radiorecord`)** — for Radio Record stations.
  Exact times and about 28 hours of history, so gaps fill themselves.
- **Shazam (`shazam`)** — only for streams that show nothing and have
  no chat (Gentleman Radio). Least reliable of the three; used because
  nothing else is possible there.
- The chat-bot `log` mode still exists but is sampled (only songs a
  viewer asks about), so `watch` is the main mode.

### Shazam: how it was decided (2026-11-06 and 2026-11-11)
- **A song counts only after 2 reads in a row agree** (`confirm_reads`).
  When Shazam doesn't know a track it names some other song, usually a
  different one each time. On 2026-11-11, about 25 of 60 reads were such
  one-off answers, and none got logged.
- **A looser rule was rejected.** Wrong answers do repeat with other
  reads in between ("Dantiez Saunderson - The Harp" twice during another
  track; "Makebo & Volen Sentir - Alchemist" twice, 14 minutes apart).
  "1 of the last 2 reads" or "2 of the last 3" would log them.
- **One read every 30 seconds, not 60.** On the same 30-minute log, a
  60-second rhythm would have confirmed 4–5 of the 7 songs that 30
  seconds confirmed. The stream changes tracks quickly; some songs are
  recognisable for only about a minute.
- **No throttling seen** at one read per 30 s (60 reads) or per 60 s
  (115 reads). Two bursts of 20 quick requests on 2026-11-06 were slowed
  to about 30 s each.
- **Cost of the strict rule:** real songs heard only once are missed
  (likely "The Return - New Day" on 2026-11-11). Every raw answer is
  kept in `radios/<name>/.shazam-reads.tsv` to review such cases.
- **Accuracy check against a radio that shows names** (Good Life Radio,
  2026-11-06, single reads): 13 of 20 right, 3 no match, 4 wrong.
- **Shazam's spelling is kept.** Names come from its catalogue, so the
  all-capitals fix used for on-screen text is not applied.
- **Tooling:** the `shazamio` package, installed by the script into
  `.venv` on first use. An older version crashed on Python 3.14; version
  0.9.0 with shazamio-core 2.0.0 works on 3.14 and 3.15 (tested
  2026-11-11 on the Mac). It publishes Windows builds; not yet run there.
- **Settings live in the radio's config** (`clip_seconds`,
  `confirm_reads`, `capture_interval_seconds`) so they can be tuned
  without touching code (Marcel's request).

### Shazam after the first day live (2026-11-12)
Marcel asked why the console shows so many `+` for gentleman.
- **Numbers, 2026-11-11 10:45 to 2026-11-12 13:05 (1,344 reads):** 537
  `.` (same song), 583 `+`, 85 `?` (no match), 8 `x`. 131 songs were
  confirmed; 130 are in `songs.csv`, 122 with a YouTube link.
- **What the `+` are:** 131 were the normal first read of a song that
  was confirmed on the next read. The other 452 were answers that did
  not repeat on the next read, so about a third of all reads are
  answers Shazam doesn't stand by 30 seconds later. Many `+` are
  therefore expected on this stream.
- **The two-in-a-row rule is not tight enough at 30 seconds.** Up to 19
  of the 131 confirmed songs were named for only 2–3 reads in the middle
  of another song. Some are real (two tracks mixed during a transition),
  but at least two are almost certainly wrong and were logged:
  "Jonny Calypso — Teenager 2K15" (named during "Gaston Lopez — Limits
  on the Mind", the same confusion as in the 2026-11-06 prototype) and
  "Kamasutra — Kamasutra Express (Train Version)" (inside an Erdi Irmak
  track). So wrong answers are not random: the same passage of music
  gives the same wrong name, and two reads 30 s apart can hit it twice.
- **Finding: Shazam also returns where in the track the clip matched**
  (`matches[].offset`, in seconds, plus `timeskew`/`frequencyskew`). In
  a probe with reads 20 s apart, a true match moved forward by exactly
  the elapsed time (261.5 → 281.5 → 301.5 s, skew about 0.0001), while
  a one-off wrong answer had a skew 50–500 times larger (−0.007 and
  0.05). Not yet used by the script.
- **Step 1 done the same day (Marcel: "go for it"):** every read in
  `.shazam-reads.tsv` now also records the match position (`offset`),
  the two skews, the number of candidates, how long Shazam took
  (`shazam_s`) and the exact stream time of the clip (`clip_start`).
  Nothing changed in what gets logged as a song. In a 2-minute test
  with reads 20 s apart, the position of a true match moved forward by
  20.00, 20.00 and 20.02 s. One lookup in that test took about 55 s
  while three watchers were asking Shazam from the same address — a
  sign that Shazam slows down above a few requests per minute.
- **Step 2, not done:** after about a day of data, check the rule
  "the position must move forward by the elapsed stream time" against
  the known wrong songs, then switch it on and remove the wrong songs.
  Raising `confirm_reads` to 3 is the blunt alternative: it would have
  dropped 76 of the 174 runs of repeated answers.
- **A wrong answer caught with the new data (test, 2026-11-12 13:18):**
  "Gasho & Maxi Raffone - Good News (Original)" was named twice in a
  row, which today's rule counts as a song. Its position jumped
  backwards from 405 s to 185 s while 30 s had passed, and its skews
  were about −0.02 and −0.01 (a true match: about 0.0001). The live
  watch heard "F. GALDi - Spiritual Awakening" at that moment.
- **The recording had not started by 2026-11-13 15:00:** the running
  `watch` was still the one started on 2026-11-12 11:56, before the
  change, so the live file holds no match positions yet. The day of
  data for step 2 starts at the next restart.

### The console says what plays on every read (2026-11-13)
Marcel: "Ideally is to show what song plays, not only the new ones, for
each radio in console."
- **Before:** a line only when a song started; in between, one mark per
  read (`.` same song, `+` heard but not confirmed, `?`, `x`, `♪`). On
  Gentleman Radio about a third of all reads were `+`, so the console
  often showed nothing about what was playing.
- **Now:** every read prints one line, so the newest line of a radio
  always names its song: `NEW song added` / `play #N` when a song
  counts, otherwise `still playing: …`, `unconfirmed (1 of 2 reads): …`,
  `Shazam has no match`, `track name not readable`, or the reason a
  capture failed. A finished download prints `mp3 saved: …`.
- **Nothing else changed:** which songs get counted, `songs.csv`,
  downloads. `unconfirmed` names are shown but not logged.
- **Cost:** `watch.log` grows about three times faster (an estimated
  0.5 MB a day with four radios; it was 0.18 MB on 2026-11-12).
- **Tested** on the three kinds of radio in a scratch folder, plus a
  scripted series of Shazam answers covering every kind of line.

### One page that explains all settings
`radios/CONFIG.md` (2026-11-11). Marcel preferred one shared page over
explanations repeated inside every `config.json`.

### The website (2026-11-11) — see `WEBSITE_PLAN.md`
- Marcel as admin plus a few invited friends; no sign-up page.
- Runs on his home Windows machine in Moldova (always on, static
  address, 300 GB free), reached by opening a port on the router.
- Only the admin configures radios. Friends subscribe to radios and see
  only their music; the admin sees everything.
- The ignore list is split: a system skip list (nobody gets the song)
  and a personal list per user, with a button on every song to add or
  remove it.
- The YouTube playlist sync stays for Marcel only at first.
- Python (Django recommended); a later move to Laravel/PHP is possible.
- The console output gets its own admin-only Log page.
- The script stays the engine; the website sits on top of its files.

## What didn't work

- **"First search result wins" for YouTube links** — gave news clips,
  tutorials and DJ sets as the song's link. Replaced by a matcher with
  regression tests (`tests_video_matches.py`).
- **The standalone yt-dlp on Marcel's Mac** — ~77 s to start each time.
  A `.venv` copy starts instantly.
- **Local wall-clock time** — a zone change dropped an hour of songs.
  Fixed with the `timezone` setting.
- **Shazam on the radios' own mp3 files** (2026-11-06) — identified only
  1 of 6 known songs, so Shazam is not used as proof that a radio plays
  real music.
- **Shazam single reads** — too many wrong answers (see above).
- **`python radio_tracklog.py`** on the Mac — stopped working around
  2026-11-05. The Mac only has `python3`; plain `python` had worked
  because VS Code quietly put the project's `.venv` on the path. Use
  `python3`.
- **Aegean Lounge and Bassport** — tried as on-screen-text radios;
  their music isn't on YouTube, so lookups returned unrelated videos.
  Their folders are no longer in `radios/`; the layout options made for
  them (`ocr_layout`) remain.

## Radios considered

Checked on 2026-10-06 unless noted. The check: open one of the channel's
uploaded mixes and see whether YouTube lists credited songs for it, and
look for a track name on screen.

- **In use:** Monstercat Silk (on-screen text), Radio Record "Organic"
  and "Innocence"/`ibiza` (tracklist service), Gentleman Radio (Shazam,
  since 2026-11-11).
- **Rejected — AI filler:** BossaLoFi Lounge ("LIVE 24/7 Café Del Mar
  Ibiza"), part of a network with Blue Escape Lounge and Ambient
  Nightscapes. No track names, no artist credits, hour-long "tracks"
  with generic names.
- **Real music with track names on screen, not added yet:** Seven Beats
  Music "Ibiza Chillout 24/7" and "Coffeeshop", The Good Life Radio x
  Sensual Musique, ChillYourMind.
- **Real music but no track names:** Maretimo Chill Radio, Café De
  Anatolia, LTB. Candidates for the Shazam source.
- **Gentleman Radio (checked 2026-11-06):** real music, mostly its own
  GNTLMN label plus known house. No track names and chat off, hence
  Shazam. Some tracks from the Gentleman (DJ) scene could not be found
  on YouTube during the Deepium 2026 preparation.
- **Idea not yet done:** Radio Record also has `deep`, `chillhouse` and
  `vip` stations, which need only a config file.

## Test results worth keeping

- **Gentleman, 2026-11-11, 30 minutes at one read per 30 s:** 60 reads,
  no errors, 7 songs logged, 6 with a YouTube link and mp3 ("Kevin Es —
  A House Thing" had no match). One logged song is doubtful and worth
  checking by ear: "Tony Romera, ASDEK & Karina Ramage — All I Know
  (Edit)" (two reads, 30 s apart).
- **Gentleman prototype, 2026-11-06, 115 minutes at one read per 60 s:**
  19 songs confirmed, 18 plausible, 1 doubtful.
- **Music on disk, 2026-11-11:** 31 GB of mp3, about 12.5 MB per song
  (record-ibiza 21 GB, record-organic 9.2 GB, monstercat-silk 0.8 GB,
  gentleman 0.2 GB).

## Open items

- Run the script on the Windows machine with all four radios (step 0 of
  the website plan).
- Build the website (not started).
