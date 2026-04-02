"""
build_church.py — Generates a red LEGO church as an LDraw .mpd file.

Uses the lego_builder.py DSL to construct:
  - A main nave (rectangular body) with arched-style windows
  - A front entrance with a large door
  - A bell tower on the front
  - A gable roof over the nave
  - A floor slab foundation

Color scheme: Red walls, dark grey roof, white window trim, tan floor.
"""

from lego_builder import (
    Scene, Color, PartType, place, attach,
    Group, FloorSlab, Column, GableRoof, Box, Wall,
    PLATES_PER_BRICK,
)

# ── Create the scene ──────────────────────────────────────────────
scene = Scene("Red Church")

# ══════════════════════════════════════════════════════════════════
# 1. FOUNDATION — Tan floor slab under the whole building
# ══════════════════════════════════════════════════════════════════
foundation = scene.floor_slab(
    width=24,
    depth=32,
    color=Color.TAN,
    name="foundation",
)

# ══════════════════════════════════════════════════════════════════
# 2. NAVE — The main body of the church  (24 wide × 32 deep × 8 high)
# ══════════════════════════════════════════════════════════════════
nave = scene.box(
    width=24,
    depth=32,
    height=8,
    color=Color.RED,
    name="nave",
)

# ── Side windows on the east wall (3 tall windows) ──
nave.east.window_row(
    y=2, width=2, height=3, count=3,
    part_type=PartType.WINDOW_1X2X3,
    color=Color.TRANS_LIGHT_BLUE,
)

# ── Side windows on the west wall (3 tall windows) ──
nave.west.window_row(
    y=2, width=2, height=3, count=3,
    part_type=PartType.WINDOW_1X2X3,
    color=Color.TRANS_LIGHT_BLUE,
)

# ── Rear window on the north wall (1 large window, centered) ──
nave.north.window_row(
    y=3, width=4, height=3, count=1,
    part_type=PartType.WINDOW_1X4X3,
    color=Color.TRANS_LIGHT_BLUE,
)

# ── Front entrance door on the south wall ──
nave.south.opening(x=10, y=0, width=4, height=6)
nave.south.insert(PartType.DOOR_1X4X6, x=10, y=0, color=Color.REDDISH_BROWN)

# ── Front windows flanking the door on the south wall ──
nave.south.opening(x=3, y=2, width=2, height=2)
nave.south.insert(PartType.WINDOW_1X2X2, x=3, y=2, color=Color.TRANS_LIGHT_BLUE)

nave.south.opening(x=19, y=2, width=2, height=2)
nave.south.insert(PartType.WINDOW_1X2X2, x=19, y=2, color=Color.TRANS_LIGHT_BLUE)

# ── Decorative ledge / cornice at the top of the nave ──
for wall in nave.walls():
    wall.ledge(y=8, overhang=1, color=Color.DARK_RED)

# ── Place nave on foundation ──
building = place(nave, on=foundation, align="center")

# ══════════════════════════════════════════════════════════════════
# 3. ROOF — Gable roof over the nave
# ══════════════════════════════════════════════════════════════════
roof = GableRoof(
    width=26,      # slightly wider than nave for overhang
    depth=34,      # slightly deeper for overhang
    ridge="east_west",
    color=Color.DARK_BLUISH_GREY,
    name="church_roof",
)

# Stack roof on top of the nave (on the building group)
# The nave sits at y=1 plate (foundation height), walls are 8 bricks = 24 plates
# Plus 1 plate for cornice ledge = 25 plates above foundation
# Foundation is 1 plate. Total Y for roof base = 1 + 24 = 25 plates
roof_y = foundation.height_plates + nave.height_plates
building.add(roof, x=-1, y=roof_y, z=-1)  # offset by -1 for overhang

# ══════════════════════════════════════════════════════════════════
# 4. BELL TOWER — Square tower on the front-left of the church
# ══════════════════════════════════════════════════════════════════
tower = Box(
    width=8,
    depth=8,
    height=14,     # taller than the nave
    color=Color.RED,
    name="tower",
)

# ── Tower windows (small, on each side) ──
tower.south.window_row(
    y=8, width=2, height=2, count=1,
    part_type=PartType.WINDOW_1X2X2,
    color=Color.TRANS_LIGHT_BLUE,
)
tower.east.window_row(
    y=8, width=2, height=2, count=1,
    part_type=PartType.WINDOW_1X2X2,
    color=Color.TRANS_LIGHT_BLUE,
)
tower.west.window_row(
    y=8, width=2, height=2, count=1,
    part_type=PartType.WINDOW_1X2X2,
    color=Color.TRANS_LIGHT_BLUE,
)
tower.north.window_row(
    y=8, width=2, height=2, count=1,
    part_type=PartType.WINDOW_1X2X2,
    color=Color.TRANS_LIGHT_BLUE,
)

# ── Tower top ledge ──
for wall in tower.walls():
    wall.ledge(y=14, overhang=1, color=Color.DARK_RED)

# ── Tower roof (small gable) ──
tower_roof = GableRoof(
    width=10,
    depth=10,
    ridge="east_west",
    color=Color.DARK_BLUISH_GREY,
    name="tower_roof",
)

tower_with_roof = place(tower_roof, on=tower, align="center")

# Place the tower at the front-left of the church
# Foundation is at y=0, tower sits on foundation level
tower_y = foundation.height_plates
building.add(tower_with_roof, x=-2, y=tower_y, z=-2)

# ══════════════════════════════════════════════════════════════════
# 5. EXPORT
# ══════════════════════════════════════════════════════════════════
scene.add(building)

output_file = "red_church.mpd"
scene.export(output_file)

# Print stats
stats = scene.stats()
print(f"Church model exported to: {output_file}")
print(f"Total parts: {stats['total_parts']}")
print(f"Unique part types: {stats['unique_parts']}")
print(f"Approximate dimensions: {stats['width_studs']}W × {stats['depth_studs']}D × {stats['height_plates']}H (studs/plates)")
print("\nPart breakdown:")
for part_name, count in sorted(stats['part_counts'].items(), key=lambda x: -x[1]):
    print(f"  {part_name}: {count}")
