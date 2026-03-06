"""
visualizer.py
-------------
Visual inspection helpers:
  - random_inspection()  draw random sample of annotated images with mask overlays
  - inspect_by_name()    draw a specific image
  - compare_annotations() side-by-side diff of two annotation sets for same image
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Sequence

from .parsers import ParsedImage

logger = logging.getLogger(__name__)

# Class colours (RGB)
_CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "schichtablosung":    (255, 80,  80),
    "schichtauflosung":   (80, 160, 255),
    "unbenetzte_stelle":  (80, 255, 120),
    "unbesandete_stelle": (255, 200, 40),
    "floatinglines":      (220, 80, 255),
}
_DEFAULT_COLOR = (180, 180, 180)


def _draw_single(
    img_data: ParsedImage,
    image_dir: Path,
    output_path: Path,
    title: str = "",
) -> bool:
    """Draw one image with polygon overlays. Returns True on success."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ImportError("pip install pillow")

    src = image_dir / img_data.filename
    if not src.exists():
        logger.warning("Image not found: %s", src)
        return False

    orig = Image.open(src).convert("RGBA")
    overlay = Image.new("RGBA", orig.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for reg in img_data.regions:
        color = _CLASS_COLORS.get(reg.label, _DEFAULT_COLOR)
        rgba = color + (160,)
        pts = list(zip(reg.xs, reg.ys))
        draw.polygon(pts, fill=rgba, outline=(255, 255, 255, 230))

        # Centroid label
        cx = int(sum(reg.xs) / len(reg.xs))
        cy = int(sum(reg.ys) / len(reg.ys))
        draw.text((cx, cy), reg.label, fill=(255, 255, 255, 255))

    composite = Image.alpha_composite(orig, overlay).convert("RGB")

    if title:
        from PIL import ImageDraw as ID2
        d2 = ID2.Draw(composite)
        d2.text((10, 10), title, fill=(255, 255, 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    composite.save(output_path, quality=90)
    return True


def random_inspection(
    images: Sequence[ParsedImage],
    image_dir: str | Path,
    output_dir: str | Path,
    n: int = 5,
    seed: int | None = None,
) -> list[Path]:
    """
    Draw *n* randomly selected annotated images with polygon overlays.
    Returns list of output paths.
    """
    image_dir = Path(image_dir)
    output_dir = Path(output_dir)
    rng = random.Random(seed)

    pool = [img for img in images if (image_dir / img.filename).exists()]
    if not pool:
        logger.warning("No images found in %s", image_dir)
        return []

    sample = rng.sample(pool, min(n, len(pool)))
    saved: list[Path] = []

    for img_data in sample:
        out = output_dir / f"inspect_{Path(img_data.filename).stem}.jpg"
        ok = _draw_single(img_data, image_dir, out, title=img_data.filename)
        if ok:
            saved.append(out)

    logger.info("Saved %d inspection images → %s", len(saved), output_dir)
    return saved


def inspect_by_name(
    images: Sequence[ParsedImage],
    filename: str,
    image_dir: str | Path,
    output_dir: str | Path,
) -> Path | None:
    """Draw a specific image by filename."""
    image_dir = Path(image_dir)
    output_dir = Path(output_dir)

    matches = [img for img in images if img.filename == filename]
    if not matches:
        logger.warning("Filename not found in annotations: %s", filename)
        return None

    img_data = matches[0]
    out = output_dir / f"inspect_{Path(filename).stem}.jpg"
    ok = _draw_single(img_data, image_dir, out, title=filename)
    return out if ok else None


def compare_annotations(
    images_a: Sequence[ParsedImage],
    images_b: Sequence[ParsedImage],
    filename: str,
    image_dir: str | Path,
    output_dir: str | Path,
    label_a: str = "Set A",
    label_b: str = "Set B",
) -> Path | None:
    """
    Render a side-by-side comparison of annotations for the same image
    from two different annotation sets (e.g. before/after merge).
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("pip install pillow")

    image_dir = Path(image_dir)
    output_dir = Path(output_dir)

    src = image_dir / filename
    if not src.exists():
        logger.warning("Image not found: %s", src)
        return None

    tmp_a = output_dir / f"_cmp_a_{filename}"
    tmp_b = output_dir / f"_cmp_b_{filename}"

    match_a = next((i for i in images_a if i.filename == filename), None)
    match_b = next((i for i in images_b if i.filename == filename), None)

    if match_a:
        _draw_single(match_a, image_dir, tmp_a, title=label_a)
    if match_b:
        _draw_single(match_b, image_dir, tmp_b, title=label_b)

    imgs = []
    for tmp in [tmp_a, tmp_b]:
        if tmp.exists():
            imgs.append(Image.open(tmp))

    if not imgs:
        return None

    total_w = sum(i.width for i in imgs)
    max_h = max(i.height for i in imgs)
    combined = Image.new("RGB", (total_w, max_h), (40, 40, 40))
    x = 0
    for i in imgs:
        combined.paste(i, (x, 0))
        x += i.width

    out = output_dir / f"compare_{Path(filename).stem}.jpg"
    output_dir.mkdir(parents=True, exist_ok=True)
    combined.save(out, quality=88)

    # Cleanup temp files
    for tmp in [tmp_a, tmp_b]:
        if tmp.exists():
            tmp.unlink()

    return out
