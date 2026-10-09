"""Split a deck into slides and reassemble it (used to move slides into appendices).

    from deckparts import load, save
    prefix, slides, suffix = load("04-agent-template.html")
    save("04-agent-template.html", prefix, new_slides, suffix)
"""

import html
import re

SEC = re.compile(r'<section class="slide[^"]*"[^>]*>.*?</section>', re.S)


def load(path):
    s = open(path).read()
    slides = [m.group(0) for m in SEC.finditer(s)]
    first = s.index(slides[0])
    last = s.rindex(slides[-1]) + len(slides[-1])
    return s[:first], slides, s[last:]


def save(path, prefix, slides, suffix):
    open(path, "w").write(prefix + "\n\n".join(slides) + suffix)


def classes(slide):
    return re.match(r'<section class="([^"]*)"', slide).group(1).split()


def to_appendix(slide):
    """Mark a slide as appendix (keeps content verbatim; drops a 'bonus' marker)."""
    cls = [c for c in classes(slide) if c != "bonus"]
    if "appendix" not in cls:
        cls.append("appendix")
    return re.sub(r'<section class="[^"]*"', f'<section class="{" ".join(cls)}"', slide, count=1)


def title(slide):
    m = re.search(r"<h[12][^>]*>(.*?)</h[12]>", slide, re.S)
    return html.unescape(re.sub("<[^>]+>", "", m.group(1))).strip() if m else "?"


def text(slide):
    s = re.sub(r'<aside class="notes">.*?</aside>', "", slide, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def appendix_header(lede="Reference material behind the talk. Skipped in the session; use it when you need the details."):
    return f'''<section class="slide section appendix">
  <div class="num">A</div>
  <h2>Appendix: reference</h2>
  <p class="lede">{lede}</p>
</section>'''
