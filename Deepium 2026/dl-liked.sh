#!/usr/bin/env bash
#
# Download only the tracks you LIKED from the suggestion lists into the genre folder.
#
#   ./dl-liked.sh TechHouse              # one genre folder
#   ./dl-liked.sh TechHouse Minimal      # several
#   ./dl-liked.sh --all                  # TechHouse Minimal DeepHouse MelodicHouse DrumAndBass
#
# HOW TO MARK A LIKE: in <Folder>/suggestions*.txt put a "+" at the start of the line, e.g.
#   + Chris Stussy - Here for the summer - 2026 - https://music.youtube.com/watch?v=XXXX
# (same in <Folder>/_played-before/*.txt, or paste any youtube link, one per line, into <Folder>/liked.txt).
# Lines without "+" are skipped.
# Already-downloaded videos are remembered in <Folder>/archive.txt, so re-running is cheap.
#
# Output: <Folder>/Artist - Title - Year.mp3  (same naming as MelodicHouse), cover art + tags embedded.
#         Tracks from <Folder>/_played-before/*.txt land in <Folder>/_played-before/ (kept separate on purpose).
# Env: ALL=1 downloads EVERY line with a link (not just "+" lines) - e.g.  ALL=1 ./dl-liked.sh TechHouse
#      AUDIO_MODE=m4a (stream copy, smaller/faster) instead of the default mp3.
#
set -uo pipefail
cd "$(dirname "$0")"

YTDLP="${YTDLP:-../radio-tracklog/yt-dlp}"
FFMPEG_DIR="${FFMPEG_DIR:-../radio-tracklog}"   # ffmpeg binary lives next to yt-dlp; needed for mp3 + cover art
AUDIO_MODE="${AUDIO_MODE:-mp3}"
JS_RUNTIME="${JS_RUNTIME:-node}"     # yt-dlp needs a JS runtime for YouTube now; node is installed

die()  { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[36m==> %s\033[0m\n' "$*"; }

[ -x "$YTDLP" ] || die "yt-dlp not found at $YTDLP (set YTDLP=/path/to/yt-dlp)"
[ -x "$FFMPEG_DIR/ffmpeg" ] || die "ffmpeg not found in $FFMPEG_DIR (set FFMPEG_DIR)"

case "$AUDIO_MODE" in
  mp3) fmt=( -f "bestaudio/best" -x --audio-format mp3 --audio-quality 0 ) ;;
  m4a) fmt=( -f "bestaudio[ext=m4a]/bestaudio/best" -x --audio-format m4a ) ;;
  *)   die "AUDIO_MODE must be mp3 or m4a" ;;
esac

collect_urls() {   # $1 = folder, $2 = "new" | "played" -> unique video URLs ("+" lines, or every line with ALL=1)
  if [ "$2" = "played" ]; then src=$(cat "$1"/_played-before/*.txt 2>/dev/null)
  else src=$(cat "$1"/suggestions*.txt "$1"/liked.txt 2>/dev/null); fi
  if [ "${ALL:-0}" = "1" ]; then printf '%s\n' "$src" | grep -vE '^\s*#'
  else printf '%s\n' "$src" | grep -E '^\s*\+|^https://'; fi \
    | grep -oE 'https://(music\.|www\.)?youtube\.com/watch\?v=[A-Za-z0-9_-]{11}' \
    | sed -E 's#https://(music\.|www\.)?youtube\.com/watch\?v=#https://www.youtube.com/watch?v=#' \
    | sort -u
}

download_batch() {   # $1 = destination dir, $2 = newline-separated URLs
  dest="$1"; urls="$2"
  n=$(printf '%s\n' "$urls" | grep -c . || true)
  if [ "$n" -eq 0 ]; then info "$dest: nothing to download"; return 0; fi
  mkdir -p "$dest"
  info "$dest: $n track(s) (mode=$AUDIO_MODE)"
  printf '%s\n' "$urls" | "$YTDLP" \
    --js-runtimes "$JS_RUNTIME" \
    --ffmpeg-location "$FFMPEG_DIR" \
    --ignore-errors \
    --sleep-requests 1 --sleep-interval 1 --max-sleep-interval 4 \
    --retry-sleep "http:exp=2:60" --extractor-retries 3 \
    "${fmt[@]}" \
    --embed-thumbnail --convert-thumbnails jpg --embed-metadata \
    --output "$dest/%(artist&{} - |)s%(title)s - %(release_date>%Y,upload_date>%Y)s.%(ext)s" \
    --download-archive "$dest/archive.txt" \
    --no-overwrites --no-mtime \
    --batch-file -
  rc=$?
  # orphan artwork cleanup (thumb landed, audio failed)
  find "$dest" -maxdepth 1 -type f \( -name '*.webp' -o -name '*.jpg' \) -print0 2>/dev/null \
    | while IFS= read -r -d '' thumb; do
        base="${thumb%.*}"; [ -f "$base.mp3" ] || [ -f "$base.m4a" ] || rm -f "$thumb"
      done
  find "$dest" -maxdepth 1 -type f \( -name '*.mp3' -o -name '*.m4a' \) | sort > "$dest/$(basename "$dest").m3u"
  info "$dest: $(wc -l < "$dest/$(basename "$dest").m3u" | tr -d ' ') tracks on disk (yt-dlp exit $rc)"
}

download_folder() {   # new suggestions -> <Folder>/ ; already-played placeholders -> <Folder>/_played-before/
  folder="$1"
  [ -d "$folder" ] || die "No folder: $folder"
  download_batch "$folder" "$(collect_urls "$folder" new)"
  download_batch "$folder/_played-before" "$(collect_urls "$folder" played)"
}

case "${1:-}" in
  --all) set -- TechHouse Minimal DeepHouse MelodicHouse DrumAndBass ;;
  "")    die "Usage: ./dl-liked.sh <Folder>... | --all" ;;
esac
info "Self-update yt-dlp"; "$YTDLP" -U >/dev/null 2>&1 || true
for f in "$@"; do download_folder "$f"; done
