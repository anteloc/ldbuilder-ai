#!/usr/bin/env python3
"""
LDraw MPD Contact & Collision Detector

Given a pre-parsed MPD model (JSON) and a SQLite database containing
a PART_BBOXES table, detects which physical pieces (.dat parts) are
in contact with each other and flags potential intersections.

Usage:
    python ldraw_contacts.py <model.json> --db <ldraw-info.db> [--eps 5.0] [--intersect-threshold 8.0] [-o output.json]

Importable:
    from ldraw_contacts import detect
    result = detect(model_json_path, db_path, eps=5.0, intersect_threshold=8.0)
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_bboxes(conn: sqlite3.Connection) -> dict:
    """Load PART_BBOXES from a SQLite database into a dict keyed by alias."""
    rows = conn.execute(
        "SELECT alias, min_x, min_y, min_z, max_x, max_y, max_z FROM PART_BBOXES"
    ).fetchall()

    bboxes = {}
    for row in rows:
        alias = row["alias"].strip()
        bboxes[alias] = {
            "min": np.array([row["min_x"], row["min_y"], row["min_z"]], dtype=float),
            "max": np.array([row["max_x"], row["max_y"], row["max_z"]], dtype=float),
        }
    return bboxes


def _load_model(json_path: str) -> dict:
    """Load the pre-parsed MPD JSON."""
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Hierarchy flattening
# ---------------------------------------------------------------------------

def _build_subfile_index(model_data: dict) -> dict:
    """Build a lookup from subfile name -> subfile body.

    Plain .ldr files have no ``0 FILE`` header.  They are treated as a
    single-subfile MPD and indexed under the sentinel key ``__root__``.
    """
    index = {}
    for entry in model_data["model"]:
        sf = entry["subfile"]
        header = sf[0]["header"]
        fname = next((h["file"] for h in header if "file" in h), "__root__")
        index[fname] = sf[1]["body"]
    return index


def _compose_transform(parent: np.ndarray, position: list, matrix: list) -> np.ndarray:
    """Compose a child's position + 3x3 matrix with a parent 4x4 transform."""
    child = np.eye(4)
    child[:3, :3] = np.array(matrix)
    child[:3, 3] = np.array(position)
    return parent @ child


def _flatten(model_data: dict) -> list:
    """
    Walk the subfile hierarchy depth-first.  Every Type-1 line gets a
    sequential pid (1-based).

    Returns a list of dicts ordered by pid:
      - .ldr refs:  {pid, ref, is_part=False}
      - .dat refs:  {pid, ref, is_part=True, world_transform}
    """
    subfile_index = _build_subfile_index(model_data)
    root_header = model_data["model"][0]["subfile"][0]["header"]
    root_name = next((h["file"] for h in root_header if "file" in h), "__root__")

    results = []
    pid_counter = [0]

    def walk(subfile_name: str, parent_transform: np.ndarray):
        for item in subfile_index.get(subfile_name, []):
            if "part" not in item:
                continue

            part = item["part"]
            pid_counter[0] += 1
            pid = pid_counter[0]
            ref = part["file_ref"]
            world_transform = _compose_transform(
                parent_transform, part["position"], part["matrix"]
            )

            if ref.endswith(".dat"):
                results.append({
                    "pid": pid,
                    "ref": ref,
                    "is_part": True,
                    "world_transform": world_transform,
                })
            else:
                results.append({
                    "pid": pid,
                    "ref": ref,
                    "is_part": False,
                })
                walk(ref, world_transform)

    walk(root_name, np.eye(4))
    return results


# ---------------------------------------------------------------------------
# Bounding-volume computation
# ---------------------------------------------------------------------------

_CORNER_SIGNS = np.array([
    [0, 0, 0], [0, 0, 1], [0, 1, 0], [0, 1, 1],
    [1, 0, 0], [1, 0, 1], [1, 1, 0], [1, 1, 1],
], dtype=float)


def _world_aabb(world_transform: np.ndarray, local_bbox: dict) -> dict:
    """
    Transform the 8 local AABB corners into world space and return the
    axis-aligned envelope plus its center.
    """
    mn, mx = local_bbox["min"], local_bbox["max"]
    corners = mn + _CORNER_SIGNS * (mx - mn)
    rot = world_transform[:3, :3]
    trans = world_transform[:3, 3]
    world_corners = (rot @ corners.T).T + trans

    w_min = world_corners.min(axis=0)
    w_max = world_corners.max(axis=0)
    return {"min": w_min, "max": w_max, "center": (w_min + w_max) / 2.0}


# ---------------------------------------------------------------------------
# Contact / collision detection
# ---------------------------------------------------------------------------

def _aabb_overlap(a: dict, b: dict, eps: float) -> float | None:
    """
    Test whether two world AABBs overlap within *eps* tolerance.
    Returns the penetration depth (min-axis real overlap) or None.
    """
    if np.any(np.minimum(a["max"], b["max"]) - np.maximum(a["min"], b["min"]) < -eps):
        return None

    real_overlap = np.minimum(a["max"], b["max"]) - np.maximum(a["min"], b["min"])
    return float(np.min(real_overlap))


def _detect_contacts(instances: list, bboxes: dict,
                     eps: float, intersect_threshold: float) -> list:
    """
    Run pairwise AABB overlap among .dat parts and build the per-piece
    contact lists.
    """
    parts = []
    for inst in instances:
        if not inst["is_part"]:
            continue
        ref = inst["ref"]
        if ref not in bboxes:
            print(f"WARNING: No AABB data for {ref}, skipping", file=sys.stderr)
            continue
        inst["world_aabb"] = _world_aabb(inst["world_transform"], bboxes[ref])
        parts.append(inst)

    contact_map = {inst["pid"]: [] for inst in instances}

    n = len(parts)
    for i in range(n):
        a = parts[i]
        a_aabb = a["world_aabb"]
        for j in range(i + 1, n):
            b = parts[j]
            b_aabb = b["world_aabb"]

            penetration = _aabb_overlap(a_aabb, b_aabb, eps)
            if penetration is None:
                continue

            intersects = penetration > intersect_threshold
            vec_ab = b_aabb["center"] - a_aabb["center"]

            contact_map[a["pid"]].append({
                "pid": b["pid"],
                "ref": b["ref"],
                "vector": {
                    "x": round(float(vec_ab[0]), 4),
                    "y": round(float(vec_ab[1]), 4),
                    "z": round(float(vec_ab[2]), 4),
                },
                "intersects": intersects,
            })
            contact_map[b["pid"]].append({
                "pid": a["pid"],
                "ref": a["ref"],
                "vector": {
                    "x": round(float(-vec_ab[0]), 4),
                    "y": round(float(-vec_ab[1]), 4),
                    "z": round(float(-vec_ab[2]), 4),
                },
                "intersects": intersects,
            })

    return [
        {
            "pid": inst["pid"],
            "ref": inst["ref"],
            "contacts": sorted(contact_map[inst["pid"]], key=lambda c: c["pid"]),
        }
        for inst in instances
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect(model_data: dict, conn: sqlite3.Connection, *,
           eps: float = 5.0, intersect_threshold: float = 8.0) -> dict:
    """
    Detect contacts and potential collisions among parts in an LDraw model.

    Args:
        model_data: Pre-parsed MPD/LDR model data.
        conn:       SQLite connection containing PART_BBOXES table.
        eps:        Contact distance tolerance in LDU.
        intersect_threshold: Penetration depth (LDU) above which
                             intersects is flagged True.

    Returns:
        A dict matching the output schema::

            {
                "input": { "eps", "intersect_threshold" },
                "pieces": [ { "pid", "ref", "contacts": [...] }, ... ]
            }
    """
    bboxes = _load_bboxes(conn)
    instances = _flatten(model_data)
    pieces = _detect_contacts(instances, bboxes, eps, intersect_threshold)

    return {
        "input": {
            "eps": eps,
            "intersect_threshold": intersect_threshold,
        },
        "pieces": pieces,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="LDraw MPD Contact & Collision Detector"
    )
    parser.add_argument("model_json", help="Path to pre-parsed MPD JSON")
    parser.add_argument("--db", required=True,
                        help="Path to SQLite database with PART_BBOXES table")
    parser.add_argument("--eps", type=float, default=5.0,
                        help="Contact distance tolerance in LDU (default: 5.0)")
    parser.add_argument("--intersect-threshold", type=float, default=8.0,
                        help="Penetration depth above which intersects=True "
                             "(default: 8.0)")
    parser.add_argument("-o", "--output", default=None,
                        help="Output JSON path (default: stdout)")

    args = parser.parse_args()

    with sqlite3.connect(args.db) as conn:
        conn.row_factory = sqlite3.Row

        result = detect(
            _load_model(args.model_json),
            conn,
            eps=args.eps,
            intersect_threshold=args.intersect_threshold,
        )

        json_str = json.dumps(result, indent=2)

        if args.output:
            Path(args.output).write_text(json_str, encoding="utf-8")
            print(f"Output written to {args.output}", file=sys.stderr)
        else:
            print(json_str)


if __name__ == "__main__":
    main()