"""
Core data classes: BuilderError and BrickPlacement.

These are the foundational types used throughout the builder.
BrickPlacement is the universal output format — every element's
to_placements() method returns a list of these.
"""

from __future__ import annotations

from dataclasses import dataclass

from .coords import to_ldraw_coords, ROTATION_MATRICES
from .parts import Part, Color


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
        part = self.part
        rotation = self.rotation % 360
        if rotation in (90, 270):
            rotated_width_studs = part.depth_studs
            rotated_depth_studs = part.width_studs
        else:
            rotated_width_studs = part.width_studs
            rotated_depth_studs = part.depth_studs

        lx, ly, lz = to_ldraw_coords(
            self.x + rotated_width_studs * 0.5,
            self.y + part.height_plates, # LDraw parts local origins are at the top studs region, y + height places the top at the height
            self.z + rotated_depth_studs * 0.5,
        )
        matrix = ROTATION_MATRICES.get(rotation, ROTATION_MATRICES[0])

        lines = []
        if self.comment:
            lines.append(f"0 // {self.comment}")
        lines.append(f"1 {self.color} {lx:.1f} {ly:.1f} {lz:.1f} {matrix} {part.filename}")
        return "\n".join(lines)
