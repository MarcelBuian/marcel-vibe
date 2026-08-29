#!/usr/bin/env python3
"""
Apply a hand-made order to a genre folder.

    python3 apply_order.py <GenreFolder>            # dry run: show the resulting order
    python3 apply_order.py <GenreFolder> --apply    # rename/move

<GenreFolder>/order.txt: one CURRENT 3-digit number per line, in the wanted order.
   "# text"  -> section header (kept in tracklist.txt)
   "drop NNN reason" -> file is moved to <GenreFolder>/_duplicates/ instead of numbered
   "NNN P"   -> mark as previously played: number gets a P suffix ("010P - ...") and source "_played-before"
Every mp3 under the folder must appear exactly once (ordered or dropped) - otherwise abort.
Result: all mp3s flattened into the genre root as "010 - ", "020 - ", ... (step 10),
tracklist.txt (number | bpm | source | file, with section headers) and <Genre>.m3u.
"""
import csv
import re
import shutil
import sys
from pathlib import Path

STEP = 10
PREFIX = re.compile(r"^(\d{2,3}) - ")


def main():
    root = Path(sys.argv[1])
    apply = "--apply" in sys.argv
    files = {}
    for p in root.rglob("*.mp3"):
        if p.parent.name == "_duplicates":
            continue
        m = PREFIX.match(p.name)
        if not m:
            sys.exit(f"no numeric prefix: {p}")
        if m.group(1) in files:
            sys.exit(f"duplicate current number {m.group(1)}: {p} / {files[m.group(1)]}")
        files[m.group(1)] = p
    meta = {}
    a = root / "analysis.csv"
    if a.exists():
        for r in csv.DictReader(a.open(encoding="utf-8")):
            m = PREFIX.match(Path(r["path"]).name)
            if m:
                bpm = float(r["bpm"] or 0)
                if 0 < bpm < 100:
                    bpm *= 2
                meta[m.group(1)] = (bpm, r["group"])
    plan, drops, seen, played_flag = [], [], set(), set()
    for raw in (root / "order.txt").read_text(encoding="utf-8").splitlines():
        l = raw.strip()
        if not l:
            continue
        if l.startswith("#"):
            plan.append(("header", l.lstrip("# ").strip()))
            continue
        if l.lower().startswith("drop"):
            num = l.split()[1]
            if num not in files:
                sys.exit(f"drop: unknown number {num}")
            if num in seen:
                sys.exit(f"number listed twice: {num}")
            seen.add(num)
            drops.append((num, " ".join(l.split()[2:])))
            continue
        toks = l.split()
        num = toks[0]
        if num not in files:
            sys.exit(f"unknown number {num}")
        if num in seen:
            sys.exit(f"number listed twice: {num}")
        seen.add(num)
        plan.append(("track", num))
        if len(toks) > 1 and toks[1].upper() == "P":
            played_flag.add(num)
    missing = sorted(set(files) - seen)
    if missing:
        sys.exit(f"not in order.txt: {missing}")
    n = 0
    out_lines, m3u = [], []
    for kind, val in plan:
        if kind == "header":
            out_lines.append(f"\n## {val}")
            print(f"\n## {val}")
            continue
        n += 1
        src = files[val]
        bare = PREFIX.sub("", src.name)
        dst = root / f"{n*STEP:03d} - {bare}"
        bpm, grp = meta.get(val, (0, "?"))
        if val in played_flag:
            grp = "_played-before"
        tag = "P" if grp == "_played-before" else ""
        dst = root / f"{n*STEP:03d}{tag} - {bare}"
        line = f"{n*STEP:03d}{tag} | {bpm:5.1f} bpm | {grp:<16} | {bare}"
        out_lines.append(line)
        print(line[:130])
        m3u.append(str(dst))
        if apply and src.resolve() != dst.resolve():
            tmp = root / f"__tmp_{n*STEP:03d}{tag} - {bare}"   # two-step to avoid clobbering an old name
            shutil.move(str(src), str(tmp))
            files[val] = tmp
            m3u[-1] = str(dst)
    if apply:
        for kind, val in plan:
            if kind == "track" and files[val].name.startswith("__tmp_"):
                final = root / files[val].name[len("__tmp_"):]
                shutil.move(str(files[val]), str(final))
        if drops:
            dd = root / "_duplicates"
            dd.mkdir(exist_ok=True)
            for num, why in drops:
                shutil.move(str(files[num]), str(dd / files[num].name))
                print(f"dropped -> _duplicates/: {files[num].name}  ({why})")
        (root / "tracklist.txt").write_text(
            f"# {root.name} - suggested mixing order (light -> aggressive). number | bpm | source | file\n"
            + "\n".join(out_lines).lstrip("\n") + "\n", encoding="utf-8")
        for old in root.rglob("*.m3u"):
            old.unlink()
        (root / f"{root.name}.m3u").write_text("\n".join(m3u) + "\n", encoding="utf-8")
        for d in sorted(root.iterdir()):
            if d.is_dir() and d.name != "_duplicates" and not any(p.suffix.lower() in (".mp3", ".m4a") for p in d.iterdir()):
                for junk in d.glob("archive.txt"):
                    junk.unlink()
                for junk in d.glob("analysis.csv"):
                    junk.unlink()
                if not any(d.iterdir()):
                    d.rmdir()
        print(f"\nAPPLIED {root.name}: {n} tracks numbered 010..{n*STEP:03d}, {len(drops)} dropped")
    else:
        print(f"\nDRY RUN {root.name}: {n} tracks, {len(drops)} drops - OK")


if __name__ == "__main__":
    main()
