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
