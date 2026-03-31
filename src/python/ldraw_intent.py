#!/usr/bin/env python
"""ldraw_intent.py — Annotate, correct, or interpret INTENT (0 !I) lines in LDraw MPD models.

--annotate (-a): Detect spatial relationships between parts using contact data
                 and write '0 !I Pn [arrow+Pk]*' lines before each type-1 line.

--correct  (-c): Read existing '0 !I' lines and adjust part positions (translation
                 only) so that each declared relationship is geometrically satisfied.

--interpret (-i): Read existing '0 !I' lines and print a human-friendly description
                  of each part's spatial relationships to stdout.

Arrow spec (how Pn is positioned relative to Pk):
  ↑ Pk  Pn is above    Pk  (Pn.y < Pk.y  in LDraw coords, i.e. Y is down)
  ↓ Pk  Pn is below    Pk
  → Pk  Pn is right of Pk
  ← Pk  Pn is left of  Pk
  ↗ Pk  Pn is in front of Pk  (more positive Z)
  ↙ Pk  Pn is behind   Pk     (more negative Z)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

import click
import numpy as np

from ldraw_parser import parse_model_semantic
from ldraw_contacts import detect as detect_contacts
import ldraw_parse_model as lpm


LDRAW_EXTS = {".ldr", ".dat", ".mpd"}

# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def iter_ldraw_files(paths: Iterable[str]) -> Iterable[Path]:
    for p in map(Path, paths):
        if p.is_file():
            yield p.resolve()
        elif p.is_dir():
            yield from (
                f.resolve()
                for f in p.rglob("*")
                if f.is_file() and f.suffix.lower() in LDRAW_EXTS
            )


def configure_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.row_factory = sqlite3.Row


# ─────────────────────────────────────────────────────────────────────────────
# Direction arrow classification
# ─────────────────────────────────────────────────────────────────────────────

def _classify_direction(vec: dict[str, float]) -> str:
    """Map a center-to-center vector (Pn → Pk) to one of 6 intent arrows.

    The arrow describes *how Pn is positioned relative to Pk*, not which way
    the vector points.  LDraw axes: X = right, Y = down, Z = toward viewer.

    vec.y > 0  →  Pk is below Pn  →  Pn is above Pk  →  ↑
    vec.y < 0  →  Pk is above Pn  →  Pn is below Pk  →  ↓
    vec.x > 0  →  Pk is right of Pn → Pn is left    →  ←
    vec.x < 0  →  Pk is left of Pn  → Pn is right   →  →
    vec.z > 0  →  Pk is farther     → Pn is in front →  ↗
    vec.z < 0  →  Pk is closer      → Pn is behind   →  ↙
    """
    x, y, z = vec["x"], vec["y"], vec["z"]
    ax, ay, az = abs(x), abs(y), abs(z)

    if ay >= ax and ay >= az:
        return "↑" if y > 0 else "↓"
    elif ax >= ay and ax >= az:
        return "←" if x > 0 else "→"
    else:
        return "↗" if z > 0 else "↙"


# Human-readable text for each arrow, used by --interpret.
ARROW_TEXT: dict[str, str] = {
    "↑": "on top of",
    "↓": "below",
    "→": "to the right of",
    "←": "to the left of",
    "↗": "in front of",
    "↙": "behind",
}

# ─────────────────────────────────────────────────────────────────────────────
# Bounding-box geometry (used by --correct)
# ─────────────────────────────────────────────────────────────────────────────

# All combinations of (min, max) per axis for the 8 corners of an AABB.
_CORNER_SIGNS = np.array([
    [0, 0, 0], [0, 0, 1], [0, 1, 0], [0, 1, 1],
    [1, 0, 0], [1, 0, 1], [1, 1, 0], [1, 1, 1],
], dtype=float)


def _rotated_corners(rot: np.ndarray, bbox: dict) -> np.ndarray:
    """Transform the 8 local AABB corners by a 3×3 rotation (no translation).
    Returns shape (8, 3) — the corners in the rotated frame at the world origin.
    """
    mn, mx = bbox["min"], bbox["max"]
    corners = mn + _CORNER_SIGNS * (mx - mn)
    return (rot @ corners.T).T


def _world_aabb(position: list[float], rot: np.ndarray, bbox: dict) -> dict:
    """Compute the world AABB for a part placed at *position* with rotation *rot*."""
    corners = _rotated_corners(rot, bbox) + np.array(position)
    return {"min": corners.min(axis=0), "max": corners.max(axis=0)}


# ─────────────────────────────────────────────────────────────────────────────
# Annotate mode
# ─────────────────────────────────────────────────────────────────────────────

class LDrawIntentAnnotator:
    def __init__(self, grammar_contents: str, conn: sqlite3.Connection):
        self.grammar_contents = grammar_contents
        self.conn = conn

    def process(self, model: Path) -> str:
        model_contents = model.read_text(encoding="utf-8")
        sem_tree = parse_model_semantic(model_contents, self.grammar_contents)
        contacts = detect_contacts(sem_tree, self.conn)

        # pid (int) → list of contact dicts {"pid", "vector", "intersects"}
        contacts_idx = {p["pid"]: p["contacts"] for p in contacts.get("pieces", [])}

        mpdModel = lpm.MPDModel(sem_tree)

        for subModel in mpdModel.subModels:
            for partRef in subModel.partRefs:
                self._annotate_part(partRef, subModel, mpdModel, contacts_idx)

        return str(mpdModel)

    def _annotate_part(self, partRef: lpm.PartRef, subModel: lpm.SubModel,
                       mpdModel: lpm.MPDModel, contacts_idx: dict) -> None:
        fr = partRef.fileRef
        pid = f"P{fr.globalOrdinal}"
        part_contacts = contacts_idx.get(fr.globalOrdinal, [])

        relations = [
            (_classify_direction(c["vector"]), f"P{c['pid']}")
            for c in part_contacts
        ]

        mpdModel.setPartIntentMeta(partRef, lpm.PartIntentMeta(pid=pid, relations=relations), subModel)


# ─────────────────────────────────────────────────────────────────────────────
# Correct mode
# ─────────────────────────────────────────────────────────────────────────────

class LDrawIntentCorrector:
    def __init__(self, grammar_contents: str, conn: sqlite3.Connection):
        self.grammar_contents = grammar_contents
        self.conn = conn
        self.bboxes = self._load_bboxes()

    def _load_bboxes(self) -> dict:
        """Load PART_BBOXES indexed by both original and sanitized lowercase alias."""
        rows = self.conn.execute(
            "SELECT alias, min_x, min_y, min_z, max_x, max_y, max_z FROM PART_BBOXES"
        ).fetchall()

        bboxes: dict = {}
        for row in rows:
            alias = row["alias"].strip()
            bbox = {
                "min": np.array([row["min_x"], row["min_y"], row["min_z"]], dtype=float),
                "max": np.array([row["max_x"], row["max_y"], row["max_z"]], dtype=float),
            }
            bboxes[alias] = bbox
            # also index by sanitized lowercase for case-insensitive lookups
            sanitized = alias.replace("\\", "/").replace("//", "/").lower()
            bboxes.setdefault(sanitized, bbox)

        return bboxes

    def _bbox_for(self, alias: str) -> dict | None:
        if alias in self.bboxes:
            return self.bboxes[alias]
        sanitized = alias.replace("\\", "/").replace("//", "/").lower()
        return self.bboxes.get(sanitized)

    def process(self, model: Path) -> str:
        model_contents = model.read_text(encoding="utf-8")
        sem_tree = parse_model_semantic(model_contents, self.grammar_contents)
        mpdModel = lpm.MPDModel(sem_tree)

        # "P3" → PartRef for resolving intent references across all submodels
        pid_lookup: dict[str, lpm.PartRef] = {
            f"P{pr.fileRef.globalOrdinal}": pr
            for sm in mpdModel.subModels
            for pr in sm.partRefs
        }

        for sm in mpdModel.subModels:
            for pr in sm.partRefs:
                if not hasattr(pr, "partIntentMeta"):
                    continue
                self._correct_part(pr, pid_lookup)

        return str(mpdModel)

    def _correct_part(self, partRef: lpm.PartRef,
                      pid_lookup: dict[str, lpm.PartRef]) -> None:
        intent = partRef.partIntentMeta
        fr = partRef.fileRef

        pn_bbox = self._bbox_for(fr.ref)
        if pn_bbox is None:
            click.echo(f"Warning: no bbox for '{fr.ref}', skipping", err=True)
            return

        pn_rot = np.array(fr.matrix)
        # Rotation-only corners (at origin). Adding pos gives the world corners.
        # This is computed once; each arrow modifies only one axis of pos.
        pn_corners = _rotated_corners(pn_rot, pn_bbox)  # (8, 3)

        pos = list(fr.position)  # mutable copy — we solve for the translation

        for arrow, pk_pid in intent.relations:
            pk_ref = pid_lookup.get(pk_pid)
            if pk_ref is None:
                click.echo(f"Warning: '{pk_pid}' not found, skipping relation", err=True)
                continue

            pk_fr = pk_ref.fileRef
            pk_bbox = self._bbox_for(pk_fr.ref)
            if pk_bbox is None:
                click.echo(f"Warning: no bbox for '{pk_fr.ref}', skipping relation", err=True)
                continue

            pk_wabb = _world_aabb(pk_fr.position, np.array(pk_fr.matrix), pk_bbox)

            # For each arrow: find the axis to adjust and the touching-face formula.
            # pn_corners are in rotated-local frame at origin, so:
            #   world_corner.axis = pn_corners[:, axis] + pos[axis]
            # Solve for pos[axis] so that Pn's face exactly meets Pk's opposite face.
            if arrow == "↑":
                # Pn above Pk: Pn's bottom (+Y) face touches Pk's top (−Y) face
                pos[1] = float(pk_wabb["min"][1]) - float(pn_corners[:, 1].max())
            elif arrow == "↓":
                # Pn below Pk: Pn's top (−Y) face touches Pk's bottom (+Y) face
                pos[1] = float(pk_wabb["max"][1]) - float(pn_corners[:, 1].min())
            elif arrow == "→":
                # Pn right of Pk: Pn's left (−X) face touches Pk's right (+X) face
                pos[0] = float(pk_wabb["max"][0]) - float(pn_corners[:, 0].min())
            elif arrow == "←":
                # Pn left of Pk: Pn's right (+X) face touches Pk's left (−X) face
                pos[0] = float(pk_wabb["min"][0]) - float(pn_corners[:, 0].max())
            elif arrow == "↗":
                # Pn in front of Pk: Pn's back (+Z) face touches Pk's front (−Z) face
                pos[2] = float(pk_wabb["min"][2]) - float(pn_corners[:, 2].max())
            elif arrow == "↙":
                # Pn behind Pk: Pn's front (−Z) face touches Pk's back (+Z) face
                pos[2] = float(pk_wabb["max"][2]) - float(pn_corners[:, 2].min())

        fr.position = [round(v) for v in pos]


# ─────────────────────────────────────────────────────────────────────────────
# Interpret mode
# ─────────────────────────────────────────────────────────────────────────────

class LDrawIntentInterpreter:
    def __init__(self, grammar_contents: str):
        self.grammar_contents = grammar_contents

    def process(self, model: Path) -> str:
        model_contents = model.read_text(encoding="utf-8")
        sem_tree = parse_model_semantic(model_contents, self.grammar_contents)
        mpdModel = lpm.MPDModel(sem_tree)

        lines: list[str] = [f"=== {model.name} ==="]

        for sm in mpdModel.subModels:
            if len(mpdModel.subModels) > 1:
                lines.append(f"\n--- Submodel: {sm.subFile.header.file.name} ---")

            for pr in sm.partRefs:
                pid = f"P{pr.fileRef.globalOrdinal}"

                if not hasattr(pr, "partIntentMeta") or not pr.partIntentMeta.relations:
                    lines.append(f"{pid} ({pr.fileRef.ref}): no declared relations")
                    continue

                rel_phrases = [
                    f"{ARROW_TEXT.get(arrow, arrow)} {pk}"
                    for arrow, pk in pr.partIntentMeta.relations
                ]
                lines.append(f"{pid} ({pr.fileRef.ref}): is {', '.join(rel_phrases)}")

        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "-f", "--filepath",
    type=click.Path(file_okay=True, dir_okay=True, readable=True, exists=True, resolve_path=True),
    required=True,
    help="Input LDraw model file or directory (recursive).",
)
@click.option(
    "-o", "--output",
    type=click.Path(file_okay=False, dir_okay=True, writable=True, resolve_path=True),
    default=None,
    help="Output directory. Files are written with the same name as the originals. Required for -a and -c.",
)
@click.option(
    "-g", "--grammar",
    type=click.Path(file_okay=True, dir_okay=False, readable=True, exists=True, resolve_path=True),
    envvar="LDRAW_GRAMMAR",
    required=True,
    help="Lark grammar file for parsing LDraw models.",
)
@click.option(
    "-d", "--db",
    type=click.Path(file_okay=True, dir_okay=False, readable=True, exists=True, resolve_path=True),
    default=None,
    help="SQLite DB file containing PART_BBOXES table. Required for -a and -c.",
)
@click.option("-a", "--annotate", "mode", flag_value="annotate",
    help="Detect spatial relationships and write 0 !I annotations.",
)
@click.option("-c", "--correct", "mode", flag_value="correct",
    help="Read existing 0 !I annotations and adjust part positions to satisfy them.",
)
@click.option("-i", "--interpret", "mode", flag_value="interpret",
    help="Read existing 0 !I annotations and print a human-friendly description to stdout.",
)
@click.option(
    "--verbose/--quiet", default=False, show_default=True,
    help="Print per-file progress messages.",
)
def main(filepath: str, output: str | None, grammar: str, db: str | None,
         mode: str | None, verbose: bool) -> None:
    """Annotate, correct, or interpret INTENT (0 !I) lines in LDraw MPD models.

    \b
    Examples:
      # Annotate a model directory
      python ldraw_intent.py -a -f models/ -o annotated/ -g ldraw.lark -d ldraw-info.db

    \b
      # Correct positions in an annotated model
      python ldraw_intent.py -c -f annotated/ -o corrected/ -g ldraw.lark -d ldraw-info.db

    \b
      # Print human-friendly interpretation (no --output or --db needed)
      python ldraw_intent.py -i -f annotated/model.mpd -g ldraw.lark
    """
    if mode is None:
        raise click.UsageError("Specify one of --annotate (-a), --correct (-c), or --interpret (-i).")

    if mode in ("annotate", "correct"):
        if output is None:
            raise click.UsageError("--output / -o is required for --annotate and --correct.")
        if db is None:
            raise click.UsageError("--db / -d is required for --annotate and --correct.")

    grammar_contents = Path(grammar).read_text(encoding="utf-8")
    files = list(iter_ldraw_files([filepath]))

    if mode == "interpret":
        interpreter = LDrawIntentInterpreter(grammar_contents)
        for model_path in files:
            try:
                click.echo(interpreter.process(model_path))
            except Exception as e:
                click.echo(f"Error processing '{model_path.name}': {e}", err=True)
        return

    assert output is not None and db is not None  # guaranteed by earlier UsageError checks

    p_output = Path(output)
    p_output.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        configure_sqlite(conn)

        processor: LDrawIntentAnnotator | LDrawIntentCorrector = (
            LDrawIntentAnnotator(grammar_contents, conn)
            if mode == "annotate"
            else LDrawIntentCorrector(grammar_contents, conn)
        )

        for model_path in files:
            try:
                result = processor.process(model_path)
                out_path = p_output / model_path.name
                out_path.write_text(result, encoding="utf-8")
                if verbose:
                    click.echo(f"Done: {model_path.name}", err=True)
            except Exception as e:
                click.echo(f"Error processing '{model_path.name}': {e}", err=True)


if __name__ == "__main__":
    main()
