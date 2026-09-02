#!/usr/bin/env python3
"""Fill MarcelVibe/NN gaps (geo-blocked or unresolved tracks) from mp3s already present in the genre folders."""
import json, re, shutil, unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "MarcelVibe"; WORK = OUT / "_work"
def toks(s):
    s = unicodedata.normalize("NFKD", s); s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return set(re.sub(r"[^a-z0-9 ]", " ", s).split()) - {"the","a","mix","original","extended","feat","ft","x","and"}
pool = [p for g in ROOT.iterdir() if g.is_dir() and g.name not in ("MarcelVibe", "tools") for p in g.rglob("*.mp3") if "_duplicates" not in p.parts]
strip = re.compile(r"^\d+P? - ")
pool_t = [(p, toks(strip.sub("", p.stem))) for p in pool]
sessions = json.loads((WORK / "sessions.json").read_text(encoding="utf-8"))
copied = 0
for s in sessions:
    d = OUT / f"{s['num']:02d}"
    if not d.exists(): continue
    have = [toks(strip.sub("", p.stem)) for p in d.glob("*.mp3")]
    for t in s["tracks"]:
        q = toks(t["artist"] + " " + t["title"]); qt = toks(t["title"])
        if not qt: continue
        if any(len(qt & h) / len(qt) >= 0.8 and len(q & h) / len(q) >= 0.6 for h in have):
            continue   # already there
        best, sc = None, 0
        for p, pt in pool_t:
            s1 = len(qt & pt) / len(qt); s2 = len(q & pt) / len(q)
            if s1 >= 0.8 and s2 > sc: best, sc = p, s2
        if best and sc >= 0.6:
            shutil.copy2(best, d / strip.sub("", best.name)); copied += 1
            have.append(toks(strip.sub("", best.stem)))
            print(f"{d.name}: {t['artist']} - {t['title']}  <-  {best.parent.name}/{best.name}")
print("copied:", copied)
