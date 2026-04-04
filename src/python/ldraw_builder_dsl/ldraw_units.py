"""
LDraw Unit (LDU) constants and grid helpers.

Key LDraw dimensions (from the official spec):
  1 stud pitch (centre-to-centre)  = 20 LDU
  1 brick body height              = 24 LDU
  1 plate body height              =  8 LDU
  1 stud protrusion height         =  4 LDU

Full bounding heights (body + stud) — what the chunks.md Dimensions field reports
and what matters for stacking calculations:
  1 brick total = 28 LDU  (24 body + 4 stud)
  1 plate total = 12 LDU  ( 8 body + 4 stud)

LDraw coordinate system: right-handed, -Y is "up".
"""

# ── Raw constants ──────────────────────────────────────────────────────────────

STUD_PITCH  = 20   # LDU — horizontal centre-to-centre distance between adjacent studs
BRICK_BODY  = 24   # LDU — brick body height (not counting stud protrusion)
PLATE_BODY  = 8    # LDU — plate body height (not counting stud protrusion)
STUD_HEIGHT = 4    # LDU — stud protrusion above the top face

# Full bounding heights (body + stud) — matches the chunks.md Dimensions field
BRICK_FULL = BRICK_BODY + STUD_HEIGHT   # 28 LDU
PLATE_FULL = PLATE_BODY + STUD_HEIGHT   # 12 LDU

# ── Helpers ────────────────────────────────────────────────────────────────────

def stud(n: float = 1) -> float:
    """Horizontal offset for n studs (n × 20 LDU)."""
    return n * STUD_PITCH


def brick(n: float = 1) -> float:
    """Full height of n bricks including stud (n × 28 LDU)."""
    return n * BRICK_FULL


def plate(n: float = 1) -> float:
    """Full height of n plates including stud (n × 12 LDU)."""
    return n * PLATE_FULL


def ldu(n: float) -> float:
    """Raw LDU value — escape hatch for non-grid-aligned measurements."""
    return float(n)


def grid_pos(stud_x: float, stud_z: float) -> tuple[float, float]:
    """
    Convert stud-grid coordinates to LDU world XZ offsets.

    Example:
        x, z = grid_pos(2, 3)   # 2 studs right, 3 studs forward
    """
    return stud(stud_x), stud(stud_z)
