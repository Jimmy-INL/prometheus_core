"""Contact sheets (3x3) from per-slide screenshots: python tools/sheet.py SHOTDIR PREFIX"""
import glob, sys
from PIL import Image
d, pre = sys.argv[1], sys.argv[2]
fs = sorted(glob.glob(f"{d}/{pre}-[0-9]*.png"))
w, h = 800, 450
for part in range(0, len(fs), 9):
    chunk = fs[part:part + 9]
    r = (len(chunk) + 2) // 3
    sheet = Image.new("RGB", (w * 3 + 20, h * r + 10 * (r - 1)), "#777")
    for i, f in enumerate(chunk):
        sheet.paste(Image.open(f).resize((w, h)), ((i % 3) * (w + 10), (i // 3) * (h + 10)))
    out = f"{d}/sheet-{pre}-{part // 9}.png"
    sheet.save(out)
    print(out)
