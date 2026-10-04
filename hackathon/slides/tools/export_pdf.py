"""Export decks to pdf/<deck>.pdf (one 1600x900 page per slide).

Run:  uv run --with playwright python tools/export_pdf.py [deck.html ...]
"""

import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent

decks = sys.argv[1:] or sorted(p.name for p in ROOT.glob("[0-9]*.html"))
(ROOT / "pdf").mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    for name in decks:
        page.goto((ROOT / name).as_uri())
        page.wait_for_load_state("load")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(500)
        out = ROOT / "pdf" / (pathlib.Path(name).stem + ".pdf")
        page.pdf(path=str(out), width="1600px", height="900px", print_background=True,
                 prefer_css_page_size=True)
        print(out)
    browser.close()
