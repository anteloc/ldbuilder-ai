---
name: ldraw-builder
description: Generate LDraw models (.mpd file format) from user specifications. Use when users ask to build, create, or generate LEGO/brick models, LDraw files, .mpd files, or any brick-based 3D model. Models should be structurally sound with minimal impossible intersections and floating parts.
---

# LDraw Model Builder

## Overview

This skill generates valid LDraw `.mpd` model files from user descriptions. The workflow involves exploring reference models and parts, proposing a build plan, iteratively generating and validating the model, and delivering a clean annotated file.

**Maximum attempts:** 5 validation/fix cycles before reporting failure.

---

## Phase 0: Preliminaries (Run Once Per Session)

Before doing anything else, read the core references and set up the environment.

### 1. Read the references

```bash
# Grammar specification
cat references/ldraw.lark

# Annotated model examples (critical for understanding structure)
cat references/ANNOTATED_REFERENCE.md
```

### 2. Install dependencies

```bash
pip install -r scripts/requirements.txt --break-system-packages
# download models library from github (contains .mpd files for reference)

mkdir deps/models

cd deps/models
wget https://raw.githubusercontent.com/anteloc/claude-ldraw-skill/refs/heads/master/ldraw-skill/models.zip
unzip models.zip
rm models.zip
cd ..

# download parts-bom.tsv (contains part alias, descriptions and dimensions)
wget https://raw.githubusercontent.com/anteloc/claude-ldraw-skill/refs/heads/master/ldraw-skill/parts-bom.zip
unzip parts-bom.zip
rm parts-bom.zip
cd ..

```

### 3. Load allowed values (colors, categories, keywords)

```bash
# All valid color codes
python scripts/ldraw-query-db.py scripts/ldraw.db "SELECT code, color FROM COLORS;"

# All valid model categories
python scripts/ldraw-query-db.py scripts/ldraw.db "SELECT category FROM MODEL_AI_CATS_UNIQ;"

# All valid model keywords
python scripts/ldraw-query-db.py scripts/ldraw.db "SELECT keyword FROM MODEL_AI_KWS_UNIQ;"
```

### 4. Familiarize with table contents

```bash
# Sample models information
python scripts/ldraw-query-db.py scripts/ldraw.db "
    SELECT alias, category, description, keywords, num_parts, difficulty, size_kb
    FROM VW_MODEL_INFOS
    LIMIT 10;"

# Sample parts with bounding boxes
cat references/parts-bom.tsv | head -n 10
```

---

## Phase 1: Research Similar Models

Search for models related to what the user wants to build. Use allowed categories and keywords only.

```bash
python scripts/ldraw-query-db.py scripts/ldraw.db "
    SELECT alias, category, description, keywords, num_parts, difficulty, size_kb
    FROM VW_MODEL_INFOS
    WHERE category = '<allowed-category>'
    AND (
        description LIKE '%<keyword>%'
        OR keywords LIKE '%<keyword>%'
    )
    LIMIT 10;"
```

Then read the `.mpd` source files of the most relevant results:

```bash
cat deps/models/<alias>
```

Study the structure: how sub-models are declared, how parts are placed, color choices, coordinate conventions.

---

## Phase 2: Proposal & User Confirmation

Before writing any model code, present a clear proposal to the user:

- **What you'll build:** brief description of the model
- **Key parts:** which bricks/pieces you plan to use
- **Approximate complexity:** simple (few pieces), medium, or complex (many pieces)
- **Color scheme:** which color codes you'll use

**Wait for user confirmation or feedback before proceeding.**

---

## Phase 3: Iterative Model Generation (Max 5 Attempts)

### Step 3a: Select Parts

Search for relevant parts by description:

```bash
cat deps/parts-bom.tsv | grep -i "<part-description-keyword>"
```

Cross-reference with parts used in the reference models from Phase 1.

### Step 3b: Write the Model

Create `generated-model.mpd` following the grammar in `references/ldraw.lark`.

Key conventions:
- Use only color codes from the `COLORS` table
- Position parts using valid LDraw transformation matrices
- Declare sub-models before referencing them
- Avoid floating parts — ensure structural connections
- Avoid impossible intersections — check bounding box dimensions (dim_x, dim_y, dim_z) when placing adjacent parts

### Step 3c: Validate

```bash
python scripts/ldraw-validator.py -g references/ldraw.lark -d scripts/ldraw.db -f generated-model.mpd
```

- **On failure:** Read the error messages carefully, fix the offending lines, fix them, and repeat from Step 3b. Count this as one attempt.
- **On success:** Proceed to Step 3d.

### Step 3d: Annotate

```bash
python scripts/ldraw-annotate-models.py -g references/ldraw.lark --db scripts/ldraw.db -f generated-model.mpd -o .
```

This produces `generated-model.ann.mpd`.

### Step 3e: Inspect Intersections

Open `generated-model.ann.mpd` and look for `⚠️` intersection warnings.

- **Too many warnings:** Warn the user about structural issues and continue to delivery.
- **Acceptable intersections:** Proceed to delivery.

**What counts as "too many":** More than a few unavoidable ⚠️ warnings (e.g., purely decorative overlap).

---

## Phase 4: Delivery

Once the model is valid and intersections are minimized:

1. Present `generated-model.ann.mpd` for download.
2. Briefly summarize:
   - Total parts used
   - Any notable design decisions
   - Remaining (unavoidable) intersection warnings, if any

---

## Failure Handling

If 5 attempts are exhausted without a valid, low-collision model:

- Report what went wrong
- Show the last validation error or intersection summary
- Suggest simplifications the user could approve (fewer parts, simpler geometry, different sub-model breakdown)

---

## Quick Reference

| Script | Purpose |
|---|---|
| `scripts/ldraw-query-db.py` | Query the LDraw SQLite database |
| `scripts/ldraw-validator.py` | Validate `.mpd` syntax and part references |
| `scripts/ldraw-annotate-models.py` | Annotate model with parts metainfo and intersection warnings |
| `scripts/ldraw.db` | SQLite database of parts, models, colors |
| `references/ldraw.lark` | Lark grammar for LDraw format |
| `references/ldraw-specs.md` | Full LDraw format specification |
| `references/ANNOTATED_REFERENCE.md` | Reference for metatags on annotated models |
| `deps/models/` | Source `.mpd` files for reference models |
| `deps/parts-bom.tsv` | Parts catalog BOM for reference |

---

## Tips for Quality Models

- **Study reference models thoroughly** — real LDraw models reveal correct coordinate scales and connection patterns
- **Use bounding box dimensions** to calculate exact part placement and avoid intersections
- **Build bottom-up** — place the base/ground-level parts first, then stack upward
- **Group logically** — use sub-model files (within the `.mpd`) for repeated assemblies like wheels, windows, legs
- **Prefer common parts** — standard bricks, plates, and tiles are more likely to exist in the DB and connect cleanly
