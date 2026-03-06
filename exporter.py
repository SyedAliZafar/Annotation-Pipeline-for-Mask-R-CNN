"""
exporter.py
-----------
Converts ParsedImage objects → standard VIA project JSON
that train.py (Schema A / {"defect": "<class_name>"}) can read directly.

Also exports PNG mask files for visual inspection.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Sequence

import numpy as np

from .parsers import ParsedImage, CANONICAL_CLASSES

logger = logging.getLogger(__name__)


# ── VIA JSON export ──────────────────────────────────────────────────────────

def _make_image_key(filename: str, size: int = -1) -> str:
    """VIA 2 uses '<filename><size>' as the dict key."""
    return f"{filename}{size}"


def build_via_project(
    images: Sequence[ParsedImage],
    project_name: str = "exported_annotations",
) -> dict:
    """
    Build a VIA 2 project dict from a sequence of ParsedImage objects.
    Uses Schema A region_attributes: {"defect": "<canonical_class_name>"}.
    """
    via_img_metadata: dict = {}
    via_image_id_list: list = []

    for img in images:
        key = _make_image_key(img.filename)
        regions = []
        for reg in img.regions:
            regions.append({
                "shape_attributes": {
                    "name": "polygon",
                    "all_points_x": reg.xs,
                    "all_points_y": reg.ys,
                },
                "region_attributes": {
                    "defect": reg.label,
                },
            })

        via_img_metadata[key] = {
            "filename": img.filename,
            "size": -1,
            "regions": regions,
            "file_attributes": {},
        }
        via_image_id_list.append(key)

    # Build class attribute options for VIA UI
    class_options = {str(i + 1): name for i, name in enumerate(CANONICAL_CLASSES)}

    return {
        "_via_settings": {
            "ui": {"annotation_editor_height": 25, "annotation_editor_fontsize": 0.8},
            "core": {"buffer_size": 18, "filepath": {}, "default_filepath": ""},
            "project": {"name": project_name},
        },
        "_via_img_metadata": via_img_metadata,
        "_via_attributes": {
            "region": {
                "defect": {
                    "type": "dropdown",
                    "description": "Defect class",
                    "options": class_options,
                    "default_options": {},
                }
            },
            "file": {},
        },
        "_via_data_format_version": "2.0.10",
        "_via_image_id_list": via_image_id_list,
    }


def save_via_json(
    images: Sequence[ParsedImage],
    output_path: str | Path,
    project_name: str = "exported_annotations",
) -> Path:
    """
    Write a VIA project JSON to *output_path*.
    Returns the resolved output path.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    project = build_via_project(images, project_name=project_name)
    output_path.write_text(
        json.dumps(project, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved %d images → %s", len(images), output_path)
    return output_path


# ── PNG mask export ──────────────────────────────────────────────────────────

def save_masks(
    images: Sequence[ParsedImage],
    image_dir: str | Path,
    output_dir: str | Path,
    *,
    overlay_alpha: float = 0.45,
) -> list[Path]:
    """
    For each ParsedImage, render coloured polygon masks and save:
        <output_dir>/<stem>_masks.png   – overlay on the original image
        <output_dir>/<stem>_labels.png  – class-coloured filled masks only

    Requires pillow and skimage.
    Returns list of saved overlay paths.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import skimage.draw
    except ImportError as e:
        raise ImportError("pip install pillow scikit-image") from e

    image_dir = Path(image_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # One distinct colour per class (RGBA)
    CLASS_COLORS: dict[str, tuple] = {
        "schichtablosung":   (255,  80,  80, 180),
        "schichtauflosung":  ( 80, 160, 255, 180),
        "unbenetzte_stelle": ( 80, 255, 120, 180),
        "unbesandete_stelle":(255, 200,  40, 180),
        "floatinglines":     (220,  80, 255, 180),
    }
    default_color = (180, 180, 180, 160)

    saved: list[Path] = []

    for img_data in images:
        src = image_dir / img_data.filename
        if not src.exists():
            logger.warning("Image not found, skipping mask: %s", src)
            continue

        orig = Image.open(src).convert("RGBA")
        overlay = Image.new("RGBA", orig.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for reg in img_data.regions:
            color = CLASS_COLORS.get(reg.label, default_color)
            pts = list(zip(reg.xs, reg.ys))
            draw.polygon(pts, fill=color, outline=(255, 255, 255, 220))

        # Composite
        composite = Image.alpha_composite(orig, overlay).convert("RGB")
        out_path = output_dir / (Path(img_data.filename).stem + "_mask_overlay.jpg")
        composite.save(out_path, quality=92)
        saved.append(out_path)

    logger.info("Saved %d mask overlays → %s", len(saved), output_dir)
    return saved
