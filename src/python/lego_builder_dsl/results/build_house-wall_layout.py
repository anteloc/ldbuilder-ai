"""
build_house.py — Generate a LEGO house with interior walls (no roof) using lego_builder.
Interior walls are built with WallLayout (turtle-style connected wall segments).

House layout (viewed from above, 32 studs wide x 28 studs deep):

  z=28 +---------------------------------+
       |  Living Room  |   Bedroom       |
       |               |                 |
  z=14 |               +-----------------+  <- spine (E-W)
       |               |  Bath | Kitchen |
  z=2  +---------------+-------+---------+
       x=2            x=18              x=30

Outer shell   : 32 w x 28 d, 8 bricks tall, tan bricks
Floor slab    : light-grey plates covering interior
Interior walls: two WallLayouts
  spine_layout  — travels east 16 studs, turns south 12 studs (L-shape)
  east_layout   — travels east 12 studs, turns north 10 studs (L-shape)
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lego_builder"))

from lego_builder import (
    Scene, FloorSlab, WallLayout,
    Color,
    PartType
)

# ── Dimensions ────────────────────────────────────────────────────────────────
HOUSE_W = 32
HOUSE_D = 28
WALL_H  = 8
DOOR_W  = 4
DOOR_H  = 6

# ── Scene ─────────────────────────────────────────────────────────────────────
scene = Scene("lego_house")

# ── Floor slab ────────────────────────────────────────────────────────────────
floor = scene.floor_slab(
    width=HOUSE_W - 4,
    depth=HOUSE_D - 4,
    color=Color.LIGHT_GREY,
    name="floor",
)
scene.add(floor, x=2, y=0, z=2)

# ── Outer shell ───────────────────────────────────────────────────────────────
outer = scene.box(
    width=HOUSE_W,
    depth=HOUSE_D,
    height=WALL_H,
    color=Color.TAN,
    name="outer_shell",
)

outer.south.opening(x=14, y=0, width=DOOR_W, height=DOOR_H)
outer.north.opening(x=14, y=0, width=DOOR_W, height=DOOR_H)
outer.east.opening(x=4,  y=2, width=4, height=4)
outer.east.opening(x=16, y=2, width=4, height=4)
outer.west.opening(x=8,  y=2, width=4, height=4)
outer.west.opening(x=20, y=2, width=4, height=4)

# ── Interior walls — WallLayout 1: L-shaped spine west + south divider ────────
#
# Turtle placed at global (x=2, z=14), starts facing east.
#   build "spine_west" east 16 studs  => covers x=2..18 at z=14
#   turn south
#   build "divider_south" south 12 studs => covers z=14..2 at x=18

spine_layout = WallLayout(
    height=WALL_H,
    color=Color.WHITE,
    name="spine_layout",
    initial_direction="east",
    fill_part=PartType.BRICK_1X4.value,  # use 1x4 bricks for interior walls
)

spine_layout.build_wall("spine_west", length=16)
spine_layout.turn("south")
spine_layout.build_wall("divider_south", length=12)

# Door openings on each named wall
spine_layout["spine_west"].opening(x=10, y=0, width=DOOR_W, height=DOOR_H)
spine_layout["divider_south"].opening(x=4, y=0, width=DOOR_W, height=DOOR_H)

scene.add(spine_layout, x=2, y=0, z=14)

# ── Interior walls — WallLayout 2: spine east + north divider ─────────────────
#
# Turtle placed at global (x=18, z=14), starts facing east.
#   build "spine_east" east 12 studs  => covers x=18..30 at z=14
#   turn north
#   build "divider_north" north 10 studs => covers z=14..24 at x=18

east_layout = WallLayout(
    height=WALL_H,
    color=Color.WHITE,
    name="east_layout",
    initial_direction="east",
    fill_part=PartType.BRICK_1X4.value,  # use 1x4 bricks for interior walls
)

east_layout.build_wall("spine_east", length=12)
east_layout.turn("north")
east_layout.build_wall("divider_north", length=10)

east_layout["spine_east"].opening(x=6, y=0, width=DOOR_W, height=DOOR_H)
east_layout["divider_north"].opening(x=2, y=0, width=DOOR_W, height=DOOR_H)

scene.add(east_layout, x=18, y=0, z=14)

# ── Export ────────────────────────────────────────────────────────────────────
output_path = "lego_house.mpd"
scene.export(output_path)

stats = scene.stats()
print(f"Exported: {output_path}")
print(f"   Total parts  : {stats['total_parts']}")
print(f"   Unique parts : {stats['unique_parts']}")
print(f"   Width        : {stats['width_studs']} studs")
print(f"   Depth        : {stats['depth_studs']} studs")
print(f"   Height       : {stats['height_plates']} plates")
print()
print("Part breakdown:")
for part, count in sorted(stats["part_counts"].items(), key=lambda x: -x[1]):
    print(f"   {count:4d}x  {part}")
