"""
tests/test_pipeline.py
-----------------------
Unit + integration tests for the annotation pipeline.
Run with:  pytest tests/ -v
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Make sure the package is importable when running tests from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from annotation_pipeline.parsers import (
    parse_via_file,
    CANONICAL_CLASSES,
    ParsedImage,
    ParsedRegion,
    _extract_label_schema_a,
    _extract_label_schema_b,
    _extract_label_schema_c,
)
from annotation_pipeline.exporter import build_via_project, save_via_json
from annotation_pipeline.merger import merge_via_files
from annotation_pipeline.validator import validate_annotations, _polygon_area


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_polygon(xs, ys):
    return {
        "shape_attributes": {"name": "polygon", "all_points_x": xs, "all_points_y": ys},
    }


def _write_via(tmp_path: Path, entries: dict, via_attributes: dict = None) -> Path:
    """Write a minimal VIA JSON to a temp file."""
    data = {
        "_via_img_metadata": entries,
        "_via_data_format_version": "2.0.10",
        "_via_image_id_list": list(entries.keys()),
    }
    if via_attributes:
        data["_via_attributes"] = via_attributes
    p = tmp_path / "test_via.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ── Schema label extraction ───────────────────────────────────────────────────

class TestSchemaExtraction:
    def test_schema_a_known_label(self):
        assert _extract_label_schema_a({"defect": "schichtablosung"}) == "schichtablosung"

    def test_schema_a_german_umlaut(self):
        assert _extract_label_schema_a({"defect": "schichtablösung"}) == "schichtablosung"

    def test_schema_a_empty(self):
        assert _extract_label_schema_a({"defect": ""}) is None

    def test_schema_a_missing_key(self):
        assert _extract_label_schema_a({}) is None

    def test_schema_b_present(self):
        assert _extract_label_schema_b({"unbenetzte Stelle": ""}) == "unbenetzte_stelle"

    def test_schema_b_absent(self):
        assert _extract_label_schema_b({}) is None

    def test_schema_c_checkbox(self):
        ra = {"Defects": {"2": True, "3": False}}
        option_map = {"2": "Unbenetzte Stelle", "3": "Unbesandete Stelle"}
        labels = _extract_label_schema_c(ra, option_map)
        assert labels == ["unbenetzte_stelle"]

    def test_schema_c_multiple_checked(self):
        ra = {"Defects": {"2": True, "3": True}}
        option_map = {"2": "Unbenetzte Stelle", "3": "Unbesandete Stelle"}
        labels = _extract_label_schema_c(ra, option_map)
        assert set(labels) == {"unbenetzte_stelle", "unbesandete_stelle"}

    def test_schema_c_no_checks(self):
        ra = {"Defects": {"2": False}}
        labels = _extract_label_schema_c(ra, {})
        assert labels == []

    def test_schema_c_unknown_option_id(self):
        ra = {"Defects": {"99": True}}
        labels = _extract_label_schema_c(ra, {})
        assert labels == []


# ── Parser ────────────────────────────────────────────────────────────────────

class TestParser:
    def test_parse_schema_a(self, tmp_path):
        entries = {
            "img1.png1": {
                "filename": "img1.png",
                "size": 1,
                "regions": [{
                    **_make_polygon([0, 10, 10], [0, 0, 10]),
                    "region_attributes": {"defect": "schichtablosung"},
                }],
                "file_attributes": {},
            }
        }
        path = _write_via(tmp_path, entries)
        images = parse_via_file(path)
        assert len(images) == 1
        assert images[0].filename == "img1.png"
        assert images[0].regions[0].label == "schichtablosung"

    def test_parse_schema_b(self, tmp_path):
        entries = {
            "img2.png1": {
                "filename": "img2.png",
                "size": 1,
                "regions": [{
                    **_make_polygon([0, 10, 10], [0, 0, 10]),
                    "region_attributes": {"unbenetzte Stelle": ""},
                }],
                "file_attributes": {},
            }
        }
        path = _write_via(tmp_path, entries)
        images = parse_via_file(path)
        assert images[0].regions[0].label == "unbenetzte_stelle"

    def test_parse_schema_c(self, tmp_path):
        entries = {
            "img3.png1": {
                "filename": "img3.png",
                "size": 1,
                "regions": [{
                    **_make_polygon([0, 10, 10], [0, 0, 10]),
                    "region_attributes": {"Defects": {"2": True}},
                }],
                "file_attributes": {},
            }
        }
        via_attributes = {
            "region": {
                "Defects": {
                    "type": "checkbox",
                    "options": {"2": "Unbenetzte Stelle"},
                    "default_options": {},
                }
            },
            "file": {},
        }
        path = _write_via(tmp_path, entries, via_attributes)
        images = parse_via_file(path)
        assert images[0].regions[0].label == "unbenetzte_stelle"

    def test_parse_skips_non_polygon(self, tmp_path):
        entries = {
            "img4.png1": {
                "filename": "img4.png",
                "size": 1,
                "regions": [{
                    "shape_attributes": {"name": "rect", "x": 0, "y": 0, "width": 10, "height": 10},
                    "region_attributes": {"defect": "schichtablosung"},
                }],
                "file_attributes": {},
            }
        }
        path = _write_via(tmp_path, entries)
        images = parse_via_file(path)
        assert len(images) == 0

    def test_parse_skips_unknown_label(self, tmp_path):
        entries = {
            "img5.png1": {
                "filename": "img5.png",
                "size": 1,
                "regions": [{
                    **_make_polygon([0, 10, 10], [0, 0, 10]),
                    "region_attributes": {"defect": "unknown_defect"},
                }],
                "file_attributes": {},
            }
        }
        path = _write_via(tmp_path, entries)
        images = parse_via_file(path)
        assert len(images) == 0

    def test_parse_empty_file(self, tmp_path):
        path = _write_via(tmp_path, {})
        images = parse_via_file(path)
        assert images == []


# ── Exporter ──────────────────────────────────────────────────────────────────

class TestExporter:
    def test_build_via_project_schema_a(self):
        images = [
            ParsedImage("a.png", [ParsedRegion("schichtablosung", [0, 10, 10], [0, 0, 10])])
        ]
        project = build_via_project(images)
        meta = list(project["_via_img_metadata"].values())[0]
        assert meta["filename"] == "a.png"
        assert meta["regions"][0]["region_attributes"]["defect"] == "schichtablosung"

    def test_save_and_reload(self, tmp_path):
        images = [
            ParsedImage("b.png", [
                ParsedRegion("floatinglines", [5, 15, 15, 5], [5, 5, 15, 15])
            ])
        ]
        out = tmp_path / "out.json"
        save_via_json(images, out)
        assert out.exists()
        reloaded = parse_via_file(out)
        assert len(reloaded) == 1
        assert reloaded[0].regions[0].label == "floatinglines"


# ── Merger ────────────────────────────────────────────────────────────────────

class TestMerger:
    def _make_file(self, tmp_path, name, filename, label):
        entries = {
            f"{filename}1": {
                "filename": filename,
                "size": 1,
                "regions": [{
                    **_make_polygon([0, 10, 10], [0, 0, 10]),
                    "region_attributes": {"defect": label},
                }],
                "file_attributes": {},
            }
        }
        p = tmp_path / name
        p.write_text(json.dumps({"_via_img_metadata": entries}), encoding="utf-8")
        return p

    def test_merge_disjoint_files(self, tmp_path):
        a = self._make_file(tmp_path, "a.json", "img1.png", "schichtablosung")
        b = self._make_file(tmp_path, "b.json", "img2.png", "floatinglines")
        merged = merge_via_files([a, b])
        filenames = {img.filename for img in merged}
        assert filenames == {"img1.png", "img2.png"}

    def test_merge_same_image_union(self, tmp_path):
        a = self._make_file(tmp_path, "a.json", "img1.png", "schichtablosung")
        b = self._make_file(tmp_path, "b.json", "img1.png", "floatinglines")
        merged = merge_via_files([a, b], on_conflict="union")
        assert len(merged) == 1
        labels = {r.label for r in merged[0].regions}
        assert labels == {"schichtablosung", "floatinglines"}

    def test_merge_same_image_first(self, tmp_path):
        a = self._make_file(tmp_path, "a.json", "img1.png", "schichtablosung")
        b = self._make_file(tmp_path, "b.json", "img1.png", "floatinglines")
        merged = merge_via_files([a, b], on_conflict="first")
        assert merged[0].regions[0].label == "schichtablosung"

    def test_merge_deduplicates_identical_regions(self, tmp_path):
        a = self._make_file(tmp_path, "a.json", "img1.png", "schichtablosung")
        b = self._make_file(tmp_path, "b.json", "img1.png", "schichtablosung")
        merged = merge_via_files([a, b], on_conflict="union")
        assert len(merged[0].regions) == 1  # deduped


# ── Validator ─────────────────────────────────────────────────────────────────

class TestValidator:
    def test_valid_annotations(self):
        images = [
            ParsedImage("x.png", [ParsedRegion("schichtablosung", [0, 10, 10], [0, 0, 10])])
        ]
        result = validate_annotations(images, image_dir=None)
        assert result.ok

    def test_unknown_label(self):
        images = [
            ParsedImage("x.png", [ParsedRegion("badlabel", [0, 10, 10], [0, 0, 10])])
        ]
        result = validate_annotations(images, image_dir=None)
        assert not result.ok

    def test_too_few_points(self):
        images = [
            ParsedImage("x.png", [ParsedRegion("schichtablosung", [0, 10], [0, 10])])
        ]
        result = validate_annotations(images, image_dir=None)
        assert not result.ok

    def test_zero_area(self):
        # Collinear points → zero area
        images = [
            ParsedImage("x.png", [ParsedRegion("schichtablosung", [0, 5, 10], [0, 0, 0])])
        ]
        result = validate_annotations(images, image_dir=None)
        assert not result.ok

    def test_polygon_area_triangle(self):
        area = _polygon_area([0, 10, 0], [0, 0, 10])
        assert abs(area - 50.0) < 0.01

    def test_class_counts(self):
        images = [
            ParsedImage("x.png", [
                ParsedRegion("schichtablosung", [0, 10, 10], [0, 0, 10]),
                ParsedRegion("schichtablosung", [0, 5, 5], [0, 0, 5]),
                ParsedRegion("floatinglines",   [0, 10, 10], [0, 0, 10]),
            ])
        ]
        result = validate_annotations(images, image_dir=None)
        assert result.class_counts["schichtablosung"] == 2
        assert result.class_counts["floatinglines"] == 1

    def test_missing_image_file(self, tmp_path):
        images = [
            ParsedImage("does_not_exist.png", [
                ParsedRegion("schichtablosung", [0, 10, 10], [0, 0, 10])
            ])
        ]
        result = validate_annotations(images, image_dir=tmp_path)
        assert not result.ok
        assert any("Missing image" in e for e in result.errors)


# ── Round-trip integration test ───────────────────────────────────────────────

class TestRoundTrip:
    def test_gp_style_roundtrip(self, tmp_path):
        """Schema C (GP checkbox style) → parse → export → re-parse → same data."""
        entries = {
            "real_img.png99": {
                "filename": "real_img.png",
                "size": 99,
                "regions": [
                    {
                        **_make_polygon([681, 692, 710, 680], [1183, 1189, 1193, 1199]),
                        "region_attributes": {"Defects": {"2": True}},
                    }
                ],
                "file_attributes": {},
            }
        }
        via_attributes = {
            "region": {
                "Defects": {
                    "type": "checkbox",
                    "options": {
                        "1": "Fließlinie", "2": "Unbenetzte Stelle",
                        "3": "Unbesandete Stelle", "6": "Schichtablösung",
                    },
                    "default_options": {},
                }
            },
            "file": {},
        }
        src = tmp_path / "gp_style.json"
        src.write_text(json.dumps({
            "_via_img_metadata": entries,
            "_via_attributes": via_attributes,
        }), encoding="utf-8")

        # Parse
        images = parse_via_file(src)
        assert len(images) == 1
        assert images[0].regions[0].label == "unbenetzte_stelle"

        # Export
        out = tmp_path / "exported.json"
        save_via_json(images, out)

        # Re-parse
        reloaded = parse_via_file(out)
        assert len(reloaded) == 1
        assert reloaded[0].regions[0].label == "unbenetzte_stelle"
        assert reloaded[0].regions[0].xs == [681, 692, 710, 680]
