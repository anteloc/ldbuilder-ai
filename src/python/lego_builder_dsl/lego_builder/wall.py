"""
Wall class: a rectangular brick wall with openings, inserts, and ledges.

A Wall is a rectangular surface of bricks, defined by:
  - length (studs along its face)
  - height (brick rows)
  - facing (north/south/east/west)

Internally, a wall stores a 2D boolean grid sized in studs × plates.
True = solid (will be filled with bricks). False = opening (empty).

The wall uses 2xN bricks oriented with their depth (2 studs) going
INTO the wall, and their width along the wall face. This gives
structurally realistic walls that are 2 studs (1 brick) deep.

At export time, the solid regions are tiled with bricks using a greedy
algorithm with running bond (each row offset by half a brick width).
"""

from __future__ import annotations

from .coords import PLATES_PER_BRICK, FACING_TO_ROTATION
from .parts import PartType, Part, PARTS, FILL_BRICKS, find_part, Color
from .core import BuilderError, BrickPlacement

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
