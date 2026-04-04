"""
GableRoof: a peaked roof made of stepped brick rows.

The roof sits on top of a rectangular footprint. The ridge runs
along one axis (east_west or north_south). The two sloping sides
step inward, each row 1 stud narrower per side and 1 brick taller.

Anatomy (cross-section, ridge running east-west, viewed from east):

         /\\            <- ridge
        /  \\
       /    \\          Each "step" is one brick row, inset 1 stud
      /      \\            from each side compared to the row below.
     /________\\        <- base = full width

The gable ends (triangular walls closing the ends) are also generated
as stepped walls.

For v1, each step is a regular brick row (not slope bricks).
This creates a stepped/ziggurat profile rather than a smooth slope.
"""

from __future__ import annotations

from .coords import PLATES_PER_BRICK
from .parts import Part, PARTS, FILL_BRICKS, PartType, Color
from .core import BuilderError, BrickPlacement
from .wall import WALL_DEPTH_STUDS


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
            for x_pos, side in [(0, "west_gable"), (self.width - WALL_DEPTH_STUDS, "east_gable")]:
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
            for z_pos, side in [(0, "south_gable"), (self.depth - WALL_DEPTH_STUDS, "north_gable")]:
                placements.extend(_tile_row(
                    span=gable_length, y_plate=y_plate,
                    x0=x_start, z0=z_pos, along_x=True, rotation=0,
                    color=self.color, comment=f"{prefix} {side} step_{step}",
                ))
        return placements
