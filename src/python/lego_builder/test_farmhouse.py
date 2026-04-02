"""
Smoke test: White Colonial Farmhouse
=====================================
This script builds a LEGO model of the white colonial farmhouse
(building 6 from our analysis) using the lego_builder DSL.

This is written as an LLM would generate it — using the DSL primitives
to describe the building from the image.

The building has:
  - Two stories, rectangular footprint
  - Ground floor: centered door, two flanking windows with shutters
  - Second floor: three evenly spaced windows with shutters
  - Gable roof with east-west ridge
  - Small front portico over the door
  - Chimney on the right side
"""

from lego_builder import (
    Scene, Box, Group, FloorSlab, Column, GableRoof,
    PartType, Color, place, attach,
)

scene = Scene("colonial_farmhouse")

# ── Foundation ──────────────────────────────────────────────────────────
foundation = scene.floor_slab(24, 14, color=Color.LIGHT_GREY, name="foundation")

# ── First Floor ─────────────────────────────────────────────────────────
floor1 = scene.box(24, 14, 8, color=Color.WHITE, name="floor1")

# Front (south) wall: door centered, two flanking windows
floor1.south.opening(x=10, y=0, width=4, height=6)
floor1.south.insert(PartType.DOOR_1X4X6, x=10, y=0)
floor1.south.window_row(y=2, width=4, height=3, count=2,
                         part_type=PartType.WINDOW_1X4X3, spacing=14)

# Back (north) wall: three windows
floor1.north.window_row(y=2, width=4, height=3, count=3,
                         part_type=PartType.WINDOW_1X4X3)

# Side walls: two windows each
floor1.east.window_row(y=2, width=4, height=3, count=2,
                        part_type=PartType.WINDOW_1X4X3)
floor1.west.window_row(y=2, width=4, height=3, count=2,
                        part_type=PartType.WINDOW_1X4X3)

# Floor divider (ceiling of first floor)
ceiling1 = FloorSlab(24, 14, color=Color.LIGHT_GREY, name="ceiling1")

# Group first floor
floor1_group = Group("first_floor", [foundation, floor1, ceiling1])
# Position ceiling at top of walls
floor1_group.children[-1] = (ceiling1, 0, floor1.height_plates, 0)

# ── Second Floor ────────────────────────────────────────────────────────
floor2 = Box(24, 14, 8, color=Color.WHITE, name="floor2")

# Front: three windows evenly spaced
floor2.south.window_row(y=2, width=4, height=3, count=3,
                         part_type=PartType.WINDOW_1X4X3)

# Back: three windows
floor2.north.window_row(y=2, width=4, height=3, count=3,
                         part_type=PartType.WINDOW_1X4X3)

# Sides: two windows each
floor2.east.window_row(y=2, width=4, height=3, count=2,
                        part_type=PartType.WINDOW_1X4X3)
floor2.west.window_row(y=2, width=4, height=3, count=2,
                        part_type=PartType.WINDOW_1X4X3)

floor2_group = Group("second_floor", [floor2])
building = place(floor2_group, on=floor1_group, align="center")

# ── Roof ────────────────────────────────────────────────────────────────
roof = GableRoof(
    width=24, depth=14,
    ridge="east_west",
    color=Color.DARK_BLUISH_GREY,
    name="main_roof",
)
place(roof, on=building, align="center")

# ── Front Portico ───────────────────────────────────────────────────────
# Small porch over the front door: floor slab + two columns + flat roof

porch_floor = FloorSlab(8, 3, color=Color.LIGHT_GREY, name="porch_floor")
col_left = Column(height=6, color=Color.WHITE, name="porch_col_l")
col_right = Column(height=6, color=Color.WHITE, name="porch_col_r")
porch_roof = FloorSlab(8, 3, color=Color.DARK_BLUISH_GREY, name="porch_roof")

portico = Group("portico")
portico.add(porch_floor, x=0, y=0, z=0)
portico.add(col_left, x=0, y=1, z=0)       # columns sit on the floor plate
portico.add(col_right, x=7, y=1, z=0)       # right column at far end
portico.add(porch_roof, x=0, y=19, z=0)     # roof at top of columns (6 rows * 3 + 1)

# Attach portico to south face of building, centered on door
attach(portico, to=building, face="south", align="center")

# ── Chimney ─────────────────────────────────────────────────────────────
# Small chimney on the right side of the roof
chimney = Group("chimney")
for facing in ["north", "south", "east", "west"]:
    from lego_builder import Wall, PLATES_PER_BRICK
    length = 2
    w = Wall(length=length, height=4, facing=facing,
             color=Color.REDDISH_BROWN, name=f"chimney_{facing}")
    chimney.add(w, x=0, y=0, z=0)

# Place chimney on top of building at an offset toward the east side
# Building height: foundation(1) + floor1(24) + floor2(24) + some roof
# We'll place it high using at_level
total_wall_height = 1 + floor1.height_plates + floor2.height_plates
place(chimney, on=building, align="center", offset=(8, 0))


# ── Export ──────────────────────────────────────────────────────────────
output_file = scene.export("/home/claude/ldraw-project/colonial_farmhouse.mpd")

# Print summary
stats = scene.stats()
print(f"Colonial Farmhouse: {stats['total_parts']} parts")
print(f"Dimensions: {stats['width_studs']}w x {stats['depth_studs']}d x {stats['height_plates']}h")
print(f"\nPart breakdown:")
for part, count in sorted(stats['part_counts'].items(), key=lambda x: -x[1]):
    print(f"  {part}: {count}")
print(f"\nExported to: {output_file}")
