"""Rebuild a deck: new talk slides, then the deck's bonus slides, then an appendix
holding the listed original slides verbatim (marked .appendix).

    python tools/rebuild.py DECK TALK.html --appendix 2-42 [--keep-bonus]
Indices are 1-based positions in the deck *before* the rebuild.
"""

import argparse
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from deckparts import SEC, appendix_header, classes, load, save, to_appendix  # noqa: E402


def ranges(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


ap = argparse.ArgumentParser()
ap.add_argument("deck")
ap.add_argument("talk")
ap.add_argument("--appendix", default="")
ap.add_argument("--lede", default=None)
args = ap.parse_args()

prefix, slides, suffix = load(args.deck)
talk = [m.group(0) for m in SEC.finditer(open(args.talk).read())]
bonus = [s for s in slides if "bonus" in classes(s)]
moved = [to_appendix(slides[i - 1]) for i in ranges(args.appendix)] if args.appendix else []
moved = [s for s in moved if "bonus" not in classes(s)]
out = talk + bonus
if moved:
    out += [appendix_header(args.lede) if args.lede else appendix_header()] + moved
save(args.deck, prefix, out, suffix)
print(f"{args.deck}: {len(talk)} talk + {len(bonus)} bonus + {len(moved)} appendix")
