"""
Smoke test: Simple Brick Church
================================
A rectangular nave with tall windows, a gable roof,
and a square bell tower attached to the west end.
Tests: attach with different heights, tall openings, gable roof.
"""

from lego_builder import (
    Scene, Box, Group, FloorSlab, Column, GableRoof,
    PartType, Color, place, attach,
)

scene = Scene("brick_church")

# ── Nave ────────────────────────────────────────────────────────────────
nave = scene.box(20, 10, 10, color=Color.RED, name="nave")

# Tall windows on side walls
nave.south.window_row(y=2, width=2, height=3, count=4,
                       part_type=PartType.WINDOW_1X2X3)
nave.north.window_row(y=2, width=2, height=3, count=4,
                       part_type=PartType.WINDOW_1X2X3)

# Large door on the east end (front entrance)
nave.east.opening(x=3, y=0, width=4, height=6)
nave.east.insert(PartType.DOOR_1X4X6, x=3, y=0)

# Window above door
nave.east.opening(x=3, y=7, width=4, height=3)
nave.east.insert(PartType.WINDOW_1X4X3, x=3, y=7)

nave_group = scene.group("nave_group", [nave])

# Nave roof - steep gable
nave_roof = GableRoof(width=20, depth=10, ridge="east_west",
                       color=Color.DARK_BLUISH_GREY, name="nave_roof")
place(nave_roof, on=nave_group, align="center")

# ── Bell Tower ──────────────────────────────────────────────────────────
# Taller than the nave, attached to the west end
tower = Box(width=8, depth=8, height=16, color=Color.RED, name="tower")

# Belfry openings near the top (arched windows approximated as tall openings)
for wall in [tower.north, tower.south, tower.east, tower.west]:
    wall.opening(x=2, y=12, width=4, height=3)
    wall.insert(PartType.WINDOW_1X4X3, x=2, y=12)

# Small door on the tower's south face
tower.south.opening(x=2, y=0, width=4, height=6)
tower.south.insert(PartType.DOOR_1X4X6, x=2, y=0)

tower_group = Group("tower_group", [tower])

# Flat roof on tower (simple cap)
tower_cap = FloorSlab(8, 8, color=Color.DARK_BLUISH_GREY, name="tower_cap")
place(tower_cap, on=tower_group)

# Attach tower to the west face of the nave, centered
attach(tower_group, to=nave_group, face="west", align="center")

# ── Export ──────────────────────────────────────────────────────────────
output_file = scene.export("/home/claude/ldraw-project/brick_church.mpd")

stats = scene.stats()
print(f"Brick Church: {stats['total_parts']} parts")
print(f"Dimensions: {stats['width_studs']}w x {stats['depth_studs']}d x {stats['height_plates']}h")
print(f"\nPart breakdown:")
for part, count in sorted(stats['part_counts'].items(), key=lambda x: -x[1]):
    print(f"  {part}: {count}")
print(f"\nExported to: {output_file}")
