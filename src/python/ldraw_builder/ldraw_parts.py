"""
RAG-backed LDraw part resolver.

Queries a ChromaDB index built by ldraw_rag.py and returns structured
PartInfo objects parsed from .chunks.md files.

Chunk file format (parts):
    Name: 3001.dat
    Description: Brick  2 x  4
    Dimensions: 80x28x40 LDU
    Keywords: ...

Chunk file format (models):
    Name: 10002-1.mpd
    Category: Vehicles
    Keywords: ...
    Description: ...
    Difficulty: medium
    Number of parts: 347
    BOM table (markdown with Qty | Description | Color | Dimensions | Name columns)

Dimensions convention (verified from corpus):
    Width × Height × Depth in LDU
    Height always includes stud protrusion (brick=28 LDU, plate=12 LDU).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ── Data type ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PartInfo:
    """
    Structured metadata for a single LDraw part, parsed from a .chunks.md file.

    Dimensions are the part's bounding box in LDU:
      width  — X axis (studs × 20)
      height — Y axis, full bounding height including stud protrusion
               (brick = 28 LDU, plate = 12 LDU)
      depth  — Z axis (studs × 20)
    """
    file:        str   # .dat filename, e.g. "3001.dat"
    description: str   # human-readable name, e.g. "Brick  2 x  4"
    width:       int   # bounding box X in LDU
    height:      int   # bounding box Y in LDU (full, incl. stud)
    depth:       int   # bounding box Z in LDU

    def __str__(self) -> str:
        return f"{self.file} — {self.description} ({self.width}×{self.height}×{self.depth} LDU)"


# ── Chunk file parser ──────────────────────────────────────────────────────────

_RE_NAME = re.compile(r"^Name:\s*(.+)$",                   re.MULTILINE)
_RE_DESC = re.compile(r"^Description:\s*(.+)$",            re.MULTILINE)
_RE_DIMS = re.compile(r"^Dimensions:\s*(\d+)x(\d+)x(\d+)", re.MULTILINE)


def parse_chunk(text: str) -> Optional[PartInfo]:
    """
    Parse a .chunks.md file text into a PartInfo.

    Returns None if any required field (Name, Description, Dimensions) is absent,
    which happens for model-level chunks that don't describe a single part.
    """
    m_name = _RE_NAME.search(text)
    m_desc = _RE_DESC.search(text)
    m_dims = _RE_DIMS.search(text)

    if not (m_name and m_desc and m_dims):
        return None

    return PartInfo(
        file        = m_name.group(1).strip(),
        description = m_desc.group(1).strip(),
        width       = int(m_dims.group(1)),
        height      = int(m_dims.group(2)),
        depth       = int(m_dims.group(3)),
    )


# ── RAG retrieval ──────────────────────────────────────────────────────────────

def find_part(
    query:   str,
    *,
    index:   str = "parts",
    backend: str = "openai",
    db_path: str = "./ldraw_rag_db",
    top_k:   int = 5,
) -> Optional[PartInfo]:
    """
    Find the best-matching LDraw part for a free-text query.

    Searches the ChromaDB index built by ldraw_rag.py and returns the first
    result that parses cleanly into a PartInfo, or None if nothing matched.

    query   — natural-language description, e.g. "red 2x4 brick"
    index   — ChromaDB collection name (default: "parts")
    backend — embedding backend: "openai" or an Ollama model tag
    db_path — path to the ChromaDB database directory
    top_k   — number of candidates to retrieve before picking the best parse
    """
    from ldraw_rag import _get_collection, _retrieve_direct

    col     = _get_collection(index, db_path)
    results = _retrieve_direct(col, query, backend, top_k)

    for r in results:
        info = parse_chunk(r.text)
        if info is not None:
            return info

    return None


def find_parts(
    query:   str,
    *,
    index:   str = "parts",
    backend: str = "openai",
    db_path: str = "./ldraw_rag_db",
    top_k:   int = 5,
) -> list[PartInfo]:
    """
    Find up to top_k matching LDraw parts for a free-text query.

    Returns all successfully parsed results in ranked order.
    Useful when the first hit is not quite right and alternatives are needed.
    """
    from ldraw_rag import _get_collection, _retrieve_direct

    col     = _get_collection(index, db_path)
    results = _retrieve_direct(col, query, backend, top_k)

    return [
        info for r in results
        if (info := parse_chunk(r.text)) is not None
    ]
