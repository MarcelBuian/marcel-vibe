#!/usr/bin/env bash
#
# YouTube Music playlist -> local DJ library (rekordbox-ready)
#
#   ./dl.sh DeepAndMelodicHouse          # one playlist
#   ./dl.sh YTDeepT DrumAndBass          # several
#   ./dl.sh --all                        # everything in the table below
#   ./dl.sh --list                       # show known playlists
#
# Env overrides:
#   AUDIO_MODE=mp3 ./dl.sh YTDeepT       # transcode to mp3 instead of copying m4a
#   MAX_ERRORS=10  ./dl.sh YTDeepT       # allow more failures before bailing
#   COOKIES=cookies.txt ./dl.sh YTDeepT  # only needed for private/age-gated lists
#
set -uo pipefail

WORK_DIR="${WORK_DIR:-$HOME/Music/yt-dlp}"
YTDLP="${YTDLP:-$WORK_DIR/yt-dlp}"
AUDIO_MODE="${AUDIO_MODE:-m4a}"   # m4a = stream copy, no re-encode (recommended) | mp3 = transcode
MAX_ERRORS="${MAX_ERRORS:-5}"     # consecutive-ish failures before skipping rest of playlist
COOKIES="${COOKIES:-}"            # empty = no cookies (see readme: this is the default on purpose)
EXTRA="${EXTRA:-}"                # extra yt-dlp flags, e.g. EXTRA="--playlist-items 1-5"

# ---------------------------------------------------------------------------
# folder|playlist-id|note
# The folder name is also the .m3u name.
# ---------------------------------------------------------------------------
playlists() {
  cat <<'EOF'
DeepAndMelodicHouse|PLoFzNYfE7BsiCqlFEJjndm53GIcXNAyDS|
YTDeepT|PLoFzNYfE7BsgCukLwCoeEt2JKxWwmfxRO|378
Car music|PLoFzNYfE7Bsi0a_sJhU6egfStZVQRCcaN|376
GreenMood|PLoFzNYfE7BsiCw455TDE81OV2nUZ3agQg|116
Lungi|PLoFzNYfE7BsjH86k4_H0R3a2Prct3BTL0|93
DeepHousePref|PLoFzNYfE7Bsj73Ob2op2iGeZGUqhWcbtj|82
TribaleDeep|PLoFzNYfE7BsgTWRflm7Wno57-heFmhG25|75
HappyDance|PLoFzNYfE7BshqKV1oE3KlOdlJ-oSoY9-i|72 rested
DrumAndBass|PLoFzNYfE7Bsh3jND-JMl9WqsxJrZBwd1T|70
2026Cabana|PLoFzNYfE7BshqLVhp21AyUj6B36E6MJav|68
MaltaBreak|PLoFzNYfE7BsjWdxWTsNzDjZrL-3N3jzY_|64
MinimalDeep|PLoFzNYfE7BsioCtL1rXGLh450nt66xHHd|47
KlavaMin|PLoFzNYfE7BsjQnfJddw4pj57k5bzsGpxi|45
JulyMalta|PLoFzNYfE7Bsg5TjuCbD0OIMfHBuA2Ek4n|40 rested
Trance emotions|PLoFzNYfE7Bsi7tfGNPnWlxwFGRBO7JjxS|39
Blue Tema|PLoFzNYfE7BsiJSYUlpu3pxLh8jOmqsyRq|39 rested
IonRev26|PLoFzNYfE7BsinyNb3XnIDSDBEmx5ZGmDv|39
deepMultiHouse|PLoFzNYfE7BsjWF9L3D_LCczQEJKN4T5DL|38
MayDeepOrg|PLoFzNYfE7BsgZJdHZzyooAhbaeRSixAR4|37 rested
newL|PLoFzNYfE7BsjmGnnC3clF85tKLjgb28D6|36
MolovGo|PLoFzNYfE7Bsg1UcZSL7RfA2M6jlncNWi7|35 rested
MaltaGo|PLoFzNYfE7Bsh_MJHp1vC9vrpKpEFdWeHR|34
DeeeepHouse|PLoFzNYfE7Bsj2U2hQF60v7JZ4_FfMVTSN|31
Sunset Surrender|PLoFzNYfE7BsjZh3j-2T58OLtzI2LCJxHc|28
Trance Deep|PLoFzNYfE7BshJndwBzZeZQNNeYiJZ97WC|26
BoatMaltaJuly25|PLoFzNYfE7BshKyh7seB-KD2DkSmBbm4et|17
BuduVeris|PLoFzNYfE7BsiAkkHH8xgLaAlzmTTSyWT_|14
EOF
}

die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[36m==> %s\033[0m\n' "$*"; }

id_for() {
  playlists | awk -F'|' -v k="$1" '$1==k {print $2; f=1} END{exit !f}'
}

download() {
  folder="$1"
  list_id="$(id_for "$folder")" || die "Unknown playlist: '$folder' (try ./dl.sh --list)"

  mkdir -p "$folder"
  info "$folder  (mode=$AUDIO_MODE, max-errors=$MAX_ERRORS)"

  # --- format: prefer a straight stream copy over a lossy->lossy transcode ---
  case "$AUDIO_MODE" in
    m4a) fmt=( -f "bestaudio[ext=m4a]/bestaudio/best" -x --audio-format m4a ) ;;
    mp3) fmt=( -f "bestaudio/best" -x --audio-format mp3 --audio-quality 0 ) ;;
    *)   die "AUDIO_MODE must be m4a or mp3 (got '$AUDIO_MODE')" ;;
  esac

  auth=()
  [ -n "$COOKIES" ] && auth=( --cookies "$COOKIES" )

  extra=()
  [ -n "$EXTRA" ] && extra=( $EXTRA )   # deliberately unquoted: splits into flags

  "$YTDLP" \
    --ignore-errors \
    --skip-playlist-after-errors "$MAX_ERRORS" \
    --sleep-requests 1 \
    --sleep-interval 2 \
    --max-sleep-interval 6 \
    --retry-sleep "http:exp=2:120" \
    --extractor-retries 3 \
    ${fmt[@]+"${fmt[@]}"} \
    ${auth[@]+"${auth[@]}"} \
    ${extra[@]+"${extra[@]}"} \
    --embed-thumbnail \
    --convert-thumbnails jpg \
    --embed-metadata \
    --output "$folder/%(artist&{} - |)s%(title)s - %(release_year,upload_date>%Y)s.%(ext)s" \
    --download-archive "$folder/archive.txt" \
    --no-overwrites \
    --no-mtime \
    "https://music.youtube.com/playlist?list=$list_id"
  rc=$?

  # Orphan artwork left behind when the audio download failed after the thumb landed.
  # Only removes a thumb that has no matching audio file, so hand-added art survives.
  find "$folder" -type f \( -name '*.webp' -o -name '*.jpg' \) -print0 2>/dev/null \
    | while IFS= read -r -d '' thumb; do
        base="${thumb%.*}"
        [ -f "$base.m4a" ] || [ -f "$base.mp3" ] || rm -f "$thumb"
      done

  # Rebuild the m3u even if the run bailed early — always reflects what is on disk.
  find "$folder" -type f \( -name '*.mp3' -o -name '*.m4a' \) | sort > "$folder.m3u"
  info "$folder: $(wc -l < "$folder.m3u" | tr -d ' ') tracks on disk (yt-dlp exit $rc)"

  [ "$rc" -ne 0 ] && printf '\033[33m    ^ non-zero exit — if you saw repeated 403s, see readme "403 Forbidden"\033[0m\n'
  return 0
}

cd "$WORK_DIR" || die "No work dir: $WORK_DIR"
[ -x "$YTDLP" ] || die "yt-dlp not found or not executable at $YTDLP"

case "${1:-}" in
  --list) playlists | awk -F'|' '{printf "  %-24s %s\n", $1, $3}'; exit 0 ;;
  --all)  info "Self-update"; "$YTDLP" -U
          playlists | awk -F'|' '{print $1}' | while IFS= read -r f; do download "$f"; done; exit 0 ;;
  "")     die "Usage: ./dl.sh <FolderName>... | --all | --list" ;;
esac

info "Self-update"; "$YTDLP" -U
for f in "$@"; do download "$f"; done
