"""Compare decks before/after the Markdown migration.

    uv run --with pillow --with beautifulsoup4 python tools/compare.py OLD_DIR NEW_DIR SHOTS_OLD SHOTS_NEW deck.html ...

Reports, per slide: text differences (whitespace-insensitive) and the share of
pixels that differ between the two screenshots.
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from deckparts import load, text  # noqa: E402
from PIL import Image, ImageChops  # noqa: E402


def norm(s):
    s = s.replace("\xa0", " ")
    return re.sub(r"\s+", "", s)


def main(old_dir, new_dir, shots_old, shots_new, *decks):
    bad = 0
    for d in decks:
        _, a, _ = load(str(pathlib.Path(old_dir) / d))
        _, b, _ = load(str(pathlib.Path(new_dir) / d))
        if len(a) != len(b):
            print(f"{d}: slide count {len(a)} -> {len(b)}")
            bad += 1
        for i, (x, y) in enumerate(zip(a, b), 1):
            tx, ty = norm(text(x)), norm(text(y))
            if tx != ty:
                bad += 1
                k = next((j for j in range(min(len(tx), len(ty))) if tx[j] != ty[j]), min(len(tx), len(ty)))
                print(f"{d} #{i}: TEXT differs at {k}: ...{tx[max(0,k-40):k+40]}...\n{' '*len(d)}       vs ...{ty[max(0,k-40):k+40]}...")
            po = pathlib.Path(shots_old) / f"{pathlib.Path(d).stem}-{i:02d}.png"
            pn = pathlib.Path(shots_new) / f"{pathlib.Path(d).stem}-{i:02d}.png"
            if po.exists() and pn.exists():
                im1, im2 = Image.open(po).convert("L"), Image.open(pn).convert("L")
                diff = ImageChops.difference(im1, im2).point(lambda v: 255 if v > 40 else 0)
                frac = sum(diff.histogram()[255:]) / (im1.width * im1.height)
                if frac > 0.01:
                    print(f"{d} #{i}: PIXELS {frac:.1%} differ")
    print("text/count problems:", bad)


if __name__ == "__main__":
    main(*sys.argv[1:])
