#!/usr/bin/env python3
"""Regression cases for video_matches() — every entry was a real search result.
Run: python3 tests_video_matches.py   (0 = wrong video that MUST be rejected)"""
import radio_tracklog as r

CASES = [('Cafe de Anatolia', 'Karwan', 'Djmilmil, Sanyar Mostafaei - Karwan', 'Cafe De Anatolia LAB', 300, '>0'),
    ('Cafe de Anatolia', 'Lotus', 'Billy Esteban, Nora Projekt - Lotus (Cafe De Anatolia Songs)', 'Cafe De Anatolia SONGS', 300, '>0'),
    ('Nichols & Roark', 'Melodica', 'Melodica', 'Nichols+Roark - Topic', 300, '>0'),
    ('Mariner & Domingo', 'Another Life', 'Another Life', 'Mariner + Domingo - Topic', 300, '>0'),
    ('Husa & Zeyada', 'Trick of the Mind (Erdi Irmak Remix)', 'Trick of the Mind (Erdi Irmak Remix)', 'Husa & Zeyada - Topic', 300, '>0'),
    ('M.O.S & Leonid Sivelkin & Krasa Rosa', 'On The Strings Of Love', 'On The Strings Of Love (Extended Mix)', 'M.O.S. - Topic', 300, '>0'),
    ('Domingo', 'Pocket Vibes', 'Pocket Vibes', 'Domingo + - Topic', 300, '>0'),
    ('Drav', 'Say My Name', 'SAY MY NAME', 'Valium Ssky - Topic', 300, 0),
    ('M-sol Deep', 'Ocean and Whales', 'Ocean and Whales', 'Mira Evans - Topic', 300, 0),
    ('Marc Samuel', 'Zen Beach', 'Zen Beach', 'SHAMUËL - Topic', 300, 0),
    ('Oracle', 'Memory', 'Memory', 'Kendrick Scott Oracle - Topic', 300, 0),
    ('Oracle', 'Memory', 'Oracle - Memory', 'ORACLE - Topic', 250, '>0'),
    ('Proff', 'Light Between the Trees', 'Light Between the Trees (Extended Mix)', 'Release - Topic', 400, '>0'),
    ('Krasa Rosa', 'Cassiopeia', 'Cassiopeia', 'Krasa Rosa - Topic', 469, '>0'),
    ('Ventt & Keparys', 'Utro', 'Utro (Reshaped Extended Mix)', 'Ventt - Topic', 400, '>0'),
    ('rshand', 'Chrome', 'Chrome', 'rshand', 200, '>0'),
    ('Approaching Black', 'Sensitive', 'Approaching Black - Sensitive (Official Audio)', 'Approaching Black', 300, '>0'),
    ('Marsh', 'Belle', "Marsh 'Belle' Official Audio", 'Anjunadeep', 330, '>0'),
    ('Blue Haze', 'Amber Glow (Blood Groove & Kikis Remix)', 'Blue Haze - Amber Glow (Blood Groove & Kikis Remix) [Silk Music]', 'Monstercat Silk', 300, '>0'),
    ('Aurum (Ar)', 'Coming Back', 'Aurum Victims Are Being Targeted Again Right Now', 'Sean Matteson', 570, 0),
    ('Hoj', 'Feel That', 'The Merrymen - Feeling Hot Hot Hot', 'MerrymenofBarbados', 200, 0),
    ('Oracle', 'Memory', 'Oracle Memory Architecture Explained: SGA vs PGA for DBAs | Day 3', 'DBA with Hillary', 216, 0),
    ('Dangelo Witker', "Lest's Flow", "Dangelo Witker - Lest's Flow | 1 hour organic house mix", 'Some Channel', 3600, 0),
    ('Hermanez', 'Alavanca', 'Hermanez - Alavanca [Organic House 2022 / All Day I Dream 2022]', 'HMWL', 400, '>0'),
    ('Underher & Kyla Millette', 'Unbreakable (Madota Remix)', 'UNDERHER feat. Kyla Millette - Unbreakable (Madotta Remix)', 'UNDERHER', 400, '>0'),
    ('Lost Desert & Hermanez', 'Jinx (Volen Sentir Remix)', 'Lost Desert, Hermanez - Jinx (Volen Sentir Remix)', 'Lost Desert', 420, '>0'),
    ('Marsh', 'Belle', 'Marsh - Belle Piano Tutorial (How to play)', 'PianoGuy', 330, 0),
    ('Distic', 'Totem Bird', 'How To Unlock “THE TOTEM” Character, In CROSSY ROAD!', 'Photics TV', 164, 0),
    ('Drav', 'Say My Name', 'Florence + The Machine - Spectrum', 'FlorenceMachineVEVO', 300, 0),
    ('Marian', 'Life and Death', 'City of Life and Death Ceremony Scene', "Johnny's War Stories", 300, 0)]

IGNORE_CASES = [  # (ignore.txt line, logged artist, logged title, must match)
    ("00:00:00 Marc Samuel (CH) - Zen Beach", "Marc Samuel", "Zen Beach", True),
    ("07:30 Legroni, Peredel, Ilana Lorraine - Feel Me", "Legroni & Peredel", "Feel Me (Extended Mix)", True),
    ("Zen Beach", "Anyone", "Zen Beach", True),
    ("[R] 33:10 Dido - Thank You (Deep Dish Vocal)", "Dido", "White Flag", False),
]


def _ignore_matches(line, artist, title):
    import os, tempfile
    radio = r.Radio("_t")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(line + "\n")
    radio.ignore_path = f.name
    radio.ignore = r.load_ignore(radio)
    os.remove(f.name)
    return r.is_ignored(radio, {"artist": artist, "title": title, "youtube": ""})


if __name__ == "__main__":
    ibad = [c for c in IGNORE_CASES if _ignore_matches(*c[:3]) != c[3]]
    for b in ibad:
        print("BAD ignore", b)
    bad = [(a, t, ch, vt, r.video_matches(a, t, vt, ch, d))
           for a, t, vt, ch, d, want in CASES if (r.video_matches(a, t, vt, ch, d) == 0) != (want == 0)]
    for b in bad:
        print("BAD", b)
    print(f"{len(CASES) - len(bad)}/{len(CASES)} video cases, "
          f"{len(IGNORE_CASES) - len(ibad)}/{len(IGNORE_CASES)} ignore cases pass")
    raise SystemExit(1 if bad or ibad else 0)
