"""
lego_builder — A Python-embedded DSL for generating LEGO LDraw models.

An LLM generates Python scripts using this library's primitives (box, wall,
floor_slab, column, group, place, attach, gable_roof) and the library
handles all geometric correctness, brick tiling, and LDraw export.

Architecture:
  - Everything uses stud units (X, Z) and plate units (Y) internally.
  - LDraw coordinate conversion happens only at export time.
  - Walls store a boolean grid; brick tiling is computed at export.
  - Each class has a to_placements() method returning BrickPlacement lists.
  - Scene collects all placements and writes a single .mpd file.

Package structure:
  coords.py     — Coordinate constants, conversion, rotation matrices
  parts.py      — PartType enum, Part catalog, Color constants
  core.py       — BuilderError, BrickPlacement
  wall.py       — Wall class (grid, openings, tiling)
  structures.py — Box, FloorSlab, Column
  roof.py       — GableRoof, _tile_row helper
  assembly.py   — Group, place(), attach(), Element type
  scene.py      — Scene (top-level container + LDraw export)
"""

# Coordinates
from .coords import (
    LDU_PER_STUD,
    LDU_PER_PLATE,
    PLATES_PER_BRICK,
    to_ldraw_coords,
    ROTATION_MATRICES,
    FACING_TO_ROTATION,
)

# Parts & Colors
from .parts import (
    PartType,
    Part,
    PARTS,
    FILL_BRICKS,
    find_part,
    Color,
)

# Core types
from .core import (
    BuilderError,
    BrickPlacement,
)

# Wall
from .wall import (
    WALL_DEPTH_STUDS,
    Wall,
)

# Structures
from .structures import (
    WallLayout,
    Box,
    FloorSlab,
    Column,
)

# Roof
from .roof import (
    GableRoof,
)

# Assembly
from .assembly import (
    Group,
    Element,
    place,
    attach,
)

# Scene
from .scene import (
    Scene,
)
