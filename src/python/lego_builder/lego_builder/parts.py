"""
Part catalog: PartType enum, Part definitions, Color constants, and lookup.

This module contains the complete catalog of available LEGO parts and
the greedy fill order used by wall/roof tiling algorithms.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Part Catalog
# ---------------------------------------------------------------------------

# PartType enum: specific part identifiers. Values match catalog keys.
# Named as TYPE_WIDTHxDEPTH (bricks/plates) or TYPE_WIDTHxDEPTHxHEIGHT
# (windows/doors where height matters).
#
# Future: find_part() will accept PartType + semantic description + color
# for RAG-based lookup. For now, it does exact match on PartType.

class PartType(Enum):
    """Enumeration of available LEGO parts.

    Naming convention:
      BRICK_DxW     — standard brick, D studs deep, W studs wide
      PLATE_DxW     — standard plate, D studs deep, W studs wide
      WINDOW_DxWxH  — window (complete), D deep, W wide, H high (in bricks)
      DOOR_DxWxH    — door frame, D deep, W wide, H high (in bricks)
      SLOPE_DxW     — 45° slope brick
    """
    # --- Bricks (height = 3 plates = 1 brick) ---
    BRICK_1X1 = "brick_1x1"
    BRICK_1X2 = "brick_1x2"
    BRICK_1X3 = "brick_1x3"
    BRICK_1X4 = "brick_1x4"
    BRICK_2X2 = "brick_2x2"
    BRICK_2X3 = "brick_2x3"
    BRICK_2X4 = "brick_2x4"

    # --- Plates (height = 1 plate) ---
    PLATE_1X1 = "plate_1x1"
    PLATE_1X2 = "plate_1x2"
    PLATE_1X4 = "plate_1x4"
    PLATE_2X2 = "plate_2x2"
    PLATE_2X3 = "plate_2x3"
    PLATE_2X4 = "plate_2x4"

    # --- Windows (complete assemblies with glass) ---
    WINDOW_1X2X2 = "window_1x2x2"
    WINDOW_1X2X3 = "window_1x2x3"
    WINDOW_1X4X3 = "window_1x4x3"

    # --- Doors ---
    DOOR_1X4X6 = "door_1x4x6"

    # --- Slopes (45°, for future roof use) ---
    SLOPE_2X2 = "slope_2x2"
    SLOPE_2X4 = "slope_2x4"


@dataclass(frozen=True)
class Part:
    """A LEGO part definition with its LDraw filename and dimensions.

    Dimensions are in internal units:
      width_studs  — along the part's local X axis (in studs)
      depth_studs  — along the part's local Z axis (in studs)
      height_plates — along Y axis (in plates: brick=3, plate=1)
    """
    filename: str         # LDraw part file, e.g. "3001.dat"
    description: str      # human-readable, e.g. "Brick 2x4"
    width_studs: int      # local X dimension in studs
    depth_studs: int      # local Z dimension in studs
    height_plates: int    # Y dimension in plates (1 brick = 3 plates)


# Part catalog: maps PartType enum values to Part definitions.
# Dimensions verified against LDraw parts-bom.tsv:
#   3001.dat Brick 2x4: 80x28x40 LDU → 4x3plates x2 studs
#   3020.dat Plate 2x4: 80x12x40 LDU → 4x1plate x2 studs
#   etc.

PARTS: dict[str, Part] = {
    # Bricks (height = 3 plates)
    "brick_1x1": Part("3005.dat",  "Brick 1x1",  width_studs=1, depth_studs=1, height_plates=3),
    "brick_1x2": Part("3004.dat",  "Brick 1x2",  width_studs=2, depth_studs=1, height_plates=3),
    "brick_1x3": Part("3622.dat",  "Brick 1x3",  width_studs=3, depth_studs=1, height_plates=3),
    "brick_1x4": Part("3010.dat",  "Brick 1x4",  width_studs=4, depth_studs=1, height_plates=3),
    "brick_2x2": Part("3003.dat",  "Brick 2x2",  width_studs=2, depth_studs=2, height_plates=3),
    "brick_2x3": Part("3002.dat",  "Brick 2x3",  width_studs=3, depth_studs=2, height_plates=3),
    "brick_2x4": Part("3001.dat",  "Brick 2x4",  width_studs=4, depth_studs=2, height_plates=3),

    # Plates (height = 1 plate)
    "plate_1x1": Part("3024.dat",  "Plate 1x1",  width_studs=1, depth_studs=1, height_plates=1),
    "plate_1x2": Part("3023.dat",  "Plate 1x2",  width_studs=2, depth_studs=1, height_plates=1),
    "plate_1x4": Part("3710.dat",  "Plate 1x4",  width_studs=4, depth_studs=1, height_plates=1),
    "plate_2x2": Part("3022.dat",  "Plate 2x2",  width_studs=2, depth_studs=2, height_plates=1),
    "plate_2x3": Part("3021.dat",  "Plate 2x3",  width_studs=3, depth_studs=2, height_plates=1),
    "plate_2x4": Part("3020.dat",  "Plate 2x4",  width_studs=4, depth_studs=2, height_plates=1),

    # Windows — "complete" assemblies (frame + glass in one part)
    # 60592c01: Window 1x2x2 without sill, with glass. 40x52x20 LDU → 2w x 2h(bricks) x 1d
    "window_1x2x2": Part("60592c01.dat", "Window 1x2x2", width_studs=2, depth_studs=1, height_plates=6),
    # 60593c01: Window 1x2x3 without sill, with glass. 40x76x20 LDU → 2w x 3h(bricks) x 1d
    "window_1x2x3": Part("60593c01.dat", "Window 1x2x3", width_studs=2, depth_studs=1, height_plates=9),
    # 60594 + glass: Window 1x4x3. 80x76x20 LDU → 4w x 3h(bricks) x 1d
    # Using the frame only; glass can be added later
    "window_1x4x3": Part("60594.dat",    "Window 1x4x3", width_studs=4, depth_studs=1, height_plates=9),

    # Doors
    # 60596: Door frame 1x4x6. 80x148x20 LDU → 4w x ~6h(bricks) x 1d
    "door_1x4x6": Part("60596.dat", "Door Frame 1x4x6", width_studs=4, depth_studs=1, height_plates=18),

    # Slopes (45°, for future roof use)
    # 3039: Slope 45° 2x2. 40x28x40 LDU
    "slope_2x2": Part("3039.dat",  "Slope 45 2x2",  width_studs=2, depth_studs=2, height_plates=3),
    # 3037: Slope 45° 2x4. 80x28x40 LDU
    "slope_2x4": Part("3037.dat",  "Slope 45 2x4",  width_studs=4, depth_studs=2, height_plates=3),
}


# Greedy fill order for brick tiling: widest first, 1x1 as last resort.
# Used by Wall._tile_solid_regions and GableRoof slope/gable builders.
FILL_BRICKS: list[Part] = [
    PARTS["brick_2x4"],  # 4 studs wide along face
    PARTS["brick_2x3"],  # 3 studs
    PARTS["brick_2x2"],  # 2 studs, 2 deep
    PARTS["brick_1x4"],  # 4 studs, 1 deep (gap filler)
    PARTS["brick_1x2"],  # 2 studs, 1 deep
    PARTS["brick_1x1"],  # last resort
]


def find_part(
    part_type: PartType,
    description: str = "",
    color: str = "",
) -> Part:
    """Look up a part by its PartType enum value.

    Current implementation: exact match on part_type, ignores description/color.
    Future (RAG): description and color will be used for semantic search
    within the matched part_type category.

    Args:
        part_type: Exact part identifier (required).
        description: Semantic description for future RAG filtering.
        color: Semantic color hint for future RAG filtering.

    Returns:
        The matching Part definition.

    Raises:
        BuilderError: If part_type is not found in catalog.
    """
    from .core import BuilderError
    key = part_type.value
    if key not in PARTS:
        raise BuilderError(f"Part '{key}' not found in catalog. "
                           f"Available: {list(PARTS.keys())}")
    return PARTS[key]


# ---------------------------------------------------------------------------
# LDraw Color Constants (commonly used subset)
# ---------------------------------------------------------------------------

# LDraw color codes. Full list in ldraw.db COLORS table.
# These are the most useful for building models.

class Color:
    """Common LDraw color codes as named constants.

    Usage: Color.RED, Color.WHITE, etc.
    The LLM can also use raw integers if needed.
    """
    BLACK = 0
    BLUE = 1
    GREEN = 2
    RED = 4
    BROWN = 6
    LIGHT_GREY = 7
    DARK_GREY = 8
    LIGHT_BLUE = 9
    BRIGHT_GREEN = 10
    YELLOW = 14
    WHITE = 15
    TAN = 19
    LIGHT_VIOLET = 20
    DARK_BLUE = 272
    DARK_RED = 320
    DARK_TAN = 28
    DARK_GREEN = 288
    REDDISH_BROWN = 70
    SAND_GREEN = 378
    DARK_BLUISH_GREY = 72
    LIGHT_BLUISH_GREY = 71
    TRANS_CLEAR = 47
    TRANS_LIGHT_BLUE = 43
