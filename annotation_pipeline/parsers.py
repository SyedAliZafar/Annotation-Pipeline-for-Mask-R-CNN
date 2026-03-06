"""
parsers.py
----------
Unified VIA annotation parser supporting all 3 known schema variants:

  Schema A  (train.py "defect" style):
      region_attributes: {"defect": "schichtablosung"}

  Schema B  (QualiFei style):
      region_attributes: {"unbenetzte Stelle": ""}

  Schema C  (checkbox / GP style – this dataset):
      region_attributes: {"Defects": {"2": true}}
      with _via_attributes.region.Defects.options = {"2": "Unbenetzte Stelle", ...}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Canonical class names used throughout the pipeline ──────────────────────
CANONICAL_CLASSES: list[str] = [
    "schichtablosung",      # 1
    "schichtauflosung",     # 2
    "unbenetzte_stelle",    # 3
    "unbesandete_stelle",   # 4
    "floatinglines",        # 5
]

# ── Human-readable label → canonical name ───────────────────────────────────
_LABEL_MAP: dict[str, str] = {
    # German originals
    "schichtablösung":      "schichtablosung",
    "schichtablosung":      "schichtablosung",
    "schichtauflösung":     "schichtauflosung",
    "schichtauflosung":     "schichtauflosung",
    "unbenetzte stelle":    "unbenetzte_stelle",
    "unbenetzte_stelle":    "unbenetzte_stelle",
    "unbesandete stelle":   "unbesandete_stelle",
    "unbesandete_stelle":   "unbesandete_stelle",
    "fließlinie":           "floatinglines",
    "fliesslinie":          "floatinglines",
    "fließlinien":          "floatinglines",
    "floatinglines":        "floatinglines",
    "floatingline":         "floatinglines",
    # checkbox option labels (lower-cased for robustness)
    "riss":                 None,   # not in CLASS_NAMES → skipped
    "verrutschung":         None,
}

# Checkbox option-id → canonical name (for Schema C)
_OPTION_ID_MAP: dict[str, str] = {
    "1": "floatinglines",
    "2": "unbenetzte_stelle",
    "3": "unbesandete_stelle",
    "4": None,          # Riss – not trained
    "5": None,          # Verrutschung – not trained
    "6": "schichtablosung",
    "7": "schichtauflosung",
}


def _normalise_label(raw: str) -> Optional[str]:
    """Map any raw label string to a canonical class name (or None to skip)."""
    return _LABEL_MAP.get(raw.strip().lower())


def _extract_label_schema_a(ra: dict) -> Optional[str]:
    """Schema A: {"defect": "<class_name>"}"""
    raw = ra.get("defect", "")
    if raw:
        return _normalise_label(raw)
    return None


def _extract_label_schema_b(ra: dict) -> Optional[str]:
    """Schema B: {"unbenetzte Stelle": ""}"""
    if "unbenetzte Stelle" in ra:
        return "unbenetzte_stelle"
    return None


def _extract_label_schema_c(ra: dict, option_map: Optional[dict] = None) -> list[str]:
    """
    Schema C: {"Defects": {"2": true, "3": false, ...}}
    Returns a list because a single region can be multi-labelled (checkbox).
    """
    defects_val = ra.get("Defects")
    if not isinstance(defects_val, dict):
        return []

    labels = []
    for option_id, checked in defects_val.items():
        if not checked:
            continue
        # Prefer resolved option name from _via_attributes if provided
        if option_map and option_id in option_map:
            raw_label = option_map[option_id]
            canonical = _normalise_label(raw_label)
        else:
            canonical = _OPTION_ID_MAP.get(option_id)
        if canonical:
            labels.append(canonical)
    return labels


def _build_option_map(via_data: dict) -> dict[str, str]:
    """Extract {option_id: human_label} from _via_attributes if present."""
    try:
        opts = via_data["_via_attributes"]["region"]["Defects"]["options"]
        return {str(k): str(v) for k, v in opts.items()}
    except (KeyError, TypeError):
        return {}


# ── Public API ───────────────────────────────────────────────────────────────

class ParsedRegion:
    __slots__ = ("label", "xs", "ys")

    def __init__(self, label: str, xs: list[int], ys: list[int]):
        self.label = label
        self.xs = xs
        self.ys = ys

    def __repr__(self):
        return f"ParsedRegion(label={self.label!r}, pts={len(self.xs)})"


class ParsedImage:
    __slots__ = ("filename", "regions")

    def __init__(self, filename: str, regions: list[ParsedRegion]):
        self.filename = filename
        self.regions = regions

    def __repr__(self):
        return f"ParsedImage(filename={self.filename!r}, regions={len(self.regions)})"


def parse_via_file(json_path: str | Path) -> list[ParsedImage]:
    """
    Load a VIA project JSON and return a list of ParsedImage objects.
    Handles Schema A, B, and C automatically.
    Skips images with no valid annotated regions.
    """
    json_path = Path(json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))

    option_map = _build_option_map(data)

    if "_via_img_metadata" in data:
        raw_images = list(data["_via_img_metadata"].values())
    else:
        raw_images = list(data.values())

    parsed: list[ParsedImage] = []

    for img_entry in raw_images:
        filename: str = img_entry.get("filename", "")
        raw_regions = img_entry.get("regions", [])
        parsed_regions: list[ParsedRegion] = []

        for r in raw_regions:
            sa = r.get("shape_attributes") or {}
            ra = r.get("region_attributes") or {}

            if sa.get("name") != "polygon":
                continue

            xs = sa.get("all_points_x", [])
            ys = sa.get("all_points_y", [])
            if len(xs) < 3 or len(xs) != len(ys):
                continue

            # Try all schemas
            labels: list[str] = []

            label_a = _extract_label_schema_a(ra)
            if label_a:
                labels = [label_a]
            else:
                label_b = _extract_label_schema_b(ra)
                if label_b:
                    labels = [label_b]
                else:
                    labels = _extract_label_schema_c(ra, option_map)

            for lbl in labels:
                if lbl in CANONICAL_CLASSES:
                    parsed_regions.append(ParsedRegion(lbl, xs, ys))
                else:
                    logger.debug("Skipping unknown label %r in %s", lbl, filename)

        if parsed_regions:
            parsed.append(ParsedImage(filename, parsed_regions))
        elif raw_regions:
            logger.debug("No valid regions for %s", filename)

    logger.info("Parsed %d annotated images from %s", len(parsed), json_path.name)
    return parsed
