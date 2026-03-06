"""annotation_pipeline – VIA annotation processing for Mask R-CNN training."""

from .parsers import parse_via_file, CANONICAL_CLASSES, ParsedImage, ParsedRegion
from .exporter import save_via_json, save_masks
from .merger import merge_via_files, merge_and_save
from .validator import validate_annotations, ValidationResult
from .visualizer import random_inspection, inspect_by_name, compare_annotations

__all__ = [
    "parse_via_file",
    "CANONICAL_CLASSES",
    "ParsedImage",
    "ParsedRegion",
    "save_via_json",
    "save_masks",
    "merge_via_files",
    "merge_and_save",
    "validate_annotations",
    "ValidationResult",
    "random_inspection",
    "inspect_by_name",
    "compare_annotations",
]
