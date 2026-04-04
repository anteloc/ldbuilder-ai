"""
Structural elements: Box, FloorSlab, and Column.

Box: 4-wall rectangular enclosure.
FloorSlab: horizontal plate surface.
Column: vertical stack of identical bricks.
"""

from __future__ import annotations

from typing import Literal

from .coords import PLATES_PER_BRICK, FACING_TO_ROTATION
from .parts import PartType, Part, PARTS, find_part, Color
from .core import BuilderError, BrickPlacement
from .wall import Wall, WALL_DEPTH_STUDS

# ---------------------------------------------------------------------------
# WallLayout Class
# ---------------------------------------------------------------------------
#
# A WallLayout is a convenience that creates a series of joined walls forming 
# an arbitrary shape composed by walls extending east, west, north or south, joined by corners.
# It handles wall positioning so the LLM never calculates wall coordinates.
#
# The WallLayout lives in its own local coordinate space:
#   - Origin (0, 0, 0) is at the starting point for the first wall.
#   - X axis represents east-west orientation, while Z axis represents north-south, and Y is up.
#
# TODO Wall layout (viewed from above)
#
#


class WallLayout:
    """An arbitrary layout of N walls with named accessors.

    The LLM creates a WallLayout to define a set of interconnected walls, joined by corners, then modifies
    individual walls via [wall_name] dict keys.

    The LLM acts in a similar way as if it was controlling a Logo turtle:
    it starts at the origin, facing an initial direction (e.g. north), builds a wall extending in that
    direction forward, turns to another direction, builds another wall in that direction, and so on.

    Attributes:
        name: Identifier for LDraw comments.
        height_bricks: Walls uniform height in brick rows.
        height_plates: Walls uniform height in plates.
        color: Default LDraw color for all walls.
        fill_part: Part catalog key for wall fill bricks.
    """

    # Wall facing is derived from travel direction to match Box coordinate conventions:
    #   travel east  → south-facing wall  (Box south-wall analog, runs E-W)
    #   travel west  → north-facing wall  (Box north-wall analog, runs E-W)
    #   travel north → west-facing wall   (Box west-wall analog,  runs N-S)
    #   travel south → east-facing wall   (Box east-wall analog,  runs N-S)
    _TRAVEL_TO_FACING: dict[str, str] = {
        "east": "south", "west": "north",
        "north": "west", "south": "east",
    }
    _OPPOSITES: dict[str, str] = {
        "north": "south", "south": "north",
        "east": "west",   "west": "east",
    }

    def __init__(
        self,
        height: int,
        color: int = Color.WHITE,
        fill_part: str = PartType.BRICK_2X4.value,
        name: str = "",
        initial_direction: Literal["north", "south", "east", "west"] = "north",
    ):
        self.name = name or "layout"
        self.height_bricks = height
        self.height_plates = height * PLATES_PER_BRICK
        self.color = color
        self.fill_part = fill_part

        self._facing: str = initial_direction
        self._position: tuple[int, int] = (0, 0)  # (x, z) outer-corner, layout-local

        # Ordered list of (wall, cx_start, cz_start, travel_direction).
        # cx/cz are the outer-corner coords recorded when build_wall() was called.
        self._wall_records: list[tuple[Wall, int, int, str]] = []
        self._wall_map: dict[str, Wall] = {}

    def turn(self, direction: Literal["north", "south", "east", "west"]):
        """Turn facing to a new direction for the next wall.
        Turning to the opposite direction is **not allowed** (would create overlapping walls)."""
        if direction == self._OPPOSITES[self._facing]:
            raise BuilderError(
                f"Cannot turn to opposite direction '{direction}' "
                f"(currently facing '{self._facing}'): would create overlapping walls."
            )
        self._facing = direction

    def build_wall(self, wall_name: str, length: int):
        """Build a wall with the given name, extending in the current facing direction,
        with a given length in studs."""
        if wall_name in self._wall_map:
            raise BuilderError(f"Duplicate wall name '{wall_name}' in layout '{self.name}'")
        if length < 1:
            raise BuilderError(f"Wall length must be >= 1, got {length}")

        wall = Wall(
            length=length,
            height=self.height_bricks,
            facing=self._TRAVEL_TO_FACING[self._facing],
            color=self.color,
            fill_part=self.fill_part,
            name=wall_name,
        )

        cx, cz = self._position
        self._wall_records.append((wall, cx, cz, self._facing))
        self._wall_map[wall_name] = wall

        # Advance the turtle to the next outer corner.
        advances: dict[str, tuple[int, int]] = {
            "east":  (cx + length, cz),
            "west":  (cx - length, cz),
            "north": (cx, cz + length),
            "south": (cx, cz - length),
        }
        self._position = advances[self._facing]

    def __getitem__(self, wall_name: str) -> Wall:
        """Access a wall by name for modification (add openings, inserts, ledges)."""
        if wall_name not in self._wall_map:
            raise KeyError(f"No wall named '{wall_name}' in layout '{self.name}'")
        return self._wall_map[wall_name]

    def walls(self) -> list[Wall]:
        """Return all walls in the layout as a list."""
        return [record[0] for record in self._wall_records]

    def to_placements(self, comment_prefix: str = "") -> list[BrickPlacement]:
        """Generate BrickPlacements for all walls, positioned correctly.

        Transforms each wall's local-space placements into the WallLayout's
        local coordinate space. The WallLayout itself may later be transformed
        by a Group or place() call.

        Coordinate transforms mirror Box conventions exactly (see Box.to_placements):
          east travel  → south wall: x=cx+p.x,                   z=cz+p.z,                rot=180
          west travel  → north wall: x=cx-p.x-part.width,        z=cz-WALL_DEPTH+p.z,     rot=0
          north travel → west wall:  x=cx+p.z,                   z=cz+p.x,                rot=270
          south travel → east wall:  x=cx-WALL_DEPTH+p.z,        z=cz-p.x-part.width,     rot=90

        Returns:
            List of BrickPlacement in WallLayout-local coordinates.
        """
        prefix = f"{comment_prefix}{self.name} > "
        result = []

        for wall, cx, cz, travel_dir in self._wall_records:
            _facing = self._TRAVEL_TO_FACING[travel_dir]
            rotation = FACING_TO_ROTATION[_facing]

            for p in wall.to_placements(prefix):
                if travel_dir == "east":
                    x = cx + p.x
                    z = cz + p.z
                elif travel_dir == "west":
                    x = cx - p.x - p.part.width_studs
                    z = cz - WALL_DEPTH_STUDS + p.z
                elif travel_dir == "north":
                    x = cx + p.z
                    z = cz + p.x
                else:  # south
                    x = cx - WALL_DEPTH_STUDS + p.z
                    z = cz - p.x - p.part.width_studs

                result.append(BrickPlacement(
                    p.part, x, p.y, z, rotation, p.color, p.comment
                ))

        return result



# ---------------------------------------------------------------------------
# Box Class
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
            (self.south, "south",
             lambda p: p.x,
             lambda p: p.z),
            (self.north, "north",
             lambda p: self.width - p.x - p.part.width_studs,
             lambda p: self.depth - WALL_DEPTH_STUDS + p.z),       # ← FIXED
            (self.west, "west",
             lambda p: p.z,
             lambda p: p.x),
            (self.east, "east",
             lambda p: self.width - WALL_DEPTH_STUDS + p.z,        # ← FIXED
             lambda p: self.depth - p.x - p.part.width_studs),
        ]


        result = []
        for wall, facing, x_fn, z_fn in wall_configs:
            rotation = FACING_TO_ROTATION[facing]
            for p in wall.to_placements(prefix):
                result.append(BrickPlacement(
                    p.part, x_fn(p), p.y, z_fn(p), rotation, p.color, p.comment
                ))
        return result


# ---------------------------------------------------------------------------
# FloorSlab Class
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
# Column Class
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
