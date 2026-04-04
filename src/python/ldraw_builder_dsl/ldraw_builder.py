"""
Programmatic LDraw model builder.

Provides a simple API for assembling LDraw/LEGO models in Python scripts.
Outputs valid LDraw .ldr format (UTF-8, CRLF line endings per spec).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COORDINATE SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LDraw uses a right-handed coordinate system where -Y is "up":
  +X = right
  -Y = up  (more negative Y = higher in the scene)
  +Z = toward the viewer

All position arguments (x, y, z) in this module use LDraw coordinates.
Use ldraw_units helpers to avoid raw LDU arithmetic:
  stud(n)   — n × 20 LDU  (horizontal stud grid offset)
  brick(n)  — n × 28 LDU  (full brick height incl. stud)
  plate(n)  — n × 12 LDU  (full plate height incl. stud)

Typical usage: y=0 at ground level, more-negative y = higher up.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART ORIGIN CONVENTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Standard LDraw bricks/plates have their origin at the top-centre of
the brick body (the stud base ring level). Studs extend upward from
there (to y − STUD_HEIGHT), and the body extends downward
(to y + (height − STUD_HEIGHT)).

place_on() relies on this convention to compute the correct stacking Y.
Non-standard parts (technic pieces, decorative elements, etc.) may have
a different origin and may require manual placement via place() instead.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUICK EXAMPLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    from ldraw_builder import Model
    from ldraw_parts  import find_part
    from ldraw_units  import stud

    m = Model("Simple Stack")

    # Find parts via RAG, then place them
    brick_2x4 = find_part("2x4 brick", backend="nomic-embed-text:v1.5")
    brick_1x2 = find_part("1x2 brick", backend="nomic-embed-text:v1.5")

    base   = m.place(brick_2x4, color=4,  x=0, y=0, z=0)
    left   = m.place_on(brick_1x2, color=1,  on=base, dx=stud(-1))
    right  = m.place_on(brick_1x2, color=14, on=base, dx=stud(1))
    top    = m.place_on(brick_2x4, color=15, on=left)

    m.save("stack.ldr")

    # Or use a PartInfo directly from a known filename (no RAG needed):
    from ldraw_parts import PartInfo
    plate = PartInfo(file="3020.dat", description="Plate 2x4", width=80, height=12, depth=40)
    m.place(plate, color=6, x=0, y=0, z=0)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from ldraw_rotation import Matrix3x3, from_euler, identity
from ldraw_units    import STUD_HEIGHT


# ── PartSpec ───────────────────────────────────────────────────────────────────
# Accepts either a ldraw_parts.PartInfo or a bare .dat filename string.
# When a bare string is used, width/height/depth must be supplied to place_on().
PartSpec = Union["PartInfo", str]   # type: ignore[name-defined]  (forward ref)


def _resolve(
    part:   PartSpec,
    width:  float,
    height: float,
    depth:  float,
) -> tuple[str, float, float, float]:
    """
    Extract (file, width, height, depth) from a PartSpec.

    Explicit dimension arguments override those from PartInfo so callers can
    correct chunks.md values for non-standard parts if needed.
    """
    try:
        # Duck-type: works with ldraw_parts.PartInfo without a hard import
        file = part.file                                 # type: ignore[union-attr]
        w = width  if width  > 0 else part.width        # type: ignore[union-attr]
        h = height if height > 0 else part.height       # type: ignore[union-attr]
        d = depth  if depth  > 0 else part.depth        # type: ignore[union-attr]
    except AttributeError:
        # Bare filename string — dimensions must be provided by the caller
        file = str(part)
        w, h, d = width, height, depth

    return file, float(w), float(h), float(d)


# ── PlacedPart ─────────────────────────────────────────────────────────────────

@dataclass
class PlacedPart:
    """
    A part that has been added to a Model.

    Returned by Model.place() and Model.place_on(). Pass as the `on` argument
    to place_on() to stack subsequent parts on top of this one.

    All coordinates are in LDraw space (-Y is up).
    """
    file:   str         # .dat filename
    color:  int         # LDraw colour code
    x:      float       # world X in LDU
    y:      float       # world Y in LDU (more negative = higher up)
    z:      float       # world Z in LDU
    matrix: Matrix3x3   # row-major 3×3 rotation matrix
    width:  float       # bounding box X in LDU
    height: float       # bounding box Y in LDU (full height incl. stud)
    depth:  float       # bounding box Z in LDU

    def _ldraw_line(self) -> str:
        """Format as a LDraw Type-1 sub-file reference line."""
        flat = " ".join(f"{v:.10g}" for row in self.matrix for v in row)
        return f"1 {self.color} {self.x:.10g} {self.y:.10g} {self.z:.10g} {flat} {self.file}"


# ── Model ──────────────────────────────────────────────────────────────────────

class Model:
    """
    A programmatic LDraw model builder.

    Parts are added via place() (absolute position) or place_on() (relative,
    stacked on top of an existing part). Both return a PlacedPart handle that
    can be passed to subsequent place_on() calls to keep stacking.

    Call save() or to_ldraw() when done.
    """

    def __init__(self, name: str = "Untitled", description: str = ""):
        self.name:        str             = name
        self.description: str             = description or name
        self._parts:      list[PlacedPart] = []

    # ── Placement ──────────────────────────────────────────────────────────────

    def place(
        self,
        part:   PartSpec,
        *,
        color:  int,
        x:      float = 0.0,
        y:      float = 0.0,
        z:      float = 0.0,
        yaw:    float = 0.0,
        pitch:  float = 0.0,
        roll:   float = 0.0,
        width:  float = 0.0,
        height: float = 0.0,
        depth:  float = 0.0,
    ) -> PlacedPart:
        """
        Place a part at an absolute position (LDraw coordinates, -Y is up).

        part   — a PartInfo from ldraw_parts.find_part(), or a bare .dat filename
        color  — LDraw colour code (e.g. 4 = red, 1 = blue, 15 = white, 0 = black)
        x,y,z  — world position in LDU; y=0 is ground level, more-negative y = higher
        yaw    — rotation around Y in degrees (turn left/right)
        pitch  — rotation around X in degrees (tilt forward/back)
        roll   — rotation around Z in degrees (tilt sideways)
        width, height, depth — override bounding box dimensions in LDU;
                               only needed when part is a bare filename string
        """
        file, w, h, d = _resolve(part, width, height, depth)
        matrix = from_euler(yaw=yaw, pitch=pitch, roll=roll)
        p = PlacedPart(file=file, color=color, x=x, y=y, z=z, matrix=matrix,
                       width=w, height=h, depth=d)
        self._parts.append(p)
        return p

    def place_on(
        self,
        part:   PartSpec,
        *,
        color:  int,
        on:     PlacedPart,
        dx:     float = 0.0,
        dz:     float = 0.0,
        yaw:    float = 0.0,
        pitch:  float = 0.0,
        roll:   float = 0.0,
        width:  float = 0.0,
        height: float = 0.0,
        depth:  float = 0.0,
    ) -> PlacedPart:
        """
        Place a part on top of an existing part.

        Y is computed automatically from the base part's bounding height:
            new_y = on.y − (on.height − STUD_HEIGHT)

        This positions the new part's origin flush with the top face of `on`,
        which is the standard LDraw stacking connection point.

        on     — the PlacedPart to stack on top of (returned by place/place_on)
        dx, dz — horizontal offset from the base part's centre in LDU;
                 use stud(n) from ldraw_units for grid-aligned offsets
        yaw, pitch, roll — rotation in degrees (same as place())
        width, height, depth — override bounding box dimensions (bare filenames only)
        """
        file, w, h, d = _resolve(part, width, height, depth)
        matrix = from_euler(yaw=yaw, pitch=pitch, roll=roll)

        # In LDraw, -Y is up. The top face of `on` is one body-height above
        # its origin, i.e. (on.height − STUD_HEIGHT) LDU in the -Y direction.
        new_y = on.y - (on.height - STUD_HEIGHT)

        p = PlacedPart(
            file=file, color=color,
            x=on.x + dx, y=new_y, z=on.z + dz,
            matrix=matrix, width=w, height=h, depth=d,
        )
        self._parts.append(p)
        return p

    # ── Output ─────────────────────────────────────────────────────────────────

    def to_ldraw(self) -> str:
        """
        Render the model as an LDraw .ldr file string.

        Uses CRLF line endings as required by the LDraw file format spec.
        """
        lines = [
            f"0 {self.description}",
            f"0 Name: {self.name}",
            f"0 Author: ldraw_builder",
            "0",
        ]
        for p in self._parts:
            lines.append(p._ldraw_line())

        return "\r\n".join(lines) + "\r\n"

    def save(self, path: Union[str, Path]) -> None:
        """Write the model to a .ldr file (UTF-8)."""
        out = Path(path)
        out.write_text(self.to_ldraw(), encoding="utf-8")
        print(f"Saved {len(self._parts)} part(s) → {out}")

    def __len__(self) -> int:
        return len(self._parts)

    def __repr__(self) -> str:
        return f"Model({self.name!r}, {len(self._parts)} parts)"
