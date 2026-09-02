#!/usr/bin/env python3
"""Build a flat folder ("crate") of mp3 copies from a list of track names, matching files already in Deepium 2026.
    python3 make_crate.py "<Folder name>" <list.txt> [pool_dir ...]
"""
import re, shutil, sys, unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
def toks(s):
    s = unicodedata.normalize("NFKD", s); s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return set(re.sub(r"[^a-z0-9 ]", " ", s).split()) - {"the","a","mix","original","extended","feat","ft","x","and","mp3","official","audio"}
strip = re.compile(r"^\d{2,4}P? - ")
D = ROOT / sys.argv[1]; D.mkdir(exist_ok=True)
want = [l.strip() for l in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines() if l.strip()]
dirs = [ROOT / d for d in sys.argv[3:]] or [g for g in ROOT.iterdir() if g.is_dir() and g.name != "tools" and g != D]
pool = [p for g in dirs for p in g.rglob("*.mp3") if "_duplicates" not in p.parts]
pt = {p: toks(strip.sub("", p.stem)) for p in pool}
ok = 0
for w in want:
    q = toks(w)
    best = max(pool, key=lambda p: len(q & pt[p]) / len(q | pt[p]))
    sc = len(q & pt[best]) / len(q | pt[best])
    if sc < 0.45:
        print(f"!! NOT FOUND: {w}  (best {sc:.2f}: {best.name})"); continue
    dst = D / strip.sub("", best.name)
    if not dst.exists(): shutil.copy2(best, dst)
    ok += 1
    print(f"{sc:.2f} {w[:48]:<48} <- {best.parent.name}/{best.name[:55]}")
print(f"\n{ok}/{len(want)} -> {D.name}/ ({len(list(D.glob('*.mp3')))} files)")
