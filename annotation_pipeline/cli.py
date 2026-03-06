"""
cli.py
------
Command-line interface for the annotation pipeline.

Commands:
  convert   – Convert one annotation file to canonical VIA JSON (+ optional masks)
  merge     – Merge multiple annotation files into one canonical VIA JSON
  validate  – Validate annotation file(s) against image directory
  inspect   – Visual inspection: render random or named images with mask overlays
  compare   – Side-by-side comparison of two annotation sets for the same image

Examples
--------
# Convert a new annotation file to the standard format
  python -m annotation_pipeline.cli convert \
    --input raw_annotations.json \
    --output exports/via_project.json \
    --masks exports/masks --image-dir images/

# Merge two annotation files
  python -m annotation_pipeline.cli merge \
    --inputs a.json b.json \
    --output merged/via_project.json

# Validate
  python -m annotation_pipeline.cli validate \
    --input merged/via_project.json \
    --image-dir images/

# Inspect 5 random images
  python -m annotation_pipeline.cli inspect \
    --input merged/via_project.json \
    --image-dir images/ \
    --output-dir inspection/ \
    --n 5

# Compare two annotation sets for a specific image
  python -m annotation_pipeline.cli compare \
    --input-a set_a.json --input-b set_b.json \
    --filename my_image.png \
    --image-dir images/ \
    --output-dir comparison/
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )


# ── convert ──────────────────────────────────────────────────────────────────

def cmd_convert(args):
    from .parsers import parse_via_file
    from .exporter import save_via_json, save_masks
    from .validator import validate_annotations

    images = parse_via_file(args.input)
    if not images:
        print("No annotated images found. Check the input file.", file=sys.stderr)
        sys.exit(1)

    out_path = save_via_json(images, args.output)
    print(f"✓ Exported {len(images)} images → {out_path}")

    if args.masks and args.image_dir:
        saved = save_masks(images, args.image_dir, args.masks)
        print(f"✓ Saved {len(saved)} mask overlays → {args.masks}")

    if args.validate and args.image_dir:
        result = validate_annotations(images, args.image_dir)
        print(result.summary())
        if not result.ok:
            sys.exit(2)


# ── merge ─────────────────────────────────────────────────────────────────────

def cmd_merge(args):
    from .merger import merge_via_files
    from .exporter import save_via_json
    from .validator import validate_annotations

    images = merge_via_files(args.inputs, on_conflict=args.on_conflict)
    if not images:
        print("No annotations after merge.", file=sys.stderr)
        sys.exit(1)

    out_path = save_via_json(images, args.output, project_name=args.project_name)
    print(f"✓ Merged {len(args.inputs)} files → {out_path} ({len(images)} images)")

    if args.validate and args.image_dir:
        result = validate_annotations(images, args.image_dir)
        print(result.summary())
        if not result.ok:
            sys.exit(2)


# ── validate ─────────────────────────────────────────────────────────────────

def cmd_validate(args):
    from .parsers import parse_via_file
    from .validator import validate_annotations

    images = parse_via_file(args.input)
    result = validate_annotations(images, args.image_dir)
    print(result.summary())
    sys.exit(0 if result.ok else 2)


# ── inspect ──────────────────────────────────────────────────────────────────

def cmd_inspect(args):
    from .parsers import parse_via_file
    from .visualizer import random_inspection, inspect_by_name

    images = parse_via_file(args.input)

    if args.filename:
        path = inspect_by_name(images, args.filename, args.image_dir, args.output_dir)
        if path:
            print(f"✓ Saved → {path}")
        else:
            print("Image not found.", file=sys.stderr)
            sys.exit(1)
    else:
        saved = random_inspection(images, args.image_dir, args.output_dir, n=args.n, seed=args.seed)
        print(f"✓ Saved {len(saved)} inspection images → {args.output_dir}")


# ── compare ──────────────────────────────────────────────────────────────────

def cmd_compare(args):
    from .parsers import parse_via_file
    from .visualizer import compare_annotations

    images_a = parse_via_file(args.input_a)
    images_b = parse_via_file(args.input_b)

    path = compare_annotations(
        images_a, images_b,
        args.filename,
        args.image_dir,
        args.output_dir,
        label_a=args.label_a,
        label_b=args.label_b,
    )
    if path:
        print(f"✓ Comparison saved → {path}")
    else:
        print("Could not generate comparison.", file=sys.stderr)
        sys.exit(1)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="annotation-pipeline",
        description="VIA annotation pipeline for Mask R-CNN",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    # convert
    p_conv = sub.add_parser("convert", help="Convert annotation file to canonical VIA JSON")
    p_conv.add_argument("--input",      required=True,  help="Input VIA JSON")
    p_conv.add_argument("--output",     required=True,  help="Output VIA JSON path")
    p_conv.add_argument("--masks",      default=None,   help="Directory to save mask overlays")
    p_conv.add_argument("--image-dir",  default=None,   help="Directory containing images")
    p_conv.add_argument("--validate",   action="store_true")
    p_conv.set_defaults(func=cmd_convert)

    # merge
    p_merge = sub.add_parser("merge", help="Merge multiple annotation files")
    p_merge.add_argument("--inputs",       nargs="+",  required=True,  help="Input VIA JSONs")
    p_merge.add_argument("--output",       required=True,  help="Output VIA JSON path")
    p_merge.add_argument("--on-conflict",  default="union", choices=["union", "first", "last"])
    p_merge.add_argument("--project-name", default="merged_annotations")
    p_merge.add_argument("--image-dir",    default=None)
    p_merge.add_argument("--validate",     action="store_true")
    p_merge.set_defaults(func=cmd_merge)

    # validate
    p_val = sub.add_parser("validate", help="Validate annotation file")
    p_val.add_argument("--input",     required=True)
    p_val.add_argument("--image-dir", default=None)
    p_val.set_defaults(func=cmd_validate)

    # inspect
    p_ins = sub.add_parser("inspect", help="Visual inspection of mask overlays")
    p_ins.add_argument("--input",      required=True)
    p_ins.add_argument("--image-dir",  required=True)
    p_ins.add_argument("--output-dir", required=True)
    p_ins.add_argument("--n",          type=int, default=5,   help="Number of random images")
    p_ins.add_argument("--filename",   default=None,          help="Inspect a specific image")
    p_ins.add_argument("--seed",       type=int, default=None)
    p_ins.set_defaults(func=cmd_inspect)

    # compare
    p_cmp = sub.add_parser("compare", help="Side-by-side annotation comparison")
    p_cmp.add_argument("--input-a",    required=True)
    p_cmp.add_argument("--input-b",    required=True)
    p_cmp.add_argument("--filename",   required=True)
    p_cmp.add_argument("--image-dir",  required=True)
    p_cmp.add_argument("--output-dir", required=True)
    p_cmp.add_argument("--label-a",    default="Set A")
    p_cmp.add_argument("--label-b",    default="Set B")
    p_cmp.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    _setup_logging(args.verbose)
    args.func(args)


if __name__ == "__main__":
    main()
