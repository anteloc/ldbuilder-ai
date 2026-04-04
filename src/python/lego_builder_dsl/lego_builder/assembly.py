"""
Assembly primitives: Group, place(), attach(), and Element type.

Group bundles elements with a shared coordinate space.
place() positions one element on top of another.
attach() positions one element beside another.

These are the spatial relationship verbs in the DSL:
  - "on top of" → place()
  - "next to"   → attach()
"""

from __future__ import annotations

from typing import Any

from .coords import PLATES_PER_BRICK
from .parts import Color
from .core import BuilderError, BrickPlacement
from .wall import Wall
from .structures import Box, FloorSlab, Column
from .roof import GableRoof


# ---------------------------------------------------------------------------
# Element type alias
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
# Group Class
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
# Placement Functions — place() and attach()
# ---------------------------------------------------------------------------

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
