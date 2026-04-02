"""
lego_builder.py — A Python-embedded DSL for generating LEGO LDraw models.

An LLM generates Python scripts using this library's primitives (box, wall,
floor_slab, column, group, place, attach, gable_roof) and the library
handles all geometric correctness, brick tiling, and LDraw export.

Architecture:
  - Everything uses stud units (X, Z) and plate units (Y) internally.
  - LDraw coordinate conversion happens only at export time.
  - Walls store a boolean grid; brick tiling is computed at export.
  - Each class has a to_placements() method returning BrickPlacement lists.
  - Scene collects all placements and writes a single .mpd file.

LDraw coordinate system (for reference, used only in export):
  - 1 stud  = 20 LDU  (horizontal, X and Z axes)
  - 1 plate =  8 LDU  (vertical, Y axis)
  - 1 brick =  3 plates = 24 LDU
  - Y axis is inverted: negative Y = upward
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Section 1: LDraw Coordinate Constants
# ---------------------------------------------------------------------------

# Conversion factors from our internal units to LDraw Drawing Units (LDU).
LDU_PER_STUD = 20    # 1 stud = 20 LDU horizontally
LDU_PER_PLATE = 8    # 1 plate = 8 LDU vertically
PLATES_PER_BRICK = 3  # 1 brick height = 3 plate heights


def to_ldraw_coords(x_studs: float, y_plates: float, z_studs: float) -> tuple[float, float, float]:
    """Convert internal (stud, plate, stud) coords to LDraw (LDU, LDU, LDU).

    LDraw Y axis is inverted: negative = up. Our y_plates is positive-up,
    so we negate when converting.
    """
    # TODO BUG: This function converts corner-based internal coordinates
    # (where x,z refer to the brick's minimum corner) straight to LDU, but
    # LDraw parts have their origin at the CENTER of the part (on X and Z).
    # This means the LDraw position should be offset by +half the part's
    # width in X and +half the part's depth in Z (in stud units, then
    # multiplied by LDU_PER_STUD).  Without this correction every brick is
    # placed half-a-brick off from where it should be.
    # Because the shift depends on the part's dimensions AND its rotation,
    # this fix belongs in to_ldraw_line() (which knows the part and rotation),
    # not here.  See the companion TODO in BrickPlacement.to_ldraw_line().
    lx = x_studs * LDU_PER_STUD
    ly = -y_plates * LDU_PER_PLATE  # flip Y: our up is LDraw's negative
    lz = z_studs * LDU_PER_STUD
    return (lx, ly, lz)


# ---------------------------------------------------------------------------
# Section 2: Rotation Matrices for LDraw
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


# ---------------------------------------------------------------------------
# Section 3: Part Catalog
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
      BRICK_WxD     — standard brick, W studs wide, D studs deep
      PLATE_WxD     — standard plate, W studs wide, D studs deep
      WINDOW_WxDxH  — window (complete), W wide, D deep, H high (in bricks)
      DOOR_WxDxH    — door frame, W wide, D deep, H high (in bricks)
      SLOPE_WxD     — 45° slope brick

    # TODO VERIFY: The naming says "WxD" but BRICK_1X2 has width_studs=2,
    # depth_studs=1 in the catalog — so the name actually reads as DxW.
    # This is confusing and may lead the LLM to pick the wrong part size.
    # The ACTUAL Part dimensions in the catalog are correct per LDraw, but
    # the enum names are misleading.  Either rename enums to match WxD
    # (BRICK_2X1) or document that the first number is depth, not width.
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
    key = part_type.value
    if key not in PARTS:
        raise BuilderError(f"Part '{key}' not found in catalog. "
                           f"Available: {list(PARTS.keys())}")
    return PARTS[key]


# ---------------------------------------------------------------------------
# Section 4: LDraw Color Constants (commonly used subset)
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


# ---------------------------------------------------------------------------
# Section 5: Core Data Classes
# ---------------------------------------------------------------------------

class BuilderError(Exception):
    """Error with an LLM-readable message.

    Messages are written to be actionable: they say what went wrong,
    what the constraints are, and implicitly what to do instead.
    """
    pass


@dataclass(frozen=True)
class BrickPlacement:
    """A single placed brick/part in the model.

    Coordinates are in internal units (studs for X/Z, plates for Y).
    Conversion to LDraw happens only in Scene.export().

    Attributes:
        part: The Part definition (contains LDraw filename + dimensions).
        x: Position along X axis in studs.
        y: Position along Y axis in plates (positive = up).
        z: Position along Z axis in studs.
        rotation: Rotation angle in degrees (0, 90, 180, 270).
        color: LDraw color code.
        comment: Annotation for LDraw comment line (e.g. "wall_north row_3").
    """
    part: Part
    x: float
    y: float  # in plates, positive = up
    z: float
    rotation: int = 0
    color: int = Color.WHITE
    comment: str = ""

    def offset_by(self, x: float, y: float, z: float) -> "BrickPlacement":
        """Return a copy of this placement shifted by (x, y, z)."""
        return BrickPlacement(self.part, self.x + x, self.y + y, self.z + z,
                              self.rotation, self.color, self.comment)

    def to_ldraw_line(self) -> str:
        """Convert this placement to an LDraw type-1 line with optional comment.

        Returns a string like:
            0 // wall_north row_3
            1 15 0 -24 0 1 0 0 0 1 0 0 0 1 3001.dat
        """
        rotation = self.rotation % 360
        if rotation in (90, 270):
            adjusted_x = self.x + self.part.depth_studs / 2
            adjusted_z = self.z + self.part.width_studs / 2
        else:
            adjusted_x = self.x + self.part.width_studs / 2
            adjusted_z = self.z + self.part.depth_studs / 2

        lx, ly, lz = to_ldraw_coords(adjusted_x, self.y, adjusted_z)
        matrix = ROTATION_MATRICES.get(rotation, ROTATION_MATRICES[0])

        lines = []
        if self.comment:
            lines.append(f"0 // {self.comment}")
        lines.append(f"1 {self.color} {lx:.1f} {ly:.1f} {lz:.1f} {matrix} {self.part.filename}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 6: Wall Class
# ---------------------------------------------------------------------------
#
# A Wall is a rectangular surface of bricks, defined by:
#   - length (studs along its face)
#   - height (brick rows)
#   - facing (north/south/east/west)
#
# Internally, a wall stores a 2D boolean grid sized in studs × plates.
# True = solid (will be filled with bricks). False = opening (empty).
#
# The wall uses 2xN bricks oriented with their depth (2 studs) going
# INTO the wall, and their width along the wall face. This gives
# structurally realistic walls that are 2 studs (1 brick) deep.
#
# At export time, the solid regions are tiled with bricks using a greedy
# algorithm with running bond (each row offset by half a brick width).

WALL_DEPTH_STUDS = 2  # all walls are 1 brick (2 studs) deep


class Wall:
    """A rectangular brick wall with openings and inserted parts.

    The wall lives in its own local coordinate space:
      - X axis: along the wall face, 0 = left end, length = right end (studs)
      - Y axis: up from the wall base, 0 = bottom (plates)
      - The wall is WALL_DEPTH_STUDS (2) deep in the Z direction.

    Global positioning (where the wall sits in the scene) is handled by
    its parent Box or Group, not by the wall itself.

    Attributes:
        name: Identifier for LDraw comments (e.g. "wall_north").
        length: Wall length in studs.
        height_bricks: Wall height in brick rows.
        height_plates: Wall height in plates (= height_bricks * 3).
        facing: Cardinal direction string.
        color: Default LDraw color code for bricks.
        fill_part: Default part key for filling solid regions.
        grid: 2D boolean array [x_stud][y_plate]. True = solid.
        inserts: List of (part, x_stud, y_plate, color) for windows/doors.
        ledges: List of (y_plate, overhang, color, part_key) tuples.
    """

    def __init__(
        self,
        length: int,
        height: int,
        facing: str,
        color: int = Color.WHITE,
        fill_part: str = PartType.BRICK_2X4.value,
        name: str = "",
    ):
        """Create a wall. All cells start as solid (True).

        Args:
            length: Wall length in studs (along the face).
            height: Wall height in brick rows (1 row = 3 plates).
            facing: "north", "south", "east", or "west".
            color: LDraw color code for the wall bricks.
            fill_part: Part catalog key for the fill brick.
            name: Identifier used in LDraw comments.
        """
        if facing not in FACING_TO_ROTATION:
            raise BuilderError(
                f"Invalid facing '{facing}'. Must be one of: "
                f"{list(FACING_TO_ROTATION.keys())}"
            )
        if length < 1:
            raise BuilderError(f"Wall length must be >= 1, got {length}")
        if height < 1:
            raise BuilderError(f"Wall height must be >= 1, got {height}")

        self.name = name or f"wall_{facing}"
        self.length = length
        self.height_bricks = height
        self.height_plates = height * PLATES_PER_BRICK
        self.facing = facing
        self.color = color
        self.fill_part = fill_part

        # Boolean grid: grid[x][y] where x=stud position along face,
        # y=plate position from base. True = solid, False = opening.
        self.grid: list[list[bool]] = [
            [True for _ in range(self.height_plates)]
            for _ in range(self.length)
        ]

        # Inserted parts (windows, doors) placed in openings.
        self.inserts: list[tuple[Part, int, int, int]] = []

        # Ledges: (y_plate, overhang_studs, color, part_key)
        self.ledges: list[tuple[int, int, int, str]] = []

    # --- Modification Methods ---

    def opening(self, x: int, y: int, width: int, height: int) -> None:
        """Cut a rectangular opening in the wall (for windows, doors, etc.).

        Clears grid cells to False in the specified rectangle.

        Args:
            x: Left edge of opening in studs from wall's left end.
            y: Bottom edge in brick rows from wall base.
            width: Opening width in studs.
            height: Opening height in brick rows.

        Raises:
            BuilderError: If the opening extends beyond wall bounds.
        """
        y_plates = y * PLATES_PER_BRICK
        h_plates = height * PLATES_PER_BRICK

        if x < 0 or x + width > self.length:
            raise BuilderError(
                f"Opening x={x}, width={width} exceeds wall '{self.name}' "
                f"length of {self.length} studs. "
                f"Opening would span studs {x}..{x + width - 1}, "
                f"but wall spans 0..{self.length - 1}."
            )
        if y < 0 or y_plates + h_plates > self.height_plates:
            raise BuilderError(
                f"Opening y={y}, height={height} exceeds wall '{self.name}' "
                f"height of {self.height_bricks} rows. "
                f"Opening would span rows {y}..{y + height - 1}, "
                f"but wall spans 0..{self.height_bricks - 1}."
            )

        for gx in range(x, x + width):
            for gy in range(y_plates, y_plates + h_plates):
                self.grid[gx][gy] = False

    def insert(self, part_type: PartType, x: int, y: int,
               color: int | None = None) -> None:
        """Place a part (window, door) into an existing opening.

        Args:
            part_type: The PartType enum value for the part to insert.
            x: Left edge in studs from wall's left end.
            y: Bottom edge in brick rows from wall base.
            color: LDraw color code. None = auto (TRANS_CLEAR for windows,
                   DARK_BLUISH_GREY for doors).

        Raises:
            BuilderError: If part not found or no opening at position.
        """
        part = find_part(part_type)
        y_plates = y * PLATES_PER_BRICK

        # Verify the full part footprint falls within an opening.
        # Checks every (stud, plate) cell the part occupies, not just the corner.
        if any(
            self.grid[cx][cy]
            for cx in range(x, x + part.width_studs)
            for cy in range(y_plates, y_plates + part.height_plates)
            if cx < self.length and cy < self.height_plates
        ):
            raise BuilderError(
                f"No opening for '{part_type.value}' at x={x}, y={y} on wall "
                f"'{self.name}'. Call .opening(x={x}, y={y}, "
                f"width={part.width_studs}, height={part.height_plates // PLATES_PER_BRICK}) first."
            )

        if color is None:
            if "window" in part_type.value:
                color = Color.TRANS_CLEAR
            elif "door" in part_type.value:
                color = Color.DARK_BLUISH_GREY
            else:
                color = self.color

        self.inserts.append((part, x, y_plates, color))

    def window_row(
        self,
        y: int,
        width: int,
        height: int,
        count: int,
        part_type: PartType,
        spacing: str | int = "even",
        color: int | None = None,
    ) -> None:
        """Cut openings and insert windows in a regular horizontal pattern.

        Args:
            y: Bottom edge of windows in brick rows from wall base.
            width: Each window's width in studs.
            height: Each window's height in brick rows.
            count: Number of windows to place.
            part_type: PartType for the window part.
            spacing: "even" to distribute evenly, or int for explicit gap.
            color: LDraw color for the windows. None = auto.

        Raises:
            BuilderError: If windows don't fit in the wall.
        """
        if count < 1:
            raise BuilderError("window_row count must be >= 1")

        # Calculate x positions for each window
        if spacing == "even":
            total_window = count * width
            if total_window > self.length:
                raise BuilderError(
                    f"Cannot fit {count} windows of width {width} "
                    f"(total {total_window} studs) in wall '{self.name}' "
                    f"of length {self.length} studs."
                )
            total_gap = self.length - total_window
            gap = total_gap / (count + 1)
            x_positions = [
                int(round(gap + i * (width + gap)))
                for i in range(count)
            ]
        else:
            gap = int(spacing)
            total_width = count * width + (count - 1) * gap
            if total_width > self.length:
                raise BuilderError(
                    f"Cannot fit {count} windows of width {width} "
                    f"with gap {gap} (total {total_width} studs) "
                    f"in wall '{self.name}' of length {self.length} studs."
                )
            start_x = (self.length - total_width) // 2
            x_positions = [
                start_x + i * (width + gap)
                for i in range(count)
            ]

        for x_pos in x_positions:
            self.opening(x=x_pos, y=y, width=width, height=height)
            self.insert(part_type=part_type, x=x_pos, y=y, color=color)

    def ledge(
        self,
        y: int,
        overhang: int = 1,
        color: int | None = None,
        part_type: PartType = PartType.PLATE_2X4,
    ) -> None:
        """Add an overhanging ledge/cornice at a given row height.

        Args:
            y: Row position in brick rows from wall base.
            overhang: How many studs the ledge projects outward.
            color: LDraw color. None = use wall color.
            part_type: PartType for the ledge plates.
        """
        y_plates = y * PLATES_PER_BRICK
        ledge_color = color if color is not None else self.color
        self.ledges.append((y_plates, overhang, ledge_color, part_type.value))

    # --- Brick Tiling (for export) ---

    def _bond_offset(self, brick_row: int) -> int:
        """Running bond offset in studs for a given brick row.

        Even rows → 0. Odd rows → half the primary brick width.
        """
        primary_width = PARTS[self.fill_part].width_studs
        return (brick_row % 2) * (primary_width // 2)

    def _tile_solid_regions(self, comment_prefix: str = "") -> list[BrickPlacement]:
        """Fill solid grid cells with bricks using a greedy algorithm.

        Uses running bond: even brick-rows start at stud 0, odd brick-rows
        start offset by half the fill brick's width.

        Tries largest bricks first, falls back to smaller ones for gaps.

        Returns:
            List of BrickPlacement in wall-local coordinates.
        """
        placements: list[BrickPlacement] = []

        # Process each brick row (every PLATES_PER_BRICK plate rows)
        for brick_row in range(self.height_bricks):
            y_plate = brick_row * PLATES_PER_BRICK

            bond_offset = self._bond_offset(brick_row)

            # Anchor pattern globally instead of per-row drifting
            x = -bond_offset

            # Running bond: on odd rows, start with a smaller brick to create
            # the offset pattern. Place a brick of bond_offset width first.
            if bond_offset > 0 and self.grid[0][y_plate]:
                # Find a brick that fits the offset width
                primary = PARTS[self.fill_part]

                candidates = [primary] + [b for b in FILL_BRICKS if b != primary]

                for brick in candidates:
                    if brick.width_studs == bond_offset:
                        if all(self.grid[cx][y_plate] for cx in range(bond_offset)):
                            placements.append(BrickPlacement(
                                part=brick,
                                x=0, y=y_plate, z=0,
                                rotation=0, color=self.color,
                                comment=f"{comment_prefix}{self.name} row_{brick_row}",
                            ))
                            x = bond_offset
                            break

            while x < self.length:
                if x < 0:
                    x += 1
                    continue
                if not self.grid[x][y_plate]:
                    x += 1
                    continue

                # Find the widest brick that fits
                placed = False
                primary = PARTS[self.fill_part]

                candidates = [primary] + [b for b in FILL_BRICKS if b != primary]

                for brick in candidates:
                    bw = brick.width_studs
                    if x + bw > self.length:
                        continue

                    # Check all studs this brick would cover are solid
                    brick_height = brick.height_plates

                    # Ensure the brick fits vertically within wall bounds
                    if y_plate + brick_height > self.height_plates:
                        continue
                    
                    # Check full brick volume (width × height), not just 1 plate row
                    if all(
                        self.grid[cx][cy]
                        for cx in range(x, x + bw)
                        for cy in range(y_plate, y_plate + brick_height)
                    ):
                        comment = f"{comment_prefix}{self.name} row_{brick_row}"
                        placements.append(BrickPlacement(
                            part=brick,
                            x=x, y=y_plate, z=0,
                            rotation=0,
                            color=self.color,
                            comment=comment,
                        ))
                        x += bw
                        placed = True
                        break

                if not placed:
                    x += 1  # skip unfillable cell (shouldn't happen)

        return placements

    def _insert_placements(self, comment_prefix: str = "") -> list[BrickPlacement]:
        """Generate BrickPlacements for inserted parts (windows, doors)."""
        placements = []
        for part, x_stud, y_plate, color in self.inserts:
            comment = f"{comment_prefix}{self.name} {part.description}"
            placements.append(BrickPlacement(
                part=part, x=x_stud, y=y_plate, z=0,
                rotation=0, color=color, comment=comment,
            ))
        return placements

    def _ledge_placements(self, comment_prefix: str = "") -> list[BrickPlacement]:
        """Generate BrickPlacements for ledges/cornices.

        Ledges are rows of plates extending outward (negative Z in local space).
        """
        placements = []
        for y_plate, overhang, color, part_key in self.ledges:
            part = PARTS[part_key]
            brick_row = y_plate // PLATES_PER_BRICK
            bond_offset = self._bond_offset(brick_row)
            
            x = -bond_offset
            while x < self.length:
                if x < 0:
                    x += 1
                    continue

                comment = f"{comment_prefix}{self.name} ledge"
                
                if x + part.width_studs <= self.length:
                    placements.append(BrickPlacement(
                        part=part, x=x, y=y_plate, z=-overhang,
                        rotation=0, color=color, comment=comment,
                    ))
                    x += part.width_studs
                else:
                    x += 1
        return placements

    def to_placements(self, comment_prefix: str = "") -> list[BrickPlacement]:
        """Generate all BrickPlacements for this wall.

        Combines brick tiling + inserted parts + ledges.
        All coordinates are in wall-local space.

        Args:
            comment_prefix: Prepended to LDraw comments (e.g. "tier_1 > ").

        Returns:
            Combined list of all placements.
        """
        result = []
        result.extend(self._tile_solid_regions(comment_prefix))
        result.extend(self._insert_placements(comment_prefix))
        result.extend(self._ledge_placements(comment_prefix))
        return result


# ---------------------------------------------------------------------------
# Section 7: Box Class
# ---------------------------------------------------------------------------
#
# A Box is a convenience that creates 4 walls forming a rectangular enclosure.
# It handles wall positioning so the LLM never calculates wall coordinates.
#
# The Box lives in its own local coordinate space:
#   - Origin (0, 0, 0) is at the bottom-left-front corner.
#   - X axis runs east (width), Z axis runs north (depth), Y is up.
#   - The four walls are placed at the edges of the footprint.
#
# Wall layout (viewed from above):
#
#        north wall (length = width)
#      +--------------------------+
#      |                          |
#  west|                          |east
#  wall|   interior (hollow)      |wall
#  (len|                          |(len
#  =dep|                          |=dep
#  th) |                          |th)
#      +--------------------------+
#        south wall (length = width)
#
#   origin (0,0) is at south-west corner


class Box:
    """A rectangular enclosure of 4 walls with named accessors.

    The LLM creates a Box to define a floor's walls, then modifies
    individual walls via .north, .south, .east, .west accessors.

    Attributes:
        name: Identifier for LDraw comments.
        width: East-west dimension in studs.
        depth: North-south dimension in studs.
        height_bricks: Wall height in brick rows.
        color: Default LDraw color for all walls.
        north: The north-facing wall.
        south: The south-facing wall.
        east: The east-facing wall.
        west: The west-facing wall.
    """

    def __init__(
        self,
        width: int,
        depth: int,
        height: int,
        color: int = Color.WHITE,
        fill_part: str = PartType.BRICK_2X4.value,
        name: str = "",
    ):
        """Create a box with 4 walls.

        Args:
            width: East-west dimension in studs.
            depth: North-south dimension in studs.
            height: Wall height in brick rows.
            color: LDraw color code for all walls.
            fill_part: Part catalog key for fill bricks.
            name: Identifier for LDraw comments.
        """
        self.name = name or "box"
        self.width = width
        self.depth = depth
        self.height_bricks = height
        self.height_plates = height * PLATES_PER_BRICK
        self.color = color

        # Create the four walls. North and south run along X (width).
        # East and west run along Z (depth).
        self.north = Wall(
            length=width, height=height, facing="north",
            color=color, fill_part=fill_part,
            name=f"{self.name}_north",
        )
        self.south = Wall(
            length=width, height=height, facing="south",
            color=color, fill_part=fill_part,
            name=f"{self.name}_south",
        )
        self.east = Wall(
            length=depth, height=height, facing="east",
            color=color, fill_part=fill_part,
            name=f"{self.name}_east",
        )
        self.west = Wall(
            length=depth, height=height, facing="west",
            color=color, fill_part=fill_part,
            name=f"{self.name}_west",
        )

    def walls(self) -> list[Wall]:
        """Return all four walls as a list."""
        return [self.north, self.south, self.east, self.west]

    def to_placements(self, comment_prefix: str = "") -> list[BrickPlacement]:
        """Generate BrickPlacements for all four walls, positioned correctly.

        Transforms each wall's local-space placements into the Box's
        local coordinate space. The Box itself may later be transformed
        by a Group or place() call.

        Wall positions in Box-local space:
          - South wall: at z=0, running along X from 0 to width
          - North wall: at z=depth, running along X from 0 to width
          - West wall:  at x=0, running along Z from 0 to depth
          - East wall:  at x=width, running along Z from 0 to depth

        Returns:
            List of BrickPlacement in Box-local coordinates.
        """
        prefix = f"{comment_prefix}{self.name} > "

        # Each entry: (wall, facing, x_transform, z_transform).
        # Transforms map wall-local (p.x, p.z) → box-local (x, z).
        # p.x = position along wall face; p.z = depth offset (0 or negative for ledges).
        #
        # South: identity — face runs along X from origin
        # North: mirror X, shift Z to far edge
        # West:  swap axes (face→Z, depth→X)
        # East:  swap + mirror Z, shift X to right edge
        wall_configs = [
            # TODO: South wall transform looks correct for corner-based coords
            # only if we DON'T apply center-origin correction.  If a center-
            # origin fix is added in to_ldraw_line(), this will remain correct.
            # But if the fix is applied here instead, south also needs adjustment.
            (self.south, "south",
             lambda p: p.x,
             lambda p: p.z),
            # TODO BUG: North wall x-transform subtracts p.part.width_studs to
            # mirror the brick's position, but this assumes the brick's anchor
            # point is at its left edge in world space after rotation.  With
            # rotation=180 the LDraw part origin (center) is already mirrored,
            # so subtracting width_studs is a double-correction and shifts
            # every brick one-brick-width off in X.
            # Possible fix: account for the fact that the 180° rotation matrix
            # already mirrors the part around its origin.  The correct offset
            # depends on whether internal coords are corner-based or center-based.
            # If corner-based, the formula should be:
            #   width - p.x - 1   (map last stud, not last stud + width)
            # or needs a half-width correction added at LDraw export time.
            (self.north, "north",
             lambda p: self.width - p.x - p.part.width_studs,
             # TODO VERIFY: z = self.depth + p.z places the wall's z=0 row
             # at z=depth in box space.  But with rotation=180 the brick's
             # depth (2 studs) extends in the -Z direction (back toward the
             # box interior).  This means the wall's OUTER face sits at
             # z=depth and its inner face at z=depth-2.  If the intent is
             # for the wall to sit with its outer face at z=depth, this is
             # correct.  But if the south wall's outer face is at z=0 and
             # inner face at z=2, then the box interior is 2 studs smaller
             # than (width × depth) on each axis — verify this matches the
             # LLM's mental model of box dimensions.
             lambda p: self.depth + p.z),
            # TODO BUG: West wall swaps axes (face→Z, depth→X) but does not
            # account for the brick width along the new axis.  After rotation
            # 270°, the part's local width runs along world-Z.  Mapping p.x
            # (wall-face position) directly to box-Z without subtracting or
            # adjusting for brick width means the brick's far edge may overshoot
            # the box boundary by width_studs - 1 studs.
            # This may appear correct for 1x1 bricks but shifts wider bricks.
            (self.west, "west",
             lambda p: p.z,
             lambda p: p.x),
            # TODO BUG: East wall z-transform subtracts p.part.width_studs, but
            # after 90° rotation the brick's local width_studs axis maps to the
            # world Z axis.  The subtraction is meant to flip the wall-face
            # coordinate, but it uses the *unrotated* part width.  For bricks
            # placed at rotation=0 in wall-local space and then globally
            # rotated to 90°, the extent along world-Z is still width_studs,
            # but the part's LDraw origin (center) already sits at the middle.
            # This causes an off-by-width_studs error in Z for every brick on
            # the east wall.
            # Possible fix: same center-vs-corner issue as north wall.  Either
            # adjust to  self.depth - p.x - 1  or add half-width corrections
            # at export time to reconcile corner-based internal coords with
            # center-based LDraw origins.
            (self.east, "east",
             lambda p: self.width + p.z,
             lambda p: self.depth - p.x - p.part.width_studs),
        ]

        result = []
        for wall, facing, x_fn, z_fn in wall_configs:
            rotation = FACING_TO_ROTATION[facing]
            for p in wall.to_placements(prefix):
                # TODO BUG: The x/z transforms above use p.part.width_studs
                # (the LOCAL/unrotated width) to compute positions, but then
                # the brick is placed with `rotation` (90, 180, 270).  After
                # rotation, the part's world-space footprint has its width and
                # depth swapped (for 90/270) or both flipped (for 180).
                # The transforms should use the ROTATED extents:
                #   rot 0/180: world_w = width_studs, world_d = depth_studs
                #   rot 90/270: world_w = depth_studs, world_d = width_studs
                # Using the wrong extent is likely the direct cause of the
                # "one stud off" defect on east and north walls, because
                # width_studs and depth_studs differ by 1-2 studs for
                # rectangular bricks like 2x4 or 1x4.
                result.append(BrickPlacement(
                    p.part, x_fn(p), p.y, z_fn(p), rotation, p.color, p.comment
                ))
        return result


# ---------------------------------------------------------------------------
# Section 8: FloorSlab Class
# ---------------------------------------------------------------------------
#
# A FloorSlab is a horizontal rectangular surface made of plates.
# Used for: foundations, floor/ceiling dividers, balcony surfaces, flat roofs.
#
# It tiles the area with plates using a simple greedy algorithm.
# No running bond needed for plates (they're only 1 plate tall).


class FloorSlab:
    """A horizontal rectangular surface tiled with plates.

    Lives in its own local coordinate space:
      - X axis: width (studs), Z axis: depth (studs), Y = 0 (one plate tall).

    Attributes:
        name: Identifier for LDraw comments.
        width: East-west dimension in studs.
        depth: North-south dimension in studs.
        color: LDraw color code.
        fill_part: Part catalog key for fill plates.
        height_plates: Always 1 (one plate tall).
    """

    def __init__(
        self,
        width: int,
        depth: int,
        color: int = Color.LIGHT_GREY,
        fill_part: str = PartType.PLATE_2X4.value,
        name: str = "",
    ):
        """Create a floor slab.

        Args:
            width: East-west dimension in studs.
            depth: North-south dimension in studs.
            color: LDraw color code.
            fill_part: Part catalog key for fill plates.
            name: Identifier for LDraw comments.
        """
        self.name = name or "floor"
        self.width = width
        self.depth = depth
        self.color = color
        self.fill_part = fill_part
        self.height_plates = 1  # one plate tall

    def to_placements(self, comment_prefix: str = "") -> list[BrickPlacement]:
        """Tile the floor area with plates.

        Uses a greedy algorithm: fill rows along X with widest plates,
        advance along Z by the plate's depth.

        Available plates for tiling (sorted by area, largest first):
          plate_2x4 (8), plate_2x3 (6), plate_2x2 (4),
          plate_1x4 (4), plate_1x2 (2), plate_1x1 (1)

        Returns:
            List of BrickPlacement in floor-local coordinates.
        """
        placements: list[BrickPlacement] = []
        prefix = f"{comment_prefix}{self.name}"

        # Available plates sorted by depth then width (largest first)
        # so we fill with fewer, larger plates.
        fill_plates = [
            PARTS["plate_2x4"],  # 4w x 2d
            PARTS["plate_2x3"],  # 3w x 2d
            PARTS["plate_2x2"],  # 2w x 2d
            PARTS["plate_1x4"],  # 4w x 1d
            PARTS["plate_1x2"],  # 2w x 1d
            PARTS["plate_1x1"],  # 1w x 1d
        ]

        # Track which cells are filled: grid[x][z] = bool
        filled = [[False] * self.depth for _ in range(self.width)]

        # Iterate over the floor area and place plates greedily
        for z in range(self.depth):
            for x in range(self.width):
                if filled[x][z]:
                    continue

                # Try to place the largest plate that fits
                placed = False
                for plate in fill_plates:
                    pw = plate.width_studs
                    pd = plate.depth_studs

                    # Check bounds
                    if x + pw > self.width or z + pd > self.depth:
                        continue

                    # Check all cells are unfilled
                    if any(filled[cx][cz] for cx in range(x, x + pw) for cz in range(z, z + pd)):
                        continue

                    # Place this plate and mark cells as filled
                    for cx in range(x, x + pw):
                        for cz in range(z, z + pd):
                            filled[cx][cz] = True

                    placements.append(BrickPlacement(
                        part=plate,
                        x=x, y=0, z=z,
                        rotation=0,
                        color=self.color,
                        comment=prefix,
                    ))
                    placed = True
                    break

                if not placed:
                    filled[x][z] = True  # skip unfillable (shouldn't happen)

        return placements


# ---------------------------------------------------------------------------
# Section 9: Column Class
# ---------------------------------------------------------------------------
#
# A Column is a vertical stack of bricks at a single point.
# Used for: porch columns, structural piers, decorative pillars.
#
# The column is 1x1 studs by default (using brick_1x1), but can use
# larger bricks (e.g. brick_2x2) for thicker columns.


class Column:
    """A vertical stack of identical bricks.

    Attributes:
        name: Identifier for LDraw comments.
        height_bricks: Number of brick rows.
        color: LDraw color code.
        part: The Part used for each row of the column.
    """

    def __init__(
        self,
        height: int,
        color: int = Color.WHITE,
        part_type: PartType = PartType.BRICK_1X1,
        name: str = "",
    ):
        """Create a column.

        Args:
            height: Column height in brick rows.
            color: LDraw color code.
            part_type: PartType for each brick in the column.
            name: Identifier for LDraw comments.
        """
        self.name = name or "column"
        self.height_bricks = height
        self.height_plates = height * PLATES_PER_BRICK
        self.color = color
        self.part = find_part(part_type)

    def to_placements(self, comment_prefix: str = "") -> list[BrickPlacement]:
        """Stack bricks vertically from y=0 up.

        Returns:
            List of BrickPlacement in column-local coordinates.
        """
        placements = []
        prefix = f"{comment_prefix}{self.name}"

        for row in range(self.height_bricks):
            y_plate = row * PLATES_PER_BRICK
            placements.append(BrickPlacement(
                part=self.part,
                x=0, y=y_plate, z=0,
                rotation=0,
                color=self.color,
                comment=f"{prefix} row_{row}",
            ))

        return placements


# ---------------------------------------------------------------------------
# Section 10: GableRoof helpers
# ---------------------------------------------------------------------------

def _tile_row(
    span: int,
    y_plate: int,
    x0: float,
    z0: float,
    along_x: bool,
    rotation: int,
    color: int,
    comment: str,
) -> list[BrickPlacement]:
    """Greedily fill a single brick row using FILL_BRICKS.

    Walks from 0 to `span`, placing the widest fitting brick at each step.
    Used by GableRoof slope and gable builders.
    
    Args:
        span: Total studs to fill along the tiling axis.
        y_plate: Vertical position in plates.
        x0, z0: Starting position in studs.
        along_x: True = tile along X; False = tile along Z.
        rotation: Brick rotation angle (0 or 90).
        color: LDraw color code.
        comment: LDraw comment string for each placed brick.

    Returns:
        List of BrickPlacements for this row.
    """
    # TODO BUG: When along_x=False and rotation=90, bricks are placed along Z
    # and advanced by brick.width_studs.  But after 90° rotation, the brick's
    # local width_studs axis maps to world-Z, and its depth maps to world-X.
    # The span check `pos + brick.width_studs <= span` is correct for the
    # tiling direction, but the resulting BrickPlacement stores the brick with
    # its unrotated width_studs, so the center-origin mismatch from
    # to_ldraw_line() shifts every roof brick by half a brick along the
    # tiling axis.  This compounds with the same issue in wall tiling.
    placements: list[BrickPlacement] = []
    pos = 0
    while pos < span:
        placed = False
        for brick in FILL_BRICKS:
            if pos + brick.width_studs <= span:
                placements.append(BrickPlacement(
                    part=brick,
                    x=x0 + (pos if along_x else 0),
                    y=y_plate,
                    z=z0 + (0 if along_x else pos),
                    rotation=rotation,
                    color=color,
                    comment=comment,
                ))
                pos += brick.width_studs
                placed = True
                break
        if not placed:
            pos += 1  # skip unfillable stud (shouldn't happen with 1x1 fallback)
    return placements


# ---------------------------------------------------------------------------
# Section 10: GableRoof Class
# ---------------------------------------------------------------------------
#
# A GableRoof generates a peaked roof using stepped bricks (v1).
# Future: replace with slope bricks for a smoother appearance.
#
# The roof sits on top of a rectangular footprint. The ridge runs
# along one axis (east_west or north_south). The two sloping sides
# step inward, each row 1 stud narrower per side and 1 brick taller.
#
# Anatomy (cross-section, ridge running east-west, viewed from east):
#
#          /\            <- ridge
#         /  \
#        /    \          Each "step" is one brick row, inset 1 stud
#       /      \            from each side compared to the row below.
#      /________\        <- base = full width
#
# The gable ends (triangular walls closing the ends) are also generated
# as stepped walls.
#
# For v1, each step is a regular brick row (not slope bricks).
# This creates a stepped/ziggurat profile rather than a smooth slope.


class GableRoof:
    """A peaked roof made of stepped brick rows.

    The roofs local coordinate space:
      - Origin at bottom-left corner of the footprint (same as a Box).
      - Ridge runs along the specified axis.
      - Steps rise from both sides toward the center ridge.

    Attributes:
        name: Identifier for LDraw comments.
        width: Footprint width in studs (perpendicular to ridge).
        depth: Footprint depth in studs (along ridge).
        ridge: "east_west" or "north_south" — direction the ridge runs.
        color: LDraw color code for roof bricks.
        fill_part: Part catalog key for roof bricks.
        num_steps: How many step rows from base to ridge.
    """

    def __init__(
        self,
        width: int,
        depth: int,
        ridge: str = "east_west",
        color: int = Color.DARK_BLUISH_GREY,
        fill_part: str = PartType.BRICK_2X4.value,
        name: str = "",
    ):
        """Create a gable roof.

        Args:
            width: Footprint width in studs (perpendicular to ridge).
            depth: Footprint depth in studs (along ridge).
            ridge: "east_west" (ridge runs left-right) or
                   "north_south" (ridge runs front-back).
            color: LDraw color code for roof bricks.
            fill_part: Part catalog key for roof bricks.
            name: Identifier for LDraw comments.
        """
        if ridge not in ("east_west", "north_south"):
            raise BuilderError(
                f"Invalid ridge direction '{ridge}'. "
                f"Must be 'east_west' or 'north_south'."
            )

        self.name = name or "roof"
        self.width = width
        self.depth = depth
        self.ridge = ridge
        self.color = color
        self.fill_part = fill_part

        # The slope dimension is perpendicular to the ridge.
        # Each step insets 1 stud from each side, so the number of
        # steps is half the slope dimension (rounded down).
        if ridge == "east_west":
            # Ridge runs along X. Slope is along Z (depth).
            self.slope_span = depth
        else:
            # Ridge runs along Z. Slope is along X (width).
            self.slope_span = width

        self.num_steps = self.slope_span // 2

    @property
    def height_plates(self) -> int:
        """Total height of the roof in plates."""
        return self.num_steps * PLATES_PER_BRICK

    def to_placements(self, comment_prefix: str = "") -> list[BrickPlacement]:
        """Generate brick placements for the stepped roof.

        Creates two mirrored slopes stepping inward toward the ridge,
        plus gable end walls (triangular infill at each end).

        All coordinates are in roof-local space. The roof's base
        is at y=0 (meant to be placed on top of walls via place()).

        Returns:
            List of BrickPlacement in roof-local coordinates.
        """
        prefix = f"{comment_prefix}{self.name}"
        placements: list[BrickPlacement] = []

        if self.ridge == "east_west":
            # Ridge runs along X (width). Slopes step inward along Z (depth).
            # Each step: row of bricks along the full width,
            # inset from front and back by `step` studs.
            placements.extend(self._build_ew_slopes(prefix))
            placements.extend(self._build_ew_gables(prefix))
        else:
            # Ridge runs along Z (depth). Slopes step inward along X (width).
            placements.extend(self._build_ns_slopes(prefix))
            placements.extend(self._build_ns_gables(prefix))

        return placements

    def _build_ew_slopes(self, prefix: str) -> list[BrickPlacement]:
        """Build slopes for east-west ridge (stepping along Z/depth).

        For each step level, place a row of bricks along the full width
        on both the south slope (front) and north slope (back).
        """
        placements: list[BrickPlacement] = []
        for step in range(self.num_steps):
            y_plate = step * PLATES_PER_BRICK
            z_south = step
            z_north = self.depth - step - WALL_DEPTH_STUDS
            for z_pos, side in [(z_south, "south_slope"), (z_north, "north_slope")]:
                placements.extend(_tile_row(
                    span=self.width, y_plate=y_plate,
                    x0=0, z0=z_pos, along_x=True, rotation=0,
                    color=self.color, comment=f"{prefix} {side} step_{step}",
                ))
        return placements

    def _build_ew_gables(self, prefix: str) -> list[BrickPlacement]:
        """Build triangular gable end walls for east-west ridge.

        Gable walls fill the triangular space at the west (x=0) and
        east (x=width) ends of the roof. Each step level is narrower
        than the one below.
        """
        placements: list[BrickPlacement] = []
        for step in range(self.num_steps):
            y_plate = step * PLATES_PER_BRICK
            z_start = step
            z_end = self.depth - step
            gable_length = z_end - z_start
            if gable_length <= 0:
                break
            # TODO BUG: East gable is placed at x_pos=self.width, but the box
            # footprint runs from x=0 to x=width-1 in studs.  With rotation=90
            # and center-origin parts, this places the gable wall one stud
            # beyond the box's east edge.  Should probably be
            #   self.width - WALL_DEPTH_STUDS
            # to match how the east wall of a Box sits at x=width with depth
            # going inward (negative x direction via rotation).
            # Similarly, west gable at x=0 may need to be at x=0 or adjusted
            # depending on how the 90° rotation maps the brick's depth.
            for x_pos, side in [(0, "west_gable"), (self.width, "east_gable")]:
                placements.extend(_tile_row(
                    span=gable_length, y_plate=y_plate,
                    x0=x_pos, z0=z_start, along_x=False, rotation=90,
                    color=self.color, comment=f"{prefix} {side} step_{step}",
                ))
        return placements

    def _build_ns_slopes(self, prefix: str) -> list[BrickPlacement]:
        """Build slopes for north-south ridge (stepping along X/width).

        Same logic as _build_ew_slopes but rotated: steps along X,
        rows run along Z (depth), bricks rotated 90°.
        """
        placements: list[BrickPlacement] = []
        for step in range(self.num_steps):
            y_plate = step * PLATES_PER_BRICK
            x_west = step
            x_east = self.width - step - WALL_DEPTH_STUDS
            for x_pos, side in [(x_west, "west_slope"), (x_east, "east_slope")]:
                placements.extend(_tile_row(
                    span=self.depth, y_plate=y_plate,
                    x0=x_pos, z0=0, along_x=False, rotation=90,
                    color=self.color, comment=f"{prefix} {side} step_{step}",
                ))
        return placements

    def _build_ns_gables(self, prefix: str) -> list[BrickPlacement]:
        """Build triangular gable end walls for north-south ridge.

        Gable walls at south (z=0) and north (z=depth) ends, running along X.
        """
        placements: list[BrickPlacement] = []
        for step in range(self.num_steps):
            y_plate = step * PLATES_PER_BRICK
            x_start = step
            x_end = self.width - step
            gable_length = x_end - x_start
            if gable_length <= 0:
                break
            # TODO BUG: North gable at z_pos=self.depth places the gable wall
            # one stud beyond the box's north edge (footprint is 0..depth-1).
            # Should likely be  self.depth - WALL_DEPTH_STUDS  to sit flush
            # with the north wall.  Same center-origin / boundary issue as the
            # east gable in _build_ew_gables.
            for z_pos, side in [(0, "south_gable"), (self.depth, "north_gable")]:
                placements.extend(_tile_row(
                    span=gable_length, y_plate=y_plate,
                    x0=x_start, z0=z_pos, along_x=True, rotation=0,
                    color=self.color, comment=f"{prefix} {side} step_{step}",
                ))
        return placements


# ---------------------------------------------------------------------------
# Section 11: Element type alias
# ---------------------------------------------------------------------------
#
# Any object that has to_placements() and can be positioned in a scene.
# Used for type hints in Group, place(), attach().

# We can't use a Protocol here (keeping it simple), so we just document
# that any "element" must have:
#   .to_placements(comment_prefix: str) -> list[BrickPlacement]
#   .height_plates: int
#   .name: str
# And optionally:
#   .width: int (for Box, FloorSlab, GableRoof)
#   .depth: int (for Box, FloorSlab, GableRoof)

def _get_height(element) -> int:
    """Get an element's height in plates."""
    return getattr(element, "height_plates", 0)


def _get_width(element) -> int:
    """Get an element's width in studs (X dimension)."""
    if hasattr(element, "width"):
        return element.width
    if hasattr(element, "length"):
        return element.length
    return 0


def _get_depth(element) -> int:
    """Get an element's depth in studs (Z dimension)."""
    if hasattr(element, "depth"):
        return element.depth
    if hasattr(element, "length"):
        return element.length
    return 0


# ---------------------------------------------------------------------------
# Section 12: Group Class
# ---------------------------------------------------------------------------
#
# A Group bundles elements together with a shared coordinate space.
# Each child element has an offset (x, y, z) within the group.
#
# Groups can contain other Groups, enabling hierarchical models:
#   building
#     └─ ground_floor (Group)
#         ├─ box (Box)
#         ├─ floor_slab (FloorSlab)
#         └─ porch (Group)
#             ├─ columns (Column × 2)
#             └─ porch_roof (FloorSlab)
#     └─ second_floor (Group)
#         └─ ...
#
# Groups track their bounding box for stacking and alignment.


class Group:
    """A named collection of positioned elements.

    Each child is stored with an (x, y, z) offset relative to this
    group's local origin.

    Attributes:
        name: Identifier for LDraw comments.
        children: List of (element, x_offset, y_offset, z_offset) tuples.
    """

    def __init__(self, name: str, elements: list | None = None):
        """Create a group, optionally with initial elements at origin.

        Args:
            name: Group identifier for LDraw comments.
            elements: Optional list of elements to add at (0, 0, 0).
        """
        self.name = name
        # Children: (element, x_off, y_off, z_off)
        self.children: list[tuple[Any, float, float, float]] = []

        if elements:
            for elem in elements:
                self.children.append((elem, 0, 0, 0))

    def add(self, element, x: float = 0, y: float = 0, z: float = 0):
        """Add an element at a specific offset within this group.

        Args:
            element: Any element with to_placements() method.
            x: X offset in studs.
            y: Y offset in plates.
            z: Z offset in studs.
        """
        self.children.append((element, x, y, z))

    @property
    def height_plates(self) -> int:
        """Total height: max (child_y_offset + child_height) across all children."""
        if not self.children:
            return 0
        return max(
            int(y_off) + _get_height(elem)
            for elem, _, y_off, _ in self.children
        )

    @property
    def width(self) -> int:
        """Total width: max (child_x_offset + child_width) across all children."""
        if not self.children:
            return 0
        return max(
            int(x_off) + _get_width(elem)
            for elem, x_off, _, _ in self.children
        )

    @property
    def depth(self) -> int:
        """Total depth: max (child_z_offset + child_depth) across all children."""
        if not self.children:
            return 0
        return max(
            int(z_off) + _get_depth(elem)
            for elem, _, _, z_off in self.children
        )

    def stack(self, times: int) -> "Group":
        """Repeat this group vertically, creating a new group with N copies.

        Each copy is offset upward by this group's height_plates.
        The original is copy 0 (at y=0).

        Args:
            times: Total number of copies (including the original).

        Returns:
            A new Group containing all stacked copies.
        """
        if times < 1:
            raise BuilderError("stack times must be >= 1")

        stacked = Group(f"{self.name}_stacked")
        h = self.height_plates

        for i in range(times):
            stacked.add(self, x=0, y=i * h, z=0)

        return stacked

    def to_placements(self, comment_prefix: str = "") -> list[BrickPlacement]:
        """Generate placements for all children, offset by their positions.

        Recursively resolves nested groups. Each child's placements are
        offset by the child's (x, y, z) position within this group.

        Args:
            comment_prefix: Prepended to LDraw comments.

        Returns:
            List of BrickPlacement in this group's local coordinates.
        """
        # Anonymous (empty-named) groups pass the prefix through unchanged —
        # used by Scene's root group so it doesn't add a spurious "scene > " prefix.
        prefix = f"{comment_prefix}{self.name} > " if self.name else comment_prefix
        result = []

        for elem, x_off, y_off, z_off in self.children:
            for p in elem.to_placements(prefix):
                result.append(p.offset_by(x_off, y_off, z_off))

        return result


# Update Element type to include Group
Element = Wall | Box | FloorSlab | Column | GableRoof | Group


# ---------------------------------------------------------------------------
# Section 13: Placement Functions — place() and attach()
# ---------------------------------------------------------------------------
#
# place(element, on=target)  — position element on top of target
# attach(element, to=target, face=...) — position element beside target
#
# Both functions work by adding the element into the target's parent
# group at the correct offset. If there's no parent group, they
# create one.
#
# These are the two spatial relationship verbs in the DSL:
#   - "on top of" → place()
#   - "next to" → attach()


def place(
    element,
    on=None,
    at_level: int | None = None,
    align: str = "center",
    offset: tuple[float, float] = (0, 0),
) -> Group:
    """Position an element on top of another, or at a specific level.

    Creates (or returns) a Group containing both elements correctly
    positioned.

    Args:
        element: The element to position.
        on: The element to stack on top of. Mutually exclusive with at_level.
        at_level: Absolute Y position in plates. Used for floating elements
                  like canopy slabs. Mutually exclusive with `on`.
        align: How to align horizontally. Options:
               "center" — center element on target
               "flush_north" — align element's north edge with target's
               "flush_south", "flush_east", "flush_west" — similar
               "origin" — align origins (no horizontal offset)
        offset: Additional (x_studs, z_studs) offset after alignment.

    Returns:
        A Group containing both elements (or the modified group if `on`
        is already a Group).

    Raises:
        BuilderError: If neither `on` nor `at_level` is specified.
    """
    if on is None and at_level is None:
        raise BuilderError(
            "place() requires either 'on=<element>' or 'at_level=<plates>'. "
            "Example: place(roof, on=walls) or place(slab, at_level=30)"
        )

    # Calculate vertical offset
    if at_level is not None:
        y_off = at_level
    else:
        y_off = _get_height(on)

    # Calculate horizontal alignment offset
    x_off, z_off = 0.0, 0.0

    if on is not None and align != "origin":
        target_w = _get_width(on)
        target_d = _get_depth(on)
        elem_w = _get_width(element)
        elem_d = _get_depth(element)

        if align == "center":
            x_off = (target_w - elem_w) / 2
            z_off = (target_d - elem_d) / 2
        elif align == "flush_south":
            x_off = (target_w - elem_w) / 2
            z_off = 0
        elif align == "flush_north":
            x_off = (target_w - elem_w) / 2
            z_off = target_d - elem_d
        elif align == "flush_west":
            x_off = 0
            z_off = (target_d - elem_d) / 2
        elif align == "flush_east":
            x_off = target_w - elem_w
            z_off = (target_d - elem_d) / 2

    # Apply additional manual offset
    x_off += offset[0]
    z_off += offset[1]

    # If `on` is already a Group, add element to it directly
    if isinstance(on, Group):
        on.add(element, x=x_off, y=y_off, z=z_off)
        return on

    # Otherwise, create a new Group containing both
    group = Group(f"{getattr(on, 'name', 'base')}+{getattr(element, 'name', 'placed')}")
    if on is not None:
        group.add(on, x=0, y=0, z=0)
    group.add(element, x=x_off, y=y_off, z=z_off)
    return group


def attach(
    element,
    to,
    face: str,
    align: str = "center",
    offset: tuple[float, float] = (0, 0),
) -> Group:
    """Position an element beside another, connected at a face.

    Args:
        element: The element to position.
        to: The target element to attach to.
        face: Which face of `to` to attach at:
              "north" — attach to target's north face (element goes behind)
              "south" — attach to target's south face (element goes in front)
              "east"  — attach to target's east face (element goes right)
              "west"  — attach to target's west face (element goes left)
        align: Alignment along the face:
               "center" — center along the face
               "flush_north"/"flush_south" — for east/west faces
               "flush_east"/"flush_west" — for north/south faces
               "origin" — align origins along the face
        offset: Additional (along_face, vertical) offset in studs/plates.
                First value: offset along the face direction.
                Second value: vertical offset in plates.

    Returns:
        A Group containing both elements.

    Raises:
        BuilderError: If face is invalid.
    """
    if face not in ("north", "south", "east", "west"):
        raise BuilderError(
            f"Invalid face '{face}'. Must be 'north', 'south', 'east', or 'west'."
        )

    target_w = _get_width(to)
    target_d = _get_depth(to)
    elem_w = _get_width(element)
    elem_d = _get_depth(element)

    # Calculate position based on face
    x_off, z_off, y_off = 0.0, 0.0, 0.0

    if face == "east":
        # Element goes to the right of target (positive X)
        x_off = target_w
        # Align along Z axis
        if align == "center":
            z_off = (target_d - elem_d) / 2
        elif align == "flush_south":
            z_off = 0
        elif align == "flush_north":
            z_off = target_d - elem_d
        z_off += offset[0]
        y_off = offset[1]

    elif face == "west":
        # Element goes to the left of target (negative X)
        x_off = -elem_w
        if align == "center":
            z_off = (target_d - elem_d) / 2
        elif align == "flush_south":
            z_off = 0
        elif align == "flush_north":
            z_off = target_d - elem_d
        z_off += offset[0]
        y_off = offset[1]

    elif face == "north":
        # Element goes behind target (positive Z)
        z_off = target_d
        if align == "center":
            x_off = (target_w - elem_w) / 2
        elif align == "flush_west":
            x_off = 0
        elif align == "flush_east":
            x_off = target_w - elem_w
        x_off += offset[0]
        y_off = offset[1]

    elif face == "south":
        # Element goes in front of target (negative Z)
        z_off = -elem_d
        if align == "center":
            x_off = (target_w - elem_w) / 2
        elif align == "flush_west":
            x_off = 0
        elif align == "flush_east":
            x_off = target_w - elem_w
        x_off += offset[0]
        y_off = offset[1]

    # If `to` is already a Group, add element to it
    if isinstance(to, Group):
        to.add(element, x=x_off, y=y_off, z=z_off)
        return to

    # Otherwise, create a new Group
    group = Group(f"{getattr(to, 'name', 'base')}+{getattr(element, 'name', 'attached')}")
    group.add(to, x=0, y=0, z=0)
    group.add(element, x=x_off, y=y_off, z=z_off)
    return group


# ---------------------------------------------------------------------------
# Section 14: Scene Class — Orchestrator + LDraw Export
# ---------------------------------------------------------------------------
#
# The Scene is the top-level container. It holds all elements and
# exports the final LDraw .mpd file.
#
# Usage:
#   scene = Scene("my_building")
#   box = scene.box(24, 16, 10)
#   ...
#   scene.export("output.mpd")
#
# The Scene provides factory methods (scene.box(), scene.wall(), etc.)
# so all elements are automatically tracked. Elements can also be
# added manually with scene.add().


class Scene:
    """Top-level container and LDraw exporter.

    Provides factory methods for creating elements and tracks them
    automatically. Handles final coordinate resolution and LDraw output.

    Internally, all top-level elements are held in an anonymous root Group
    so placement collection reuses Group.to_placements() with no duplication.

    Attributes:
        name: Model name (used in LDraw file header).
    """

    def __init__(self, name: str = "model"):
        """Create a scene.

        Args:
            name: Model name for LDraw file header.
        """
        self.name = name
        # Root group with empty name so it adds no prefix to LDraw comments.
        self._root = Group(name="")

    # --- Factory Methods ---
    # These create elements and add them to the scene at the origin.
    # The LLM uses these instead of constructing objects directly.

    def box(
        self,
        width: int,
        depth: int,
        height: int,
        color: int = Color.WHITE,
        name: str = "",
    ) -> Box:
        """Create a Box and add it to the scene.

        Args:
            width: East-west dimension in studs.
            depth: North-south dimension in studs.
            height: Wall height in brick rows.
            color: LDraw color code.
            name: Identifier for LDraw comments.

        Returns:
            The created Box (already added to scene).
        """
        b = Box(width=width, depth=depth, height=height, color=color, name=name)
        self._root.add(b)
        return b

    def wall(
        self,
        length: int,
        height: int,
        facing: str,
        color: int = Color.WHITE,
        name: str = "",
    ) -> Wall:
        """Create a standalone Wall and add it to the scene."""
        w = Wall(length=length, height=height, facing=facing, color=color, name=name)
        self._root.add(w)
        return w

    def floor_slab(
        self,
        width: int,
        depth: int,
        color: int = Color.LIGHT_GREY,
        name: str = "",
    ) -> FloorSlab:
        """Create a FloorSlab and add it to the scene."""
        f = FloorSlab(width=width, depth=depth, color=color, name=name)
        self._root.add(f)
        return f

    def column(
        self,
        height: int,
        color: int = Color.WHITE,
        part_type: PartType = PartType.BRICK_1X1,
        name: str = "",
    ) -> Column:
        """Create a Column and add it to the scene."""
        c = Column(height=height, color=color, part_type=part_type, name=name)
        self._root.add(c)
        return c

    def gable_roof(
        self,
        width: int,
        depth: int,
        ridge: str = "east_west",
        color: int = Color.DARK_BLUISH_GREY,
        name: str = "",
    ) -> GableRoof:
        """Create a GableRoof and add it to the scene."""
        r = GableRoof(width=width, depth=depth, ridge=ridge, color=color, name=name)
        self._root.add(r)
        return r

    def group(self, name: str, elements: list | None = None) -> Group:
        """Create a Group and add it to the scene."""
        g = Group(name=name, elements=elements)
        self._root.add(g)
        return g

    def add(self, element, x: float = 0, y: float = 0, z: float = 0):
        """Add an existing element to the scene at a specific position."""
        self._root.add(element, x=x, y=y, z=z)

    # --- Export ---

    def _collect_all_placements(self) -> list[BrickPlacement]:
        """Collect all BrickPlacements in global coordinates.

        Delegates to the root Group, which recursively resolves all children.
        """
        return self._root.to_placements()

    def export(self, filename: str) -> str:
        """Export the scene as an LDraw .mpd file.

        Collects all placements, converts to LDraw coordinates, and
        writes to file. Returns the file path.

        The output file structure:
          0 FILE <name>.ldr
          0 <name>
          0 Name: <name>.ldr
          0 Author: lego_builder.py
          0 // <comment>
          1 <color> <x> <y> <z> <matrix> <part>
          ...
          0 NOFILE

        Args:
            filename: Output file path (e.g. "building.mpd").

        Returns:
            The filename (for convenience).
        """
        placements = self._collect_all_placements()

        lines = []
        # MPD file header
        model_name = self.name.replace(" ", "_")
        lines.append(f"0 FILE {model_name}.ldr")
        lines.append(f"0 {self.name}")
        lines.append(f"0 Name: {model_name}.ldr")
        lines.append(f"0 Author: lego_builder.py")
        lines.append(f"0 !LDRAW_ORG Unofficial_Model")
        lines.append("")

        # Sort placements by Y (bottom to top) for readable output
        placements.sort(key=lambda p: (p.y, p.z, p.x))

        # Write each placement as LDraw type-1 line with comment
        current_y = None
        for p in placements:
            # Add a blank line between different Y levels for readability
            if current_y is not None and p.y != current_y:
                lines.append("")
            current_y = p.y

            lines.append(p.to_ldraw_line())

        lines.append("")
        lines.append("0 NOFILE")
        lines.append("")

        # Write to file
        content = "\n".join(lines)
        with open(filename, "w") as f:
            f.write(content)

        return filename

    def stats(self) -> dict:
        """Return model statistics: part count, unique parts, dimensions.

        Useful for the LLM to verify the model looks reasonable.

        Returns:
            Dict with keys: total_parts, unique_parts, width, depth, height,
            part_counts (dict of part description -> count).
        """
        placements = self._collect_all_placements()

        part_counts: dict[str, int] = {}
        for p in placements:
            desc = p.part.description
            part_counts[desc] = part_counts.get(desc, 0) + 1

        xs = [p.x for p in placements] if placements else [0]
        ys = [p.y for p in placements] if placements else [0]
        zs = [p.z for p in placements] if placements else [0]

        return {
            "total_parts": len(placements),
            "unique_parts": len(part_counts),
            "width_studs": max(xs) - min(xs) + 4,  # approximate
            "depth_studs": max(zs) - min(zs) + 2,
            "height_plates": max(ys) + 3,
            "part_counts": part_counts,
        }
