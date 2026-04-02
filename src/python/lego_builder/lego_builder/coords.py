"""
Coordinate system constants and conversions for the LDraw builder.

MENTAL MODEL (read this first):
  - Internally we use stud units (X, Z horizontal) and plate units (Y vertical).
  - Y is positive-up in our system.
  - LDraw's Y axis is INVERTED: negative Y = upward, positive Y = downward.
  - Conversion to LDraw coordinates happens ONLY at export time.
  - Part origins in LDraw sit at the TOP of the brick body (where studs connect).
    The body extends DOWNWARD (positive Y in LDraw).
    Studs extend UPWARD (negative Y in LDraw) by ~4 LDU.

Unit conversions:
  - 1 stud  = 20 LDU  (horizontal, X and Z axes)
  - 1 plate =  8 LDU  (vertical, Y axis)
  - 1 brick =  3 plates = 24 LDU

Stacking:
  - Brick at row N has y_plates = N * 3.
  - In LDraw coords: ly = -(N * 3) * 8 = -N * 24.
  - Row 0: ly = 0. Row 1: ly = -24. Row 2: ly = -48. Etc.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# LDraw Coordinate Constants
# ---------------------------------------------------------------------------

LDU_PER_STUD = 20    # 1 stud = 20 LDU horizontally
LDU_PER_PLATE = 8    # 1 plate = 8 LDU vertically
PLATES_PER_BRICK = 3  # 1 brick height = 3 plate heights


def to_ldraw_coords(x_studs: float, y_plates: float, z_studs: float) -> tuple[float, float, float]:
    """Convert internal (stud, plate, stud) coords to LDraw (LDU, LDU, LDU).

    LDraw Y axis is inverted: negative = up. Our y_plates is positive-up,
    so we negate when converting.
    """
    lx = x_studs * LDU_PER_STUD
    ly = -y_plates * LDU_PER_PLATE  # flip Y: our up is LDraw's negative
    lz = z_studs * LDU_PER_STUD
    return (lx, ly, lz)


# ---------------------------------------------------------------------------
# Rotation Matrices for LDraw
# ---------------------------------------------------------------------------

# LDraw uses a 3x3 rotation matrix written as 9 space-separated values:
#   a b c d e f g h i
# representing the matrix:
#   | a b c |
#   | d e f |
#   | g h i |
#
# For our purposes, walls face one of 4 cardinal directions.
# These matrices rotate a part (which is defined facing "north" = -Z)
# to face the desired direction.

ROTATION_MATRICES: dict[int, str] = {
    0:   "1 0 0 0 1 0 0 0 1",          # no rotation (facing north / -Z)
    # TODO VERIFY: The 90° and 270° matrices need careful validation against
    # actual LDraw convention.  LDraw's coordinate system is left-handed
    # (Y points down), so a "clockwise" rotation when viewed from above
    # (looking down -Y in LDraw = looking down +Y in our system) may have
    # opposite sign conventions from what's expected.
    # If these are wrong, east/west walls will have their bricks placed with
    # the X and Z axes swapped or reflected in the wrong direction, producing
    # one-stud-off shifts that depend on brick width.
    # Cross-check: place a single 1x1 brick at a known corner with rotation
    # 90 and 270 and verify its LDraw output lands at the expected coordinate.
    90:  "0 0 -1 0 1 0 1 0 0",         # 90° CW  (facing east / +X)
    180: "-1 0 0 0 1 0 0 0 -1",        # 180°    (facing south / +Z)
    270: "0 0 1 0 1 0 -1 0 0",         # 270° CW (facing west / -X)
}

# Cardinal direction to rotation angle mapping.
# "north" means the wall's outer face points toward -Z in LDraw.
FACING_TO_ROTATION: dict[str, int] = {
    "north": 0,
    "east":  90,
    "south": 180,
    "west":  270,
}
