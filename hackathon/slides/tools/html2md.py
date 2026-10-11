# This file is part of Prometheus
# https://inl.gov/super-intelligence/prometheus/
#
# Copyright 2026 Battelle Energy Alliance, LLC
# All rights reserved, see NOTICE.txt for full restrictions
# https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
#
# Licensed under the MIT License, please see LICENSE for details
# https://github.com/idaholab/prometheus_core/blob/main/LICENSE
#
# SPDX-License-Identifier: MIT

"""One-time converter: an existing deck NN-name.html -> slides/NN-name.md.

    uv run --with beautifulsoup4 --with pyyaml python tools/html2md.py 05-dry-run.html [...]

Known patterns become Markdown (see slides/README.md); anything else is kept as a
raw HTML block, and listed in the report printed at the end, so nothing is lost.
"""

from __future__ import annotations

import html
import pathlib
import re
import sys

import yaml
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT: list[str] = []


# ---------------------------------------------------------------------------
# inline
# ---------------------------------------------------------------------------
def esc_text(t: str) -> str:
    t = t.replace("\\", "\\\\").replace("*", "\\*").replace("`", "\\`")
    t = t.replace("[", "\\[").replace("]", "\\]")
    t = re.sub(r"(?<![\w\\])_(?=\w)", r"\\_", t)  # leading underscore of a word
    t = t.replace("\xa0", "&nbsp;")
    t = t.replace("<", "&lt;").replace(">", "&gt;")
    return t


def code_span(s: str) -> str:
    fence = "``" if "`" in s else "`"
    pad = " " if s.startswith("`") or s.endswith("`") else ""
    return f"{fence}{pad}{s}{pad}{fence}"


def inline(node, table=False) -> str:
    out = []
    for c in node.children:
        if isinstance(c, NavigableString):
            if type(c).__name__ == "Comment":
                continue
            t = esc_text(str(c))
            if table:
                t = t.replace("|", "\\|")
            out.append(t)
            continue
        name = c.name
        attrs = {k: v for k, v in c.attrs.items() if not (name == "code" and k == "style")}
        if name == "code" and not attrs and not c.find(True):
            s = c.get_text()
            if table:
                s = s.replace("|", "\\|")
            out.append(code_span(s))
        elif name in ("b", "strong") and not attrs:
            inner = inline(c, table).strip()
            out.append(f"**{inner}**" if inner else "")
        elif name in ("i", "em") and not attrs:
            inner = inline(c, table).strip()
            out.append(f"*{inner}*" if inner else "")
        elif name == "a" and set(attrs) == {"href"}:
            out.append(f"[{inline(c, table)}]({attrs['href']})")
        elif name == "br":
            out.append("<br>")
        else:
            out.append(str(c).replace("\n", " "))
    s = "".join(out)
    return re.sub(r"[ \t\r\n]+", " ", s)


# ---------------------------------------------------------------------------
# blocks
# ---------------------------------------------------------------------------
def raw(el: Tag, why: str) -> list[str]:
    REPORT.append(why)
    s = str(el).strip("\n")
    lines = [l if l.strip() else "<!---->" for l in s.split("\n")]
    return ["\n".join(lines)]


def classes(el) -> list[str]:
    return list(el.get("class", []))


def kids(el) -> list[Tag]:
    out = []
    for c in el.children:
        if isinstance(c, Tag):
            out.append(c)
        elif str(c).strip() and type(c).__name__ != "Comment":
            out.append(c)  # stray text: caller decides
    return out


def attrline(cls: list[str], extra: dict | None = None) -> str:
    parts = [f".{c}" for c in cls]
    for k, v in (extra or {}).items():
        parts.append(f'{k}="{v}"')
    return "{" + " ".join(parts) + "}" if parts else ""


def guess_lang(text: str) -> str:
    t = text.strip()
    if re.search(r"^## \w", t, re.M):
        return "markdown"
    if t.startswith("{") or t.startswith("["):
        return "json"
    if re.search(r"^\s*(from|import|class|async def|def|await|if __name__)\b", t, re.M) or "self." in t:
        return "python"
    if re.search(r"^(FROM|RUN|ENV|COPY|ARG|CMD) ", t, re.M):
        return "docker"
    if re.search(r"^\s*[\w.-]+:\s*(\S.*)?$", t, re.M) and not re.search(r"^\s*(git|cd|make|curl|docker|uv|gh|export|python3?)\b", t, re.M):
        return "yaml"
    if re.search(r"^\s*(git|cd|make|curl|docker|uv|gh|export|python3?|echo|cp|mkdir|ls|set|source)\b", t, re.M):
        return "bash"
    return "text"


def pre_block(el: Tag) -> list[str]:
    cls = [c for c in classes(el)]
    style = el.get("style")
    lines = []
    hl = []
    text_lines = el.decode_contents().split("\n")
    for n, l in enumerate(text_lines, 1):
        if 'class="h"' in l:
            hl.append(n)
    text = el.get_text()
    lang = guess_lang(text)
    info_attrs = [f".{c}" for c in cls]
    if hl:
        spans, start, prev = [], hl[0], hl[0]
        for x in hl[1:] + [None]:
            if x is not None and x == prev + 1:
                prev = x
                continue
            spans.append(f"{start}-{prev}" if prev != start else f"{start}")
            if x is not None:
                start = prev = x
        info_attrs.append(f"hl={','.join(spans)}")
    if style:
        info_attrs.append(f'style="{style}"')
    info = lang + (" {" + " ".join(info_attrs) + "}" if info_attrs else "")
    fence = "````" if "```" in text else "```"
    lines.append(f"{fence}{info}\n{text.rstrip(chr(10))}\n{fence}")
    return lines


def list_block(el: Tag) -> list[str] | None:
    cls = [c for c in classes(el) if c != "b"]
    items = [c for c in el.children if isinstance(c, Tag)]
    if any(i.name != "li" for i in items):
        return None
    lines = []
    start = int(el.get("start", 1))
    for n, li in enumerate(items, start):
        if li.find(["ul", "ol", "pre", "table", "div", "p"]) or li.attrs:
            return None
        bullet = f"{n}." if el.name == "ol" else "-"
        lines.append(f"{bullet} {inline(li).strip()}")
    head = attrline(cls)
    return [(head + "\n" if head else "") + "\n".join(lines)]


def table_block(el: Tag) -> list[str] | None:
    rows = el.find_all("tr")
    if not rows or el.find(["table", "ul", "ol", "pre", "div"], recursive=True) and el.find("table") is not el:
        return None
    if el.find(["ul", "ol", "pre", "div", "p"]):
        return None
    head = rows[0]
    if head.find("td") or not head.find("th"):
        return None
    ncol = len(head.find_all(["th", "td"]))
    widths = []
    for th in head.find_all("th"):
        m = re.search(r"width:\s*([\d.]+px)", th.get("style", ""))
        widths.append(m.group(1) if m else "")
        if th.get("style") and not m:
            return None
    out = ["| " + " | ".join(inline(c, True).strip() or " " for c in head.find_all(["th", "td"])) + " |",
           "|" + "---|" * ncol]
    for tr in rows[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) != ncol or any(c.attrs for c in cells):
            return None
        vals = [inline(c, True).strip() or " " for c in cells]
        hl = " {.hl}" if "hl" in classes(tr) else ""
        if tr.attrs and set(classes(tr)) - {"hl"}:
            return None
        out.append("| " + " | ".join(vals) + hl + " |")
    cls = [c for c in classes(el) if c != "t"]
    extra = {"widths": "|".join(widths)} if any(widths) else None
    a = attrline(cls, extra)
    return [(a + "\n" if a else "") + "\n".join(out)]


def colons(depth: int) -> str:
    return ":" * (3 + depth)


def col_part(c: Tag) -> list[str]:
    """Content of a grid child. A .col holding a single table/pre stays an explicit
    ::: col (the builder would otherwise leave a lone table/pre unwrapped)."""
    if "col" in classes(c) and not c.get("style") and not set(classes(c)) - {"col"}:
        elems = [x for x in c.children if isinstance(x, Tag)]
        if len(elems) == 1 and elems[0].name in ("pre", "table"):
            return container("col", "", blocks_of(c))
        return blocks_of(c)
    return block(c)


def depth_of(blocks: list[str]) -> int:
    d = -1
    for b in blocks:
        for m in re.finditer(r"^(:{3,})\s*\w", b, re.M):
            d = max(d, len(m.group(1)) - 3)
    return d + 1


def container(name: str, args: str, inner: list[str]) -> list[str]:
    c = colons(depth_of(inner))
    head = f"{c} {name}" + (f" {args}" if args else "")
    return [head + "\n" + "\n\n".join(inner) + "\n" + c]


def box_item(box: Tag) -> str | None:
    style = box.get("style", "")
    m = re.fullmatch(r"\s*flex:\s*([\d.]+);?\s*", style) if style else None
    if style and not m:
        return None
    color = " ".join(c for c in classes(box) if c != "box")
    flex = f" flex={m.group(1)}" if m else ""
    pieces = []
    title_seen = False
    for c in box.children:
        if isinstance(c, NavigableString):
            if str(c).strip():
                pieces.append("=" + esc_text(str(c).strip()))
            continue
        if c.name == "b" and not title_seen:
            pieces.insert(0, f"**{inline(c).strip()}**")
            title_seen = True
        elif c.name == "span" and classes(c) == ["small"]:
            pieces.append(inline(c).strip())
        elif c.name == "span" and classes(c) == ["mono"]:
            pieces.append("~" + inline(c).strip())
        elif c.name == "span" and not c.attrs:
            pieces.append("=" + inline(c).strip())
        else:
            return None
    if not title_seen:
        pieces.insert(0, "")
    pieces = [x.replace("|", "\\|") for x in pieces]
    return f"- [{color}{flex}] " + " | ".join(pieces)


def flow_block(el: Tag) -> list[str] | None:
    style = el.get("style", "")
    gm = re.search(r"gap:\s*([\d.]+px|0)", style)
    if re.sub(r"(align-items:\s*stretch|gap:\s*[\d.]+px|gap:\s*0|;|\s)", "", style):
        return None
    items = []
    for c in el.children:
        if isinstance(c, NavigableString):
            if str(c).strip():
                return None
            continue
        if "box" in classes(c):
            b = box_item(c)
            if b is None:
                return None
            items.append(b)
        elif "arrow-h" in classes(c):
            m = re.fullmatch(r"\s*width:\s*(\d+)px;?\s*", c.get("style", "")) if c.get("style") else None
            if c.get("style") and not m:
                return None
            sp = c.find("span")
            label = inline(sp).strip() if sp else ""
            arrow = "<-" if "left" in classes(c) else "->"
            w = f" {{w={m.group(1)}}}" if m else ""
            items.append(f"- {arrow} {label}{w}".rstrip() if not w else f"- {arrow} {label}{w}")
        else:
            return None
    gap = f" gap={gm.group(1)}" if gm and gm.group(1) not in ("0",) else ""
    return container("flow", gap.strip(), ["\n".join(items)])


def split_heading_block(el: Tag, level: str) -> list[str]:
    """Card/step/takeaway inner: headings become markdown headings."""
    out = []
    for c in kids(el):
        out += block(c)
    return out


def block(el) -> list[str]:
    if isinstance(el, NavigableString):
        return [esc_text(str(el).strip())]
    name, cls = el.name, classes(el)
    style = el.get("style")

    if name == "p":
        if style:
            return raw(el, "p with style")
        a = attrline(cls)
        return [(a + "\n" if a else "") + inline(el).strip()]
    if name in ("h3", "h4", "h5"):
        if style:
            return raw(el, f"{name} with style")
        a = attrline(cls)
        hashes = "#" * int(name[1])
        return [f"{hashes} {inline(el).strip()}" + (f" {a}" if a else "")]
    if name in ("ul", "ol") and not style:
        r = list_block(el)
        return r if r is not None else raw(el, "complex list")
    if name == "pre":
        return pre_block(el)
    if name == "table" and not style:
        r = table_block(el)
        return r if r is not None else raw(el, "complex table")
    if name != "div":
        return raw(el, f"<{name}>")

    if "callout" in cls and not style:
        inner = blocks_of(el, inline_ok=True)
        return container("callout", " ".join(c for c in cls if c != "callout"), inner)
    if "card" in cls and not style:
        tag = el.find("span", class_="tag", recursive=False)
        args = " ".join(c for c in cls if c != "card")
        if tag:
            args += f' tag="{tag.get_text().strip()}"'
            tag.extract()
        inner = blocks_of(el, inline_ok=True)
        return container("card", args.strip(), inner)
    if "grid" in cls:
        n = next((c[1:] for c in cls if re.fullmatch(r"g\d+", c)), None)
        extra = [c for c in cls if c != "grid" and not re.fullmatch(r"g\d+", c)]
        tmpl = None
        gap = None
        if style:
            rest = style
            m = re.search(r"grid-template-columns:\s*([^;]+);?", rest)
            if m:
                tmpl = m.group(1).strip()
                rest = rest.replace(m.group(0), "")
            g = re.search(r"gap:\s*([^;]+);?", rest)
            if g:
                gap = g.group(1).strip()
                rest = rest.replace(g.group(0), "")
            if rest.strip(" ;"):
                return raw(el, "grid with style")
        children = [c for c in el.children if isinstance(c, Tag)]
        if any(isinstance(c, NavigableString) and str(c).strip() for c in el.children):
            return raw(el, "grid with text")
        if tmpl and not n:
            parts = []
            for c in children:
                parts.append(col_part(c))
            inner = []
            for i, p in enumerate(parts):
                if i:
                    inner.append("|||")
                inner += p
            args = tmpl + (f" gap={gap}" if gap else "") + (" " + " ".join(extra) if extra else "")
            if extra:
                return raw(el, "cols with extra classes")
            return container("cols", args.replace(" gap=30px", ""), inner)
        if not n:
            return raw(el, "grid without gN")
        all_cards = all(c.name == "div" and ("card" in classes(c) or "callout" in classes(c))
                        and not c.get("style") for c in children)
        inner = []
        if all_cards:
            for c in children:
                inner += block(c)
        else:
            for i, c in enumerate(children):
                if i:
                    inner.append("|||")
                inner += col_part(c)
        args = n + (" " + " ".join(extra) if extra else "") + (f" gap={gap}" if gap else "")
        return container("grid", args, inner)
    if cls == ["steps"] and not style:
        inner = []
        for st in el.find_all("div", class_="step", recursive=False):
            d = st.find("div", recursive=False)
            inner += blocks_of(d)
        return container("steps", "", inner)
    if cls == ["takeaways"] and not style:
        inner = []
        for tk in el.find_all("div", class_="tk", recursive=False):
            d = tk.find("div", recursive=False)
            inner += blocks_of(d)
        return container("takeaways", "", inner)
    if "row" in cls and cls == ["row"]:
        r = flow_block(el)
        return r if r is not None else raw(el, "row (not a simple flow)")
    if cls == ["col"] and not style:
        return container("col", "", blocks_of(el))
    return raw(el, f"div.{'.'.join(cls)}")


def blocks_of(el: Tag, inline_ok=False) -> list[str]:
    """Convert the children of el; consecutive agenda rows become one ::: agenda."""
    out, agenda = [], []
    children = list(el.children)
    # an element with only inline content (callout text) -> one paragraph
    if inline_ok and all(isinstance(c, NavigableString) or c.name in ("b", "strong", "i", "em", "code", "a", "br", "span")
                         for c in children):
        s = inline(el).strip()
        return [s] if s else []
    buf_inline = []

    def flush_inline():
        if buf_inline:
            s = "".join(buf_inline)
            s = re.sub(r"[ \t\r\n]+", " ", s).strip()
            if s:
                out.append(s)
            buf_inline.clear()

    def flush_agenda():
        if agenda:
            out.extend(container("agenda", "", ["\n".join(agenda)]))
            agenda.clear()

    for c in children:
        if isinstance(c, NavigableString):
            if type(c).__name__ == "Comment":
                continue
            if str(c).strip():
                buf_inline.append(esc_text(str(c)))
            continue
        if c.name in ("b", "strong", "i", "em", "code", "a", "br", "span"):
            wrapper = BeautifulSoup("<x></x>", "html.parser").x
            wrapper.append(c.__copy__())
            buf_inline.append(inline(wrapper))
            continue
        flush_inline()
        if "agenda-row" in classes(c):
            r = agenda_item(c)
            if r is not None:
                agenda.append(r)
                continue
        flush_agenda()
        out += block(c)
    flush_inline()
    flush_agenda()
    return out


def agenda_item(row: Tag) -> str | None:
    if row.get("style"):
        return None
    tm = row.find("span", class_="tm")
    ti = row.find("div", class_="ti")
    de = row.find("div", class_="de")
    if not tm or not ti:
        return None
    extra = [c for c in classes(row) if c != "agenda-row"]
    parts = [inline(tm).strip(), inline(ti).strip()] + ([inline(de).strip()] if de else [])
    return "- " + " | ".join(parts) + (" " + attrline(extra) if extra else "")


# ---------------------------------------------------------------------------
# slides
# ---------------------------------------------------------------------------
def heading_attrs(cls: list[str], at: dict[str, str]) -> str:
    parts = [f".{c}" for c in cls]
    for k, v in at.items():
        parts.append(k if v is True else f'{k}="{v}"')
    return (" {" + " ".join(parts) + "}") if parts else ""


def convert_slide(sec: Tag, mode: str) -> tuple[str, str]:
    cls = classes(sec)
    kind = [c for c in cls if c not in ("slide",)]
    smode = "appendix" if "appendix" in kind else "bonus" if "bonus" in kind else ""
    kind = [c for c in kind if c not in ("appendix", "bonus")]
    at: dict = {}
    if sec.has_attr("data-nofit"):
        at["nofit"] = True
    if sec.has_attr("data-nofoot"):
        at["nofoot"] = True
    if sec.get("style"):
        at["style"] = sec["style"]
    notes = []
    for aside in sec.find_all("aside", class_="notes"):
        notes.append("Note: " + inline(aside).strip())
        aside.extract()

    if "title" in kind:
        kicker = sec.find(class_="kicker")
        h1 = sec.find("h1")
        sub = sec.find("p", class_="sub")
        meta = sec.find(class_="meta")
        at2 = {}
        if kicker:
            at2["kicker"] = inline(kicker).strip().replace('"', "&quot;")
        if meta:
            at2["pills"] = " | ".join(inline(p).strip() for p in meta.find_all("span"))
        at2.update(at)
        if smode != mode:
            kind.append(smode or "main")
        lines = [f"# {inline(h1).strip()}{heading_attrs(kind, at2)}"]
        if sub:
            lines.append(inline(sub).strip())
        return "\n".join(lines + notes), mode

    if "section" in kind:
        num = sec.find(class_="num")
        h2 = sec.find("h2")
        lede = sec.find("p", class_="lede")
        at2 = {}
        if num:
            at2["num"] = num.get_text().strip()
        at2.update(at)
        if smode != mode:
            kind.append(smode or "main")
        lines = [f"# {inline(h2).strip()}{heading_attrs(kind, at2)}"]
        if lede:
            lines.append(inline(lede).strip())
        return "\n".join(lines + notes), smode

    head = sec.find("div", class_="head", recursive=False)
    content = sec.find("div", class_=re.compile(r"\bcontent\b"), recursive=False)
    at2 = {}
    eyebrow = head.find(class_="eyebrow") if head else None
    h2 = head.find("h2") if head else None
    lede = head.find("p", class_="lede") if head else None
    if eyebrow:
        at2["eyebrow"] = inline(eyebrow).strip().replace('"', "&quot;")
    if content is not None:
        extra = [c for c in classes(content) if c != "content"]
        if extra:
            at2["content"] = " ".join(extra)
        if content.get("style"):
            at2["content-style"] = content["style"]
    at2.update(at)
    if smode != mode:
        kind.append(smode or "main")
    lines = [f"## {inline(h2).strip() if h2 else ''}{heading_attrs(kind, at2)}"]
    if lede:
        lines.append("> " + inline(lede).strip())
    others = [c for c in (head.children if head else []) if isinstance(c, Tag) and c not in (eyebrow, h2, lede)]
    if others:
        REPORT.append("extra elements in .head")
    body = blocks_of(content) if content is not None else []
    rest = [c for c in sec.children if isinstance(c, Tag) and c not in (head, content)]
    for r in rest:
        body += raw(r, "element outside .content")
    return "\n".join(lines) + ("\n\n" + "\n\n".join(body) if body else "") + ("\n\n" + "\n".join(notes) if notes else ""), mode


def convert(path: pathlib.Path) -> pathlib.Path:
    REPORT.clear()
    soup = BeautifulSoup(path.read_text(), "html.parser")
    body = soup.body
    title = soup.title.get_text() if soup.title else path.stem
    meta = {"title": title, "footer": body.get("data-title", ""), "accent": body.get("data-sec", "welcome")}
    styles = [s.get_text() for s in soup.head.find_all("style")]
    if styles:
        meta["css"] = "\n".join(s.strip("\n") for s in styles)
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000)
    slides = []
    mode = ""
    for sec in soup.find_all("section", class_="slide"):
        md, mode = convert_slide(sec, mode)
        slides.append(md)
    out = ROOT / "slides" / (path.stem + ".md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(f"---\n{front}---\n\n" + "\n\n---\n\n".join(slides) + "\n")
    from collections import Counter
    print(f"{path.name} -> slides/{out.name}: {len(slides)} slides; raw blocks: {dict(Counter(REPORT))}")
    return out


if __name__ == "__main__":
    for a in sys.argv[1:]:
        convert(pathlib.Path(a))
