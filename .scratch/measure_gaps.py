"""Crop and magnify the regions the eye complains about, so the numbers are visible."""

from __future__ import annotations

from PIL import Image

shot = Image.open(".scratch/shot5.png").convert("RGB")

regions = {
    "sidebar": (0, 0, 300, 330),
    "messages": (400, 40, 1200, 320),
}
for name, box in regions.items():
    crop = shot.crop(box)
    scale = 2
    crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    path = f".scratch/crop-{name}.png"
    crop.save(path)
    print(f"{name}: {box} -> {path} ({crop.width}x{crop.height})")

# Measure the vertical gaps in the sidebar by scanning rows for non-white pixels.
import numpy as np

arr = np.asarray(shot.crop((0, 0, 280, 340)).convert("L")).astype(int)
ink_rows = (arr < 240).sum(axis=1)
print("\nrow ink profile (y: count) where something is drawn:")
runs = []
inside = False
for y, count in enumerate(ink_rows):
    if count > 0 and not inside:
        start = y
        inside = True
    elif count == 0 and inside:
        runs.append((start, y - 1))
        inside = False
if inside:
    runs.append((start, len(ink_rows) - 1))
previous_end = None
for start, end in runs:
    gap = "" if previous_end is None else f"  gap before: {start - previous_end - 1}px"
    print(f"  y {start:>3}-{end:>3}  height {end - start + 1:>2}px{gap}")
    previous_end = end
