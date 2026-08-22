cd ~/Music/yt-dlp/ && \
TARGET_FOLDER="DeepAndMelodicHouse" && \
mkdir -p "$TARGET_FOLDER" && \
./yt-dlp \
--ignore-errors \
--extract-audio \
--audio-format mp3 \
--audio-quality 0 \
-f "ba/b" \
--embed-thumbnail \
--embed-metadata \
--parse-metadata "%(artist)s:%(artist)s" \
--parse-metadata "%(album)s:%(album)s" \
--parse-metadata "%(release_year)s:%(release_date)s" \
--output "$TARGET_FOLDER/%(artist)s - %(title)s - %(release_year)s.%(ext)s" \
--download-archive "$TARGET_FOLDER/archive.txt" \
--no-overwrites \
--no-mtime \
--playlist-start 1 \
--cookies-from-browser chrome \
"https://music.youtube.com/playlist?list=PLoFzNYfE7BsiCqlFEJjndm53GIcXNAyDS" && \
find "$TARGET_FOLDER/" -name "*.mp3" > "$TARGET_FOLDER.m3u"


### How --download-archive works (no seeding needed):
### - yt-dlp already skips songs whose .mp3 exists ("has already been
###   downloaded") AND records their ID into archive.txt while doing so.
### - So the FIRST run with --download-archive takes the usual time
###   (it still checks each song's metadata, but downloads nothing you
###   already have) and fills archive.txt by itself, with normal progress
###   output in the console.
### - Every run AFTER that is instant: songs in archive.txt are skipped
###   before any metadata is fetched ("has already been recorded in the
###   archive", ~0.2s per song).
### Same recipe for the other playlist folders: add the
### --download-archive "$TARGET_FOLDER/archive.txt" line to their commands.



cd ~/Music/yt-dlp/ && \
TARGET_FOLDER="DrumAndBass" && \
./yt-dlp \
--extract-audio \
--audio-format mp3 \
--audio-quality 0 \
--embed-thumbnail \
--embed-metadata \
--parse-metadata "%(artist)s:%(artist)s" \
--parse-metadata "%(album)s:%(album)s" \
--parse-metadata "%(release_year)s:%(release_date)s" \
--output "$TARGET_FOLDER/%(artist)s - %(title)s - %(release_year)s.%(ext)s" \
--no-overwrites \
--no-mtime \
--playlist-start 1 \
--cookies-from-browser chrome \
"https://music.youtube.com/playlist?list=PLoFzNYfE7Bsh3jND-JMl9WqsxJrZBwd1T" && \
find "$TARGET_FOLDER/" -name "*.mp3" > "$TARGET_FOLDER.m3u"



cd ~/Music/yt-dlp/ && \
TARGET_FOLDER="DrumAndBass" && \
./yt-dlp -U && \
./yt-dlp \
--extract-audio \
--audio-format mp3 \
--audio-quality 0 \
--embed-thumbnail \
--embed-metadata \
--parse-metadata "%(artist)s:%(artist)s" \
--parse-metadata "%(album)s:%(album)s" \
--parse-metadata "%(release_year)s:%(release_date)s" \
--output "$TARGET_FOLDER/%(artist)s - %(title)s - %(release_year)s.%(ext)s" \
--no-overwrites \
--no-mtime \
--playlist-start 1 \
"https://music.youtube.com/playlist?list=PLoFzNYfE7Bsh3jND-JMl9WqsxJrZBwd1T" && \
find "$TARGET_FOLDER/" -name "*.mp3" > "$TARGET_FOLDER.m3u"



MaltaGo - 34 - https://music.youtube.com/playlist?list=PLoFzNYfE7Bsh_MJHp1vC9vrpKpEFdWeHR
newL - 36 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsjmGnnC3clF85tKLjgb28D6
MayDeepOrg - 37 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsgZJdHZzyooAhbaeRSixAR4 - rested
DeepHousePref - 82 - https://music.youtube.com/playlist?list=PLoFzNYfE7Bsj73Ob2op2iGeZGUqhWcbtj
DeeeepHouse - 31 - https://music.youtube.com/playlist?list=PLoFzNYfE7Bsj2U2hQF60v7JZ4_FfMVTSN
Car music - 376 - https://music.youtube.com/playlist?list=PLoFzNYfE7Bsi0a_sJhU6egfStZVQRCcaN
MolovGo - 35 - https://music.youtube.com/playlist?list=PLoFzNYfE7Bsg1UcZSL7RfA2M6jlncNWi7 - rested
Trance Deep - 26 - https://music.youtube.com/playlist?list=PLoFzNYfE7BshJndwBzZeZQNNeYiJZ97WC
Trance emotions - 39 - https://music.youtube.com/playlist?list=PLoFzNYfE7Bsi7tfGNPnWlxwFGRBO7JjxS
Blue Tema - 39 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsiJSYUlpu3pxLh8jOmqsyRq - rested
JulyMalta - 40 - https://music.youtube.com/playlist?list=PLoFzNYfE7Bsg5TjuCbD0OIMfHBuA2Ek4n - rested
Sunset Surrender - 28 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsjZh3j-2T58OLtzI2LCJxHc
HappyDance - 72 - https://music.youtube.com/playlist?list=PLoFzNYfE7BshqKV1oE3KlOdlJ-oSoY9-i - rested
MaltaBreak - 64 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsjWdxWTsNzDjZrL-3N3jzY_
BoatMaltaJuly25 - 17 - https://music.youtube.com/playlist?list=PLoFzNYfE7BshKyh7seB-KD2DkSmBbm4et
YTDeepT - 378 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsgCukLwCoeEt2JKxWwmfxRO
TribaleDeep - 75 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsgTWRflm7Wno57-heFmhG25
BuduVeris - 14 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsiAkkHH8xgLaAlzmTTSyWT_
Lungi - 93 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsjH86k4_H0R3a2Prct3BTL0
MinimalDeep - 47 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsioCtL1rXGLh450nt66xHHd
GreenMood - 116 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsiCw455TDE81OV2nUZ3agQg
KlavaMin - 45 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsjQnfJddw4pj57k5bzsGpxi
2026Cabana - 68 - https://music.youtube.com/playlist?list=PLoFzNYfE7BshqLVhp21AyUj6B36E6MJav
IonRev26 - 39 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsinyNb3XnIDSDBEmx5ZGmDv
deepMultiHouse - 38 - https://music.youtube.com/playlist?list=PLoFzNYfE7BsjWF9L3D_LCczQEJKN4T5DL
DrumAndBass - 70 - https://music.youtube.com/playlist?list=PLoFzNYfE7Bsh3jND-JMl9WqsxJrZBwd1T