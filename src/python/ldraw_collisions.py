#!/usr/bin/env python3
"""
LDraw mesh-accurate collision detector.

Extracts triangle geometry from LDraw parts (recursively resolving sub-file
references), then uses FCL (via trimesh) for precise mesh-vs-mesh collision
detection between every pair of top-level pieces.

Pieces whose meshes overlap are reported as collisions.  Because LEGO bricks
connect through geometric interference (studs into tubes, axle pins into
holes, etc.), a well-built model will still show many "collisions."  Use
``--margin`` to set the minimum penetration depth (in LDU) that counts as a
collision; overlaps shallower than this are ignored.  Normal LEGO stud/tube
connections penetrate ~4 LDU, so ``--margin 5`` filters those out and only
reports deeper (likely erroneous) intersections.

Output: JSON to stdout.

Dependencies:  pip install trimesh python-fcl numpy

Usage:
    python ldraw-collisions.py model.ldr --search /path/to/ldraw
    python ldraw-collisions.py model.ldr --search /path/to/ldraw --margin 4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import trimesh
import trimesh.collision


# ── LDraw parsing ────────────────────────────────────────────────────

_file_cache: Dict[str, Dict[str, List[str]]] = {}


def _parse_mpd(text: str) -> Dict[str, List[str]]:
    lines = text.splitlines()
    subs: Dict[str, List[str]] = {}
    cur: Optional[str] = None
    buf: List[str] = []
    saw = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("0") and len(s) > 1 and s[1:2].isspace():
            rest = s[2:].lstrip()
            if rest.upper().startswith("FILE "):
                if cur is not None:
                    subs[cur] = buf
                saw = True
                cur = rest[5:].strip()
                buf = [ln]
                continue
        buf.append(ln)
    if saw and cur is not None:
        subs[cur] = buf
    elif not saw:
        subs["__main__"] = lines
    return subs


def _ensure(path: str) -> None:
    if path not in _file_cache:
        with open(path, encoding="utf-8", errors="replace") as f:
            _file_cache[path] = _parse_mpd(f.read())


def _norm(name: str) -> str:
    return name.strip().replace("\\", "/")


def _expand_search(dirs: List[str]) -> List[str]:
    out, seen = [], set()
    for d in dirs:
        d = os.path.abspath(d)
        for sub in ("", "parts", "p",
                     os.path.join("parts", "s"), os.path.join("p", "s")):
            full = os.path.join(d, sub) if sub else d
            if os.path.isdir(full) and full not in seen:
                seen.add(full); out.append(full)
    return out


def _find(ref: str, search: List[str], base: str) -> Optional[str]:
    ref = _norm(ref).strip("\"'")
    for root in [base] + search:
        for v in (ref, ref.lower(), ref.upper()):
            p = os.path.join(root, v)
            if os.path.isfile(p):
                return os.path.abspath(p)
    return None


def _resolve(src_path: str, ref: str, search: List[str]) -> Optional[Tuple[str, str]]:
    rn = _norm(ref)
    if src_path in _file_cache and rn in _file_cache[src_path]:
        return (src_path, rn)
    disk = _find(rn, search, os.path.dirname(src_path))
    if disk:
        _ensure(disk)
        s = _file_cache[disk]
        e = "__main__" if "__main__" in s else next(iter(s.keys()))
        return (disk, e)
    return None


# ── Triangle extraction ──────────────────────────────────────────────

def _mat4(r9: List[float], t3: List[float]) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = np.array(r9).reshape(3, 3)
    m[:3, 3] = t3
    return m


def _is_stud(ref: str) -> bool:
    """True if *ref* is a stud or anti-stud (stud-group) primitive."""
    base = _norm(ref).rsplit("/", 1)[-1].lower()
    return base.startswith("stud") or base.startswith("stug")


def _extract(
    path: str, entry: str, world: np.ndarray,
    search: List[str], missing: Set[str],
    depth: int = 0, max_depth: int = 999,
    ignore_studs: bool = False,
) -> List[np.ndarray]:
    if depth > max_depth:
        return []
    _ensure(path)
    sub = _file_cache[path]
    if entry not in sub:
        return []
    tris: List[np.ndarray] = []
    for raw in sub[entry]:
        p = raw.strip().split()
        if not p:
            continue
        try:
            lt = int(p[0])
        except ValueError:
            continue

        if lt == 3 and len(p) >= 11:
            pts = np.array([[float(p[i]) for i in r]
                            for r in ((2,3,4),(5,6,7),(8,9,10))])
            w = (world @ np.hstack([pts, np.ones((3,1))]).T).T[:, :3]
            tris.append(w)
        elif lt == 4 and len(p) >= 14:
            pts = np.array([[float(p[i]) for i in r]
                            for r in ((2,3,4),(5,6,7),(8,9,10),(11,12,13))])
            w = (world @ np.hstack([pts, np.ones((4,1))]).T).T[:, :3]
            tris.append(w[[0,1,2]]); tris.append(w[[0,2,3]])
        elif lt == 1 and len(p) >= 15:
            fl = [float(p[i]) for i in range(2, 14)]
            cw = world @ _mat4(fl[3:], fl[:3])
            ref = p[14] if len(p) == 15 else " ".join(p[14:])
            if ignore_studs and _is_stud(ref):
                continue
            t = _resolve(path, ref, search)
            if t is None:
                missing.add(_norm(ref)); continue
            tris.extend(_extract(t[0], t[1], cw, search, missing,
                                 depth+1, max_depth, ignore_studs))
    return tris


def _build_mesh(tris: List[np.ndarray]) -> Optional[trimesh.Trimesh]:
    if not tris:
        return None
    v = np.vstack(tris)
    f = np.arange(len(tris) * 3).reshape(len(tris), 3)
    return trimesh.Trimesh(vertices=v, faces=f, process=False)


# ── Collision detection ──────────────────────────────────────────────

def _penetration_depth(
    mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh,
) -> float:
    """Return the penetration depth between two meshes (positive = overlap).

    Uses convex hulls so that FCL can compute a signed distance (it needs
    watertight convex geometry for penetration depth).  This may slightly
    overestimate depth for concave parts, which is the conservative choice
    for filtering.
    """
    mgr = trimesh.collision.CollisionManager()
    mgr.add_object("a", mesh_a.convex_hull)
    mgr.add_object("b", mesh_b.convex_hull)
    d, _ = mgr.min_distance_internal(return_names=True)
    return -d  # positive when overlapping


# ── Main logic ───────────────────────────────────────────────────────

def run(path: str, subfile: Optional[str], search_dirs: List[str],
        margin: float, ignore_studs: bool = False) -> dict:
    search = _expand_search(search_dirs)
    root = os.path.abspath(path)
    _ensure(root)
    sub = _file_cache[root]

    entry = subfile
    if entry is None:
        entry = "__main__" if "__main__" in sub else next(iter(sub.keys()))
    if entry not in sub:
        return {"error": f"entry '{entry}' not found"}

    missing: Set[str] = set()
    pieces: List[dict] = []
    pid = 0

    for idx, raw in enumerate(sub[entry]):
        p = raw.strip().split()
        if not p:
            continue
        try:
            lt = int(p[0])
        except ValueError:
            continue
        if lt != 1 or len(p) < 15:
            continue

        fl = [float(p[i]) for i in range(2, 14)]
        world = _mat4(fl[3:], fl[:3])
        ref = p[14] if len(p) == 15 else " ".join(p[14:])
        t = _resolve(root, ref, search)
        if t is None:
            missing.add(_norm(ref)); continue

        tris = _extract(t[0], t[1], world, search, missing,
                        ignore_studs=ignore_studs)
        mesh = _build_mesh(tris)
        pid += 1
        pieces.append({"pid": pid, "ref": ref, "line": idx + 1,
                        "tris": len(tris), "mesh": mesh})

    # -- collision detection -------------------------------------------------
    mgr = trimesh.collision.CollisionManager()
    meshes: Dict[int, trimesh.Trimesh] = {}
    for pc in pieces:
        m = pc["mesh"]
        if m is not None and len(m.faces) > 0:
            mgr.add_object(str(pc["pid"]), m)
            meshes[pc["pid"]] = m

    _, raw_pairs = mgr.in_collision_internal(return_names=True)

    # For each colliding pair, compute penetration depth and filter by margin
    pairs = []
    for a_s, b_s in raw_pairs:
        a_id, b_id = int(a_s), int(b_s)
        lo, hi = min(a_id, b_id), max(a_id, b_id)
        depth = _penetration_depth(meshes[lo], meshes[hi])
        if depth > margin:
            pairs.append((lo, hi, depth))

    pairs.sort()

    by_pid = {pc["pid"]: pc for pc in pieces}

    return {
        "model": os.path.basename(path),
        "margin_ldu": margin,
        "ignore_studs": ignore_studs,
        "num_pieces": len(pieces),
        "num_collisions": len(pairs),
        "pieces": [{"pid": pc["pid"], "part": pc["ref"],
                     "line": pc["line"], "triangles": pc["tris"]}
                    for pc in pieces],
        "collisions": [{"pid_a": a, "pid_b": b,
                         "part_a": by_pid[a]["ref"],
                         "part_b": by_pid[b]["ref"],
                         "depth_ldu": round(depth, 2)}
                        for a, b, depth in pairs],
        **({"missing_refs": sorted(missing)} if missing else {}),
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Mesh-accurate LDraw collision detector")
    ap.add_argument("path", help="LDraw file (.ldr/.mpd/.dat)")
    ap.add_argument("--subfile", default=None)
    ap.add_argument("--search", action="append", default=[],
                    help="LDraw library root dir(s)")
    ap.add_argument("--margin", type=float, default=0.1,
                    help="Min penetration depth (LDU) to report as collision "
                         "(default: 0.1).  Normal LEGO connections (studs in "
                         "tubes) penetrate ~ 4 LDU; use --margin 5 to filter "
                         "them and find only construction errors.")
    ap.add_argument("--ignore-studs", action="store_true",
                    help="Strip stud and anti-stud geometry (stud*.dat, "
                         "stug*.dat) from every piece before collision "
                         "testing.  This removes the main source of "
                         "expected overlaps in standard brick connections.")
    args = ap.parse_args()

    result = run(args.path, args.subfile, args.search, args.margin,
                 args.ignore_studs)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()