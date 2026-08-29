#!/usr/bin/env python3
"""
Audio analysis for ordering a genre folder from light to aggressive.

    .venv/bin/python analyze_energy.py <GenreFolder> [bpm_lo bpm_hi]

Writes <GenreFolder>/analysis.csv with one row per mp3 (root + subfolders):
path, group, duration_s, bpm, rms_db, rms_p90_db, centroid_hz, onset, low_ratio
Three 30 s windows (at 25 %, 50 %, 75 % of the track) are analysed, so intros/outros
don't dominate. BPM is folded into [bpm_lo, bpm_hi] (house 118-134, D&B 160-180).
"""
import csv
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
SR = 22050
WIN = 30.0


def fold_bpm(b, lo, hi):
    if not b or b <= 0:
        return 0.0
    while b < lo:
        b *= 2
    while b > hi:
        b /= 2
    return round(float(b), 1)


def analyse(args):
    path, lo, hi = args
    import librosa  # imported in the worker
    try:
        dur = librosa.get_duration(path=path)
        rms_all, cent_all, onset_all, low_all, tempos = [], [], [], [], []
        for frac in (0.25, 0.5, 0.75):
            off = max(0.0, min(dur * frac - WIN / 2, max(dur - WIN, 0)))
            y, sr = librosa.load(path, sr=SR, mono=True, offset=off, duration=WIN)
            if len(y) < sr * 5:
                continue
            rms = librosa.feature.rms(y=y)[0]
            rms_all.append(rms)
            cent_all.append(librosa.feature.spectral_centroid(y=y, sr=sr)[0].mean())
            oenv = librosa.onset.onset_strength(y=y, sr=sr)
            onset_all.append(float(oenv.mean()))
            oenv_fine = librosa.onset.onset_strength(y=y, sr=sr, hop_length=128)
            S = np.abs(librosa.stft(y, n_fft=2048)) ** 2
            freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
            low_all.append(float(S[freqs < 150].sum() / (S.sum() + 1e-9)))
            # unbiased BPM: autocorrelation tempogram averaged over time, peak inside [lo, hi]
            tg = librosa.feature.tempogram(onset_envelope=oenv_fine, sr=sr, hop_length=128, win_length=1536)
            ac = tg.mean(axis=1)
            lags = np.arange(len(ac))
            bpms = np.full(len(ac), np.inf); bpms[1:] = 60.0 * sr / (128 * lags[1:])
            idx = np.where((bpms >= lo) & (bpms <= hi))[0]
            if len(idx):
                k = idx[np.argmax(ac[idx])]
                if 1 <= k < len(ac) - 1:   # parabolic interpolation of the peak lag
                    a, b, c = ac[k - 1], ac[k], ac[k + 1]
                    d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
                    lag = k + d
                else:
                    lag = float(k)
                tempos.append(60.0 * sr / (128 * lag))
        if not rms_all:
            raise RuntimeError("too short")
        rms = np.concatenate(rms_all)
        bpm = fold_bpm(float(np.median(tempos)), lo, hi) if tempos else 0.0
        return dict(path=str(path), duration_s=round(dur, 1), bpm=bpm,
                    rms_db=round(float(20 * np.log10(rms.mean() + 1e-9)), 2),
                    rms_p90_db=round(float(20 * np.log10(np.percentile(rms, 90) + 1e-9)), 2),
                    centroid_hz=round(float(np.mean(cent_all)), 0),
                    onset=round(float(np.mean(onset_all)), 3),
                    low_ratio=round(float(np.mean(low_all)), 4))
    except Exception as e:  # keep going, mark the row
        return dict(path=str(path), duration_s=0, bpm=0, rms_db=0, rms_p90_db=0,
                    centroid_hz=0, onset=0, low_ratio=0, error=str(e)[:80])


def main():
    root = Path(sys.argv[1])
    lo, hi = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (118.0, 134.0)
    files = sorted(p for p in root.rglob("*.mp3"))
    print(f"{root.name}: analysing {len(files)} files", flush=True)
    rows = []
    with ProcessPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(analyse, [(str(p), lo, hi) for p in files]), 1):
            p = Path(r["path"])
            r["group"] = p.parent.name if p.parent != root else "new"
            rows.append(r)
            if i % 10 == 0:
                print(f"  {i}/{len(files)}", flush=True)
    fields = ["path", "group", "duration_s", "bpm", "rms_db", "rms_p90_db", "centroid_hz", "onset", "low_ratio", "error"]
    with (root / "analysis.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            r.setdefault("error", "")
            w.writerow(r)
    bad = [r for r in rows if r["error"]]
    print(f"{root.name}: done, {len(rows)} rows, {len(bad)} errors -> {root/'analysis.csv'}", flush=True)
    for r in bad:
        print("   ERR", Path(r["path"]).name, r["error"])


if __name__ == "__main__":
    main()
