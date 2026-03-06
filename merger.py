"""
merger.py
---------
Merge multiple VIA annotation files (any supported schema) into one
canonical VIA project JSON.

Conflict strategy:
  - If the same filename appears in multiple files, their regions are UNION-merged.
  - Duplicate polygons (identical point lists) are de-duplicated.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Sequence

from .parsers import ParsedImage, ParsedRegion, parse_via_file

logger = logging.getLogger(__name__)


def _region_hash(reg: ParsedRegion) -> str:
    """Stable hash for a region so duplicates can be detected."""
    key = f"{reg.label}|{reg.xs}|{reg.ys}"
    return hashlib.md5(key.encode()).hexdigest()


def merge_via_files(
    json_paths: Sequence[str | Path],
    *,
    on_conflict: str = "union",   # "union" | "first" | "last"
) -> list[ParsedImage]:
    """
    Merge multiple VIA JSON files into a unified list of ParsedImage objects.

    Parameters
    ----------
    json_paths:
        Paths to VIA project JSON files (any schema variant).
    on_conflict:
        How to handle the same filename appearing in multiple files.
        'union'  – merge all regions (default)
        'first'  – keep regions from the first file that mentions the image
        'last'   – keep regions from the last file that mentions the image

    Returns
    -------
    List of ParsedImage, one per unique filename, sorted by filename.
    """
    # filename → {region_hash: ParsedRegion}
    merged: dict[str, dict[str, ParsedRegion]] = {}
    source_order: dict[str, list[str]] = {}  # filename → ordered file sources

    for path in json_paths:
        path = Path(path)
        images = parse_via_file(path)
        for img in images:
            if img.filename not in merged:
                merged[img.filename] = {}
                source_order[img.filename] = []

            source_order[img.filename].append(str(path.name))

            if on_conflict == "first" and len(source_order[img.filename]) > 1:
                continue  # skip later files
            if on_conflict == "last":
                merged[img.filename] = {}  # reset, take new file

            for reg in img.regions:
                h = _region_hash(reg)
                if h not in merged[img.filename]:
                    merged[img.filename][h] = reg
                else:
                    logger.debug("Duplicate region skipped in %s", img.filename)

    result: list[ParsedImage] = []
    for filename in sorted(merged.keys()):
        regions = list(merged[filename].values())
        result.append(ParsedImage(filename, regions))
        sources = source_order[filename]
        if len(sources) > 1:
            logger.info(
                "%s: merged from %d sources (%d regions total)",
                filename, len(sources), len(regions),
            )

    logger.info(
        "Merge complete: %d unique images, %d total regions",
        len(result),
        sum(len(img.regions) for img in result),
    )
    return result


def merge_and_save(
    json_paths: Sequence[str | Path],
    output_path: str | Path,
    *,
    on_conflict: str = "union",
    project_name: str = "merged_annotations",
) -> Path:
    """Convenience: merge files and save the result as a VIA JSON."""
    from .exporter import save_via_json

    merged = merge_via_files(json_paths, on_conflict=on_conflict)
    return save_via_json(merged, output_path, project_name=project_name)
