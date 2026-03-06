"""
validator.py
------------
Annotation quality checks run as part of the CI pipeline.

Checks:
  1. Every annotated filename exists in the image directory.
  2. All polygons have >= 3 points.
  3. All labels are in CANONICAL_CLASSES.
  4. No region with 0 area.
  5. Polygon points are within image bounds (if image is loadable).
  6. Class distribution report (warns on heavy imbalance).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .parsers import ParsedImage, CANONICAL_CLASSES

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    class_counts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = [
            f"Validation {'PASSED' if self.ok else 'FAILED'}",
            f"  Errors:   {len(self.errors)}",
            f"  Warnings: {len(self.warnings)}",
            "  Class distribution:",
        ]
        for cls, cnt in sorted(self.class_counts.items(), key=lambda x: -x[1]):
            lines.append(f"    {cls:<25} {cnt:>5}")
        if self.errors:
            lines.append("  ERRORS:")
            for e in self.errors:
                lines.append(f"    ✗ {e}")
        if self.warnings:
            lines.append("  WARNINGS:")
            for w in self.warnings:
                lines.append(f"    ⚠ {w}")
        return "\n".join(lines)


def validate_annotations(
    images: Sequence[ParsedImage],
    image_dir: str | Path | None = None,
) -> ValidationResult:
    result = ValidationResult()
    image_dir = Path(image_dir) if image_dir else None

    for cls in CANONICAL_CLASSES:
        result.class_counts[cls] = 0

    for img in images:
        # 1. File existence
        if image_dir is not None:
            img_path = image_dir / img.filename
            if not img_path.exists():
                result.errors.append(f"Missing image: {img.filename}")
                continue

        # Load image size if possible
        img_size: tuple[int, int] | None = None
        if image_dir is not None:
            try:
                from PIL import Image as PILImage
                with PILImage.open(image_dir / img.filename) as pil:
                    img_size = pil.size  # (width, height)
            except Exception:
                pass

        for i, reg in enumerate(img.regions):
            prefix = f"{img.filename}[region {i}]"

            # 2. Minimum points
            if len(reg.xs) < 3:
                result.errors.append(f"{prefix}: polygon has < 3 points")
                continue

            # 3. Known label
            if reg.label not in CANONICAL_CLASSES:
                result.errors.append(f"{prefix}: unknown label '{reg.label}'")
                continue

            result.class_counts[reg.label] += 1

            # 4. Non-zero area (cross product check)
            area = _polygon_area(reg.xs, reg.ys)
            if area == 0:
                result.errors.append(f"{prefix}: polygon has zero area")

            # 5. Bounds check
            if img_size is not None:
                w, h = img_size
                if any(x < 0 or x >= w for x in reg.xs):
                    result.warnings.append(
                        f"{prefix}: x-coordinates out of image width {w}"
                    )
                if any(y < 0 or y >= h for y in reg.ys):
                    result.warnings.append(
                        f"{prefix}: y-coordinates out of image height {h}"
                    )

    # 6. Class imbalance
    counts = [v for v in result.class_counts.values() if v > 0]
    if len(counts) >= 2:
        ratio = max(counts) / min(counts)
        if ratio > 10:
            result.warnings.append(
                f"Heavy class imbalance (max/min ratio = {ratio:.1f}). "
                "Consider augmentation or resampling."
            )

    return result


def _polygon_area(xs: list[int], ys: list[int]) -> float:
    """Shoelace formula."""
    n = len(xs)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += xs[i] * ys[j]
        area -= xs[j] * ys[i]
    return abs(area) / 2.0
