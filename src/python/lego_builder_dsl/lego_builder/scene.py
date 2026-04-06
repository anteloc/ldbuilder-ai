"""
Scene: top-level container and LDraw exporter.

The Scene is the top-level container. It holds all elements and
exports the final LDraw .mpd file.

Usage:
  scene = Scene("my_building")
  box = scene.box(24, 16, 10)
  ...
  scene.export("output.mpd")

The Scene provides factory methods (scene.box(), scene.wall(), etc.)
so all elements are automatically tracked. Elements can also be
added manually with scene.add().
"""

from __future__ import annotations

from typing import Literal

from .parts import PartType, Color
from .core import BrickPlacement
from .wall import Wall
from .structures import Box, FloorSlab, Column, WallLayout
from .roof import GableRoof
from .assembly import Group


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
        fill_part: PartType = PartType.BRICK_2X4,
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
        b = Box(width=width, depth=depth, height=height, color=color, fill_part=fill_part.value, name=name)
        self._root.add(b)
        return b

    def wall(
        self,
        length: int,
        height: int,
        facing: str,
        color: int = Color.WHITE,
        fill_part: PartType = PartType.BRICK_2X4,
        name: str = "",
    ) -> Wall:
        """Create a standalone Wall and add it to the scene."""
        w = Wall(length=length, height=height, facing=facing, color=color, fill_part=fill_part.value, name=name)
        self._root.add(w)
        return w
    
    def wall_layout(
        self,
        height: int,
        color: int = Color.WHITE,
        fill_part: PartType = PartType.BRICK_2X4,
        name: str = "",
        initial_direction: Literal["north", "south", "east", "west"] = "east",
    ) -> WallLayout:
        """Create an arbitrary layout of N walls with named accessors.
        Args:
            name: Identifier for LDraw comments.
            height: Walls uniform height in brick rows.
            color: Default LDraw color for all walls.
            fill_part: PartType used to fill the walls (e.g. BRICK_2X4).
            initial_direction: Initial direction for the first wall.
        Returns:
            The created WallLayout (already added to scene), walls can be added and concatenated along a continuous path
            by calling wall_layout.turn(direction) and wall_layout.build_wall(wall_name, length_in_studs), successively.            
        """

        wl = WallLayout(
            height=height,
            color=color,
            fill_part=fill_part.value,
            name=name,
            initial_direction=initial_direction,
        )
        self._root.add(wl)
        return wl

    def floor_slab(
        self,
        width: int,
        depth: int,
        color: int = Color.LIGHT_GREY,
        fill_part: PartType = PartType.PLATE_2X4,
        name: str = "",
    ) -> FloorSlab:
        """Create a FloorSlab and add it to the scene."""
        f = FloorSlab(width=width, depth=depth, color=color, fill_part=fill_part.value, name=name)
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
          0 FILE <n>.ldr
          0 <n>
          0 Name: <n>.ldr
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
