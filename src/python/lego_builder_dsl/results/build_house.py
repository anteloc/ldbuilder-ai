"""
build_house.py — Generate a LEGO house with interior walls (no roof) using lego_builder.

House layout (viewed from above, 32 studs wide x 28 studs deep):
  ┌──────────────────────────────────┐
  │  Living Room  │   Bedroom        │
  │               │                  │
  │               ├──────┬───────────│
  │               │  Bath │  Kitchen  │
  └───────────────┴───────┴──────────┘
  South                              North

Outer shell : 32 w × 28 d, 8 bricks tall (tan bricks)
Floor slab  : light-grey plates covering interior
Interior walls divide the space into 4 rooms:
  - Longitudinal spine wall running E-W at z=14 (splits north/south)
  - Transverse wall running N-S at x=18  (splits east/west on north half)
  - Short stub wall running N-S at x=18 on south half (partial, creates
    a wide living-room + narrow bath entry)
"""

import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lego_builder"))

from lego_builder import (
    Scene, Box, FloorSlab, Wall,
    Color, PartType,
    place, attach,
)

# ── Dimensions ───────────────────────────────────────────────────────────────
HOUSE_W    = 32   # studs east-west
HOUSE_D    = 28   # studs north-south
WALL_H     = 8    # bricks tall (outer walls)
INNER_H    = 8    # bricks tall (inner walls, same height)

# Door-opening parameters (width × height in studs/plates)
DOOR_W     = 4    # studs wide
DOOR_H     = 6    # plates tall (2 bricks)

# ── Scene ─────────────────────────────────────────────────────────────────────
scene = Scene("lego_house")

# ── Floor slab (full interior footprint, under everything) ────────────────────
# Inset by 2 studs on each side to sit inside the 2-stud-deep outer walls
floor = scene.floor_slab(
    width=HOUSE_W - 4,
    depth=HOUSE_D - 4,
    color=Color.LIGHT_GREY,
    name="floor",
)
# Place floor at y=0, offset inward so it sits inside the outer walls
scene.add(floor, x=2, y=0, z=2)

# ── Outer shell ───────────────────────────────────────────────────────────────
outer = scene.box(
    width=HOUSE_W,
    depth=HOUSE_D,
    height=WALL_H,
    color=Color.TAN,
    name="outer_shell",
)

# Front (south) door opening — centred at x=14, y=0
outer.south.opening(x=14, y=0, width=DOOR_W, height=DOOR_H)

# Back (north) door opening
outer.north.opening(x=14, y=0, width=DOOR_W, height=DOOR_H)

# Windows on east wall — two windows, one per room
outer.east.opening(x=4,  y=2, width=4, height=4)   # bedroom window
outer.east.opening(x=16, y=2, width=4, height=4)   # kitchen window

# Windows on west wall — one for living room
outer.west.opening(x=8,  y=2, width=4, height=4)   # living room window
outer.west.opening(x=20, y=2, width=4, height=4)   # bathroom window

# Place outer box at origin (default)
# scene.add() was called implicitly by scene.box()

# ── Interior walls ────────────────────────────────────────────────────────────

# 1) East-West spine wall: divides house into north and south halves
#    Runs along X from x=2 (inside west wall) to x=30 (inside east wall)
#    Sits at z=14 (middle of the 28-stud depth)
#    Length = HOUSE_W - 4 = 28 studs (inside the outer walls)
spine_wall = Wall(
    length=HOUSE_W - 4,   # 28 studs
    height=INNER_H,
    facing="south",       # face visible from south (interior)
    color=Color.WHITE,
    name="spine_wall",
)
# Add a doorway in the spine wall connecting south rooms to north rooms
# Centred at x=10 of the wall (global x≈12)
spine_wall.opening(x=10, y=0, width=DOOR_W, height=DOOR_H)
# Second doorway connecting living area to kitchen
spine_wall.opening(x=20, y=0, width=DOOR_W, height=DOOR_H)

scene.add(spine_wall, x=2, y=0, z=14)

# 2) North-South divider: splits east half into bedroom (south) and kitchen (north)
#    Runs along Z in the south half from z=2 to z=14
#    Sits at x=18
divider_south = Wall(
    length=12,            # covers z=2..14 inside
    height=INNER_H,
    facing="east",        # face visible from east
    color=Color.WHITE,
    name="divider_south",
)
# Door from living room to bedroom corridor
divider_south.opening(x=4, y=0, width=DOOR_W, height=DOOR_H)
scene.add(divider_south, x=18, y=0, z=2)

# 3) North-South divider: splits east half into kitchen (east) and bathroom (west)
#    in the north half, from z=16 to z=26 (inside north wall)
divider_north = Wall(
    length=10,
    height=INNER_H,
    facing="east",
    color=Color.WHITE,
    name="divider_north",
)
# Bathroom door opening
divider_north.opening(x=2, y=0, width=DOOR_W, height=DOOR_H)
scene.add(divider_north, x=18, y=0, z=16)

# ── Export ────────────────────────────────────────────────────────────────────
output_path = "/home/claude/lego_house.mpd"
scene.export(output_path)

stats = scene.stats()
print(f"✅  Exported: {output_path}")
print(f"   Total parts  : {stats['total_parts']}")
print(f"   Unique parts : {stats['unique_parts']}")
print(f"   Width        : {stats['width_studs']} studs")
print(f"   Depth        : {stats['depth_studs']} studs")
print(f"   Height       : {stats['height_plates']} plates")
print()
print("Part breakdown:")
for part, count in sorted(stats["part_counts"].items(), key=lambda x: -x[1]):
    print(f"   {count:4d}×  {part}")
