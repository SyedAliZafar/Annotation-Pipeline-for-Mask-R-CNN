# Annotation Pipeline for Mask R-CNN

A unified annotation processing pipeline that handles **all VIA project JSON formats**, converts them to a single canonical schema, supports merging multiple files, validates quality, and generates visual mask overlays — with a full GitHub Actions CI/CD pipeline.

---

## The Problem This Solves

VIA annotations arrive in different formats depending on who created them:

| Schema | Example `region_attributes` | Source |
|--------|----------------------------|--------|
| **A** (train.py style) | `{"defect": "schichtablosung"}` | Original dataset |
| **B** (QualiFei style) | `{"unbenetzte Stelle": ""}` | QualiFei export |
| **C** (checkbox / GP style) | `{"Defects": {"2": true}}` | This dataset |

This pipeline auto-detects the schema and normalises everything to Schema A, which `train.py` reads natively.

---

## Canonical Class Names

| ID | Name | German original |
|----|------|----------------|
| 1 | `schichtablosung` | Schichtablösung |
| 2 | `schichtauflosung` | Schichtauflösung |
| 3 | `unbenetzte_stelle` | Unbenetzte Stelle |
| 4 | `unbesandete_stelle` | Unbesandete Stelle |
| 5 | `floatinglines` | Fließlinie |

---

## Installation

```bash
git clone https://github.com/your-org/annotation-pipeline.git
cd annotation-pipeline
pip install -r requirements.txt          # runtime
pip install -r requirements-dev.txt     # tests + linting
```

---

## CLI Usage

### Convert a new annotation file

```bash
python -m annotation_pipeline.cli convert \
  --input  raw/annotation_dataset_20260221_defects_GP.json \
  --output exports/via_project.json \
  --masks  exports/masks/ \
  --image-dir  /path/to/images/ \
  --validate
```

### Merge multiple annotation files

```bash
python -m annotation_pipeline.cli merge \
  --inputs  set_a.json set_b.json set_c.json \
  --output  merged/via_project.json \
  --on-conflict union \
  --image-dir /path/to/images/ \
  --validate
```

`--on-conflict` options:
- `union` *(default)* — combine all regions; deduplicate identical polygons
- `first` — keep only regions from the first file per image
- `last`  — keep only regions from the last file per image

### Validate

```bash
python -m annotation_pipeline.cli validate \
  --input merged/via_project.json \
  --image-dir /path/to/images/
```

Exits with code **2** if errors are found (CI-friendly).

### Visual inspection (random sample)

```bash
python -m annotation_pipeline.cli inspect \
  --input merged/via_project.json \
  --image-dir /path/to/images/ \
  --output-dir inspection/ \
  --n 8 \
  --seed 42
```

### Inspect a specific image

```bash
python -m annotation_pipeline.cli inspect \
  --input merged/via_project.json \
  --image-dir /path/to/images/ \
  --output-dir inspection/ \
  --filename 20260219-180728_7669-1_3-232.png
```

### Compare two annotation sets side by side

```bash
python -m annotation_pipeline.cli compare \
  --input-a  set_a.json \
  --input-b  set_b.json \
  --filename 20260219-135829_7669-1_2-220.png \
  --image-dir /path/to/images/ \
  --output-dir comparison/ \
  --label-a "Before merge" \
  --label-b "After merge"
```

---

## Python API

```python
from annotation_pipeline import (
    parse_via_file,
    save_via_json,
    merge_via_files,
    validate_annotations,
    random_inspection,
)

# Parse any VIA format
images = parse_via_file("raw_annotations.json")

# Validate
result = validate_annotations(images, image_dir="images/")
print(result.summary())

# Merge multiple files
merged = merge_via_files(["week1.json", "week2.json", "week3.json"])

# Export canonical VIA JSON (train.py compatible)
save_via_json(merged, "exports/via_project.json")

# Visual inspection
random_inspection(merged, image_dir="images/", output_dir="inspection/", n=5)
```

---

## Repository Layout

```
annotation-pipeline/
├── annotation_pipeline/
│   ├── __init__.py        # Public API
│   ├── parsers.py         # Auto-detect & parse all VIA schemas
│   ├── exporter.py        # VIA JSON + mask PNG export
│   ├── merger.py          # Multi-file merge with deduplication
│   ├── validator.py       # Quality checks (CI-safe exit codes)
│   ├── visualizer.py      # Mask overlays & side-by-side compare
│   └── cli.py             # CLI entry point
├── tests/
│   └── test_pipeline.py   # Full unit + integration test suite
├── annotations/
│   ├── incoming/          # Drop new annotation files here
│   └── merged/            # Auto-generated merged output
├── .github/workflows/
│   └── annotation_pipeline.yml   # CI/CD pipeline
├── requirements.txt
├── requirements-dev.txt
└── pyproject.toml
```

---

## CI/CD Pipeline

```
Push / PR  →  [1] Lint + Tests  →  [2] Validate Annotations
                                          ↓
                               [3] Merge (main branch only)
                                          ↓
                               [4] Generate Inspection Visuals
                                          ↓
                               [5] Commit merged file back to repo
```

### Automatic triggers

| Event | What runs |
|-------|-----------|
| Any push / PR | Lint, unit tests, validate changed `*.json` files |
| Push to `main` | + merge all `annotations/` files, generate inspection |
| `workflow_dispatch` | Manual run with optional `annotation_file` and `run_merge` inputs |
| Git tag `v*` | Build + GitHub Release |

### Artifacts retained

| Artifact | Retention |
|----------|-----------|
| Canonical annotation JSONs | 30 days |
| Merged annotation JSON | 90 days |
| Inspection overlay images | 14 days |

---

## Validation Checks

| Check | Severity |
|-------|----------|
| All annotated images exist in image directory | Error |
| All polygons have ≥ 3 points | Error |
| All labels in canonical class list | Error |
| No zero-area polygons | Error |
| Polygon coordinates within image bounds | Warning |
| Class imbalance > 10× | Warning |

---

## Integration with `train.py`

The exported `via_project.json` uses **Schema A** (`{"defect": "<class_name>"}`), which `train.py` already reads. No changes to `train.py` are needed.

### Typical workflow

```bash
# 1. New annotations arrive
cp new_batch_20260301.json annotations/incoming/

# 2. Merge with existing
python -m annotation_pipeline.cli merge \
  --inputs annotations/incoming/*.json \
  --output datasets/TrainingValidationDatasets/train/via_project.json \
  --image-dir datasets/TrainingValidationDatasets/train/

# 3. Run training (unchanged)
python train.py
```

Or just push to `main` — CI does steps 2 and inspection automatically.

---

## Running Tests

```bash
pytest tests/ -v --cov=annotation_pipeline
```
