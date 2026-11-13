# Radio Tracklog website — plan

Status: **plan only, nothing built yet** (written 2026-11-11; all open
questions answered the same day — see the last section).

## Decisions already made (Marcel, 2026-11-11)

- **Users:** Marcel (admin) and a few invited friends. No sign-up page;
  accounts are created by invitation only.
- **Where it runs:** Marcel's home Windows machine in Moldova, always on.
- **Who configures what:** only the admin adds radios and edits their
  settings. Other users choose which radios they subscribe to and have
  personal preferences that never change the admin's settings.
- **Who sees what:** the admin sees everything (all radios, all songs,
  logs, users). Other users see only their music.
- **Technology:** Python. A later move to Laravel/PHP stays possible.
- **Log page:** what the console prints today gets its own page, admin only.
- **Outside access:** a port opened on the home router (the machine has
  a static address).
- **Ignore lists:** split into a system skip list and a personal list
  per user, with a button on every song to add or remove it.
- **YouTube playlist sync:** stays for Marcel only for now.
- **The machine:** latest Windows, on 24/7, 300 GB free.

## Shape of the system

Three parts on the Windows machine:

1. **The engine** — today's `radio_tracklog.py`, kept as it is. It keeps
   watching the radios and writing `radios/<name>/songs.csv`,
   `config.json`, the mp3 files and `watch.log`. The command line keeps
   working exactly as now.
2. **The website** — a separate Python program that reads those files
   and shows them, and writes `config.json` / ignore lists when the admin
   edits them. It owns a small database (one SQLite file) for what the
   engine doesn't know about: users, invitations, subscriptions and
   personal ignore lists.
3. **The way in from outside** — a secure connection from the internet
   to the home machine (see "Reaching it from outside").

Why this split: the engine is tested and running. The website sits on
top of its files, so a website bug can't stop the logging, and each part
can be restarted alone.

Recommended building blocks:

- **Django** for the website. It ships with the parts that matter most
  for a site reachable from the internet: accounts, password storage,
  login sessions, and form protection. It is also the Python framework
  closest to Laravel, which keeps a later move simple.
- **SQLite** as the database (one file, no server to install).
- Pages rendered on the server, with small live-updating parts (status,
  log) refreshed every couple of seconds.

## Small engine changes the website needs

1. **Pick up config changes by itself.** Today a radio reads its
   settings only when it starts. The all-radios `watch` will re-check
   the configs regularly, restart a radio whose settings changed, start
   a newly enabled one and stop a disabled one. Then "save" on the
   website is all the admin has to do.
2. **A status file per radio** (what's playing, time of the last read,
   whether the last read failed), so the website can show live status
   without parsing the log.
3. **Split the ignore list in two** — see the next section.

## Ignore lists with several users

Today one ignore list does two jobs: "I already played this in a set"
and "never download this". With friends on the site those must be
separate, or Marcel's already-played songs would be missing for everyone.

- **System skip list (admin):** songs nobody should get (junk, wrong
  matches). Not downloaded at all. This is today's `global_ignore.txt`.
- **Personal ignore list (every user, admin included):** songs hidden
  from *my* list and left out of *my* "download all". The file is still
  downloaded once for the others. Marcel's current per-radio
  `ignore.txt` entries move into his personal list.

Consequence: the engine downloads every song that has a YouTube match
unless it is on the system skip list. That uses more disk (see Risks).

## Pages

### For every user
- **My radios** — the radios the admin offers, with subscribe /
  unsubscribe.
- **My music** — one searchable, sortable table of the songs from my
  radios: artist, title, year, radio, first heard, play count, YouTube
  link. Per song: play in the browser, download, and an **ignore
  button** that adds the song to my ignore list or takes it off again
  with one click. Ignored songs are hidden by default; a switch shows
  them (greyed out) so they can be restored. On top: **download all**, **download new since my last
  download**, and **download selected** (as one zip).
- **My ignore list** — view, add, remove, paste a tracklist.
- **Account** — change password.

### Admin only
- **Dashboard** — every radio: running or stopped, playing now, last
  read, songs today, restart button.
- **Radios** — add a radio, edit its settings in a form (each field with
  its explanation from `radios/CONFIG.md`), switch it on or off.
- **All songs** — like "My music" but everything, plus: fix a wrong
  YouTube link, re-download, delete a song.
- **System skip list** — view and edit.
- **Log** — live console output, all radios or one, with history,
  search, highlighted new songs and errors, and a legend for the marks.
- **Shazam review** — raw Shazam answers per radio, with "likely missed"
  songs (named twice but not back to back) and a one-click add.
- **Users** — create an invitation link, see who joined, disable a user,
  see each user's subscriptions.
- **System** — disk space used by music, tool versions, backups.

## Login and safety

- No sign-up page. The admin creates a one-time invitation link that
  expires; the friend opens it and sets a password.
- Passwords stored hashed (Django default). Repeated wrong logins are
  slowed down.
- Every page checks who is asking: admin pages refuse other users, and a
  user can only reach songs from radios they subscribe to.
- Downloads are addressed by song number, never by a file path typed by
  the visitor.
- The site is only reachable over HTTPS.
- A nightly copy of the database and the `songs.csv` files.

## Reaching it from outside

Decided: **open a port on the home router.** The machine has a static
address, so no address-tracking service is needed.

- Only the HTTPS port (443) is forwarded to the machine, plus port 80 if
  the certificate renewal needs it. Nothing else is opened.
- **HTTPS needs a certificate.** The usual way is a name (a domain or
  sub-domain) pointing at the static address, with a free certificate
  renewed automatically. A small web server in front of the site
  (Caddy) does this by itself on Windows. Still to settle: which name
  to use.
- Because the home address is visible, the site must hold up on its
  own: login attempts are slowed and then blocked per address, there is
  no page without login except the login and invitation pages, the
  Windows firewall allows only those ports, and the site runs under a
  Windows account without admin rights.
- Big downloads go straight from the machine at the home upload speed,
  with nobody in the middle.

Not chosen: Cloudflare Tunnel (needs a domain, unclear terms for large
music downloads) and Tailscale (every friend would install an app).

## Running on Windows

- The engine already supports Windows (text reading through Windows'
  own reader, its own ffmpeg and yt-dlp builds). The Shazam package has
  Windows builds too. **None of this has been run on a real Windows
  machine from here**, so the first step is a test run there of all
  three kinds of radio.
- The machine must not go to sleep. Engine and website start by
  themselves when Windows starts, and restart if they stop.
- Updates: the code lives in the git repository; an update on the
  Windows machine is "pull the new version, restart".
- A home connection in Moldova is an advantage: YouTube tends to block
  rented servers, not home connections.

## Build order

0. **Windows check.** Run today's script on the Windows machine with
   all four radios. Confirm text reading, Shazam and downloads work
   there. Check free disk space and upload speed. Choose how the site is
   reached from outside.
1. **Engine changes.** Config pick-up, status file, ignore split.
2. **Site, admin only.** Login, dashboard, all songs with downloads,
   radio settings form, skip list, log page.
3. **Friends.** Invitations, subscriptions, My music, personal ignore,
   the three zip downloads.
4. **Go live.** Outside access with HTTPS, auto-start, backups, move
   the data from the Mac, stop the watchers on the Mac.
5. **Extras.** Shazam review, add-radio helper (draw the text region on
   a frame), DJ tags ("liked", "played in set" → personal ignore),
   alerts when a radio stops, daily digest, statistics.

Each step ends with something usable; steps 2–3 can be built and tried
on the Mac before anything moves to Windows.

## Risks and open points

- **Disk space.** Today: 31 GB of mp3 (record-ibiza 21 GB, record-organic
  9.2 GB, monstercat-silk 0.8 GB, gentleman 0.2 GB), about 12.5 MB per
  song. The Windows machine has 300 GB free, room for roughly 24,000
  songs. After the ignore split, songs Marcel currently skips get
  downloaded too (record-organic alone has ~600 songs without an mp3).
  The System page shows disk use and warns before it runs low.
- **Big zips.** "Download all" for one Radio Record station is 10–20 GB.
  The zip is built while it is sent (no temporary copy), but it depends
  on the home upload speed and on the outside-access choice.
- **Windows is untested from here.** Step 0 exists for this.
- **Copyright.** The site hands out music taken from YouTube. Keeping it
  invite-only and behind login is the reason sign-up stays off.
- **Home address exposed.** A consequence of the open port; covered by
  the measures under "Reaching it from outside".

## Answers from Marcel (2026-11-11)

1. Outside access: open a port on the router.
2. Ignore split: agreed, plus a button on each song to add or remove it
   from the ignore list.
3. The machine: latest Windows, on 24/7, 300 GB free, reached by its
   own static address.
4. YouTube playlist: Marcel only for now.

Still to settle when building starts: the name (domain or sub-domain)
for the HTTPS certificate.
