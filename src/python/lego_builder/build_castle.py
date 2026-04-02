"""
build_castle.py — Generates a medieval LEGO castle as an LDraw .mpd file.

Inspired by a classic medieval castle with:
  - Green baseplate foundation
  - Curtain walls (front and back) with battlements
  - Four corner towers (square, tall)
  - A central gatehouse with large door on the front wall
  - A tall central keep/tower rising above the rest
  - An interior building (great hall) with a gable roof
  - Gable roofs on the corner towers and keep

Color scheme: Light bluish grey walls, dark bluish grey roofs,
             dark grey accents, green base, reddish brown doors.
"""

from lego_builder import (
    Scene, Color, PartType, place, attach,
    Group, FloorSlab, Column, GableRoof, Box, Wall,
    PLATES_PER_BRICK, WALL_DEPTH_STUDS,
)

scene = Scene("Medieval Castle")

# ══════════════════════════════════════════════════════════════════
# COLOR PALETTE
# ══════════════════════════════════════════════════════════════════
WALL_COLOR = Color.LIGHT_BLUISH_GREY
ACCENT_COLOR = Color.DARK_BLUISH_GREY
ROOF_COLOR = Color.DARK_BLUISH_GREY
BASE_COLOR = Color.GREEN
FLOOR_COLOR = Color.DARK_GREY
DOOR_COLOR = Color.REDDISH_BROWN
WINDOW_COLOR = Color.TRANS_CLEAR

# ══════════════════════════════════════════════════════════════════
# DIMENSIONS (in studs / brick-rows)
# ══════════════════════════════════════════════════════════════════
# Overall castle footprint
CASTLE_W = 48          # east-west
CASTLE_D = 48          # north-south

# Curtain walls
CURTAIN_H = 6          # brick rows tall

# Corner towers
TOWER_SIZE = 10        # square footprint
TOWER_H = 10           # brick rows

# Central keep
KEEP_W = 14
KEEP_D = 14
KEEP_H = 16            # tallest structure

# Interior great hall
HALL_W = 16
HALL_D = 24
HALL_H = 7

# ══════════════════════════════════════════════════════════════════
# 1. GREEN BASEPLATE
# ══════════════════════════════════════════════════════════════════
baseplate = scene.floor_slab(
    width=CASTLE_W + 4,
    depth=CASTLE_D + 4,
    color=BASE_COLOR,
    name="baseplate",
)

# A second layer for elevation (tan/dark tan ground level)
ground = FloorSlab(
    width=CASTLE_W,
    depth=CASTLE_D,
    color=Color.DARK_TAN,
    name="ground",
)

castle_group = Group("castle")

# Place ground on baseplate centered
base_assembly = place(ground, on=baseplate, align="center")

# ══════════════════════════════════════════════════════════════════
# 2. CURTAIN WALLS — South (front), North (back), East, West
# ══════════════════════════════════════════════════════════════════
# The curtain walls connect the corner towers. They span the gap
# between towers (CASTLE_W - 2*TOWER_SIZE on each side).

WALL_SPAN_EW = CASTLE_W - 2 * TOWER_SIZE   # 28 studs for east-west walls
WALL_SPAN_NS = CASTLE_D - 2 * TOWER_SIZE   # 28 studs for north-south walls

# ── South wall (front) — has gatehouse door ──
south_wall = Wall(
    length=WALL_SPAN_EW,
    height=CURTAIN_H,
    facing="south",
    color=WALL_COLOR,
    name="south_curtain",
)
# Large gate opening in center
gate_w = 4
gate_h = 6   # full height door
gate_x = (WALL_SPAN_EW - gate_w) // 2
south_wall.opening(x=gate_x, y=0, width=gate_w, height=gate_h)
south_wall.insert(PartType.DOOR_1X4X6, x=gate_x, y=0, color=DOOR_COLOR)

# Small windows flanking the gate
sw_x1 = 4
sw_x2 = WALL_SPAN_EW - 6
south_wall.opening(x=sw_x1, y=2, width=2, height=2)
south_wall.insert(PartType.WINDOW_1X2X2, x=sw_x1, y=2, color=WINDOW_COLOR)
south_wall.opening(x=sw_x2, y=2, width=2, height=2)
south_wall.insert(PartType.WINDOW_1X2X2, x=sw_x2, y=2, color=WINDOW_COLOR)

# ── North wall (back) ──
north_wall = Wall(
    length=WALL_SPAN_EW,
    height=CURTAIN_H,
    facing="north",
    color=WALL_COLOR,
    name="north_curtain",
)
north_wall.window_row(
    y=2, width=2, height=2, count=3,
    part_type=PartType.WINDOW_1X2X2,
    color=WINDOW_COLOR,
)

# ── East wall ──
east_wall = Wall(
    length=WALL_SPAN_NS,
    height=CURTAIN_H,
    facing="east",
    color=WALL_COLOR,
    name="east_curtain",
)
east_wall.window_row(
    y=2, width=2, height=2, count=3,
    part_type=PartType.WINDOW_1X2X2,
    color=WINDOW_COLOR,
)

# ── West wall ──
west_wall = Wall(
    length=WALL_SPAN_NS,
    height=CURTAIN_H,
    facing="west",
    color=WALL_COLOR,
    name="west_curtain",
)
west_wall.window_row(
    y=2, width=2, height=2, count=3,
    part_type=PartType.WINDOW_1X2X2,
    color=WINDOW_COLOR,
)

# Add ledges (battlements effect) at the top of each curtain wall
for w in [south_wall, north_wall, east_wall, west_wall]:
    w.ledge(y=CURTAIN_H, overhang=1, color=ACCENT_COLOR)

# ── Position curtain walls ──
# Walls sit on the ground slab. Ground is at y=0 within castle_group,
# walls placed at ground level after the baseplate+ground assembly.
ground_y = baseplate.height_plates + ground.height_plates  # 2 plates up

# South wall: along the south edge, between SW and SE towers
castle_group.add(south_wall, x=TOWER_SIZE, y=ground_y, z=0)

# North wall: along the north edge
castle_group.add(north_wall, x=TOWER_SIZE, y=ground_y, z=CASTLE_D - WALL_DEPTH_STUDS)

# West wall: along the west edge
castle_group.add(west_wall, x=0, y=ground_y, z=TOWER_SIZE)

# East wall: along the east edge
castle_group.add(east_wall, x=CASTLE_W - WALL_DEPTH_STUDS, y=ground_y, z=TOWER_SIZE)


# ══════════════════════════════════════════════════════════════════
# 3. CORNER TOWERS — four square towers at each corner
# ══════════════════════════════════════════════════════════════════
def make_corner_tower(name: str) -> Group:
    """Create a corner tower with windows and a gable roof."""
    tower = Box(
        width=TOWER_SIZE,
        depth=TOWER_SIZE,
        height=TOWER_H,
        color=WALL_COLOR,
        name=name,
    )
    # Windows on two visible faces (south and east for SE tower, etc.)
    # We'll add windows to all four sides and let positioning handle visibility
    for wall in tower.walls():
        wall.window_row(
            y=5, width=2, height=2, count=1,
            part_type=PartType.WINDOW_1X2X2,
            color=WINDOW_COLOR,
        )
        # Battlement ledge
        wall.ledge(y=TOWER_H, overhang=1, color=ACCENT_COLOR)

    # Gable roof on tower
    tower_roof = GableRoof(
        width=TOWER_SIZE + 2,
        depth=TOWER_SIZE + 2,
        ridge="east_west",
        color=ROOF_COLOR,
        name=f"{name}_roof",
    )
    assembly = place(tower_roof, on=tower, align="center")
    return assembly


tower_sw = make_corner_tower("tower_sw")
tower_se = make_corner_tower("tower_se")
tower_nw = make_corner_tower("tower_nw")
tower_ne = make_corner_tower("tower_ne")

# Position towers at corners
castle_group.add(tower_sw, x=0,                    y=ground_y, z=0)
castle_group.add(tower_se, x=CASTLE_W - TOWER_SIZE, y=ground_y, z=0)
castle_group.add(tower_nw, x=0,                    y=ground_y, z=CASTLE_D - TOWER_SIZE)
castle_group.add(tower_ne, x=CASTLE_W - TOWER_SIZE, y=ground_y, z=CASTLE_D - TOWER_SIZE)


# ══════════════════════════════════════════════════════════════════
# 4. CENTRAL KEEP — the tall main tower
# ══════════════════════════════════════════════════════════════════
keep = Box(
    width=KEEP_W,
    depth=KEEP_D,
    height=KEEP_H,
    color=WALL_COLOR,
    name="keep",
)

# Windows on all sides of the keep — tall windows at mid-height
keep.south.window_row(
    y=4, width=2, height=3, count=2,
    part_type=PartType.WINDOW_1X2X3,
    color=WINDOW_COLOR,
)
keep.north.window_row(
    y=4, width=2, height=3, count=2,
    part_type=PartType.WINDOW_1X2X3,
    color=WINDOW_COLOR,
)
keep.east.window_row(
    y=4, width=2, height=3, count=1,
    part_type=PartType.WINDOW_1X2X3,
    color=WINDOW_COLOR,
)
keep.west.window_row(
    y=4, width=2, height=3, count=1,
    part_type=PartType.WINDOW_1X2X3,
    color=WINDOW_COLOR,
)

# Upper windows
keep.south.window_row(
    y=10, width=2, height=2, count=2,
    part_type=PartType.WINDOW_1X2X2,
    color=WINDOW_COLOR,
)
keep.north.window_row(
    y=10, width=2, height=2, count=2,
    part_type=PartType.WINDOW_1X2X2,
    color=WINDOW_COLOR,
)

# Battlement ledge at top
for wall in keep.walls():
    wall.ledge(y=KEEP_H, overhang=1, color=ACCENT_COLOR)

# Keep roof — taller gable
keep_roof = GableRoof(
    width=KEEP_W + 2,
    depth=KEEP_D + 2,
    ridge="north_south",
    color=ROOF_COLOR,
    name="keep_roof",
)

keep_assembly = place(keep_roof, on=keep, align="center")

# Position keep — center-back of the castle courtyard
keep_x = (CASTLE_W - KEEP_W) // 2
keep_z = CASTLE_D - KEEP_D - TOWER_SIZE + 2  # near the back wall
castle_group.add(keep_assembly, x=keep_x, y=ground_y, z=keep_z)


# ══════════════════════════════════════════════════════════════════
# 5. INTERIOR GREAT HALL — a smaller building inside the courtyard
# ══════════════════════════════════════════════════════════════════
hall = Box(
    width=HALL_W,
    depth=HALL_D,
    height=HALL_H,
    color=Color.TAN,
    name="great_hall",
)

# Windows on the hall
hall.south.window_row(
    y=2, width=2, height=2, count=2,
    part_type=PartType.WINDOW_1X2X2,
    color=WINDOW_COLOR,
)
hall.east.window_row(
    y=2, width=2, height=2, count=2,
    part_type=PartType.WINDOW_1X2X2,
    color=WINDOW_COLOR,
)
hall.west.window_row(
    y=2, width=2, height=2, count=2,
    part_type=PartType.WINDOW_1X2X2,
    color=WINDOW_COLOR,
)

# Door on south face of the hall
hall.south.opening(x=6, y=0, width=4, height=6)
hall.south.insert(PartType.DOOR_1X4X6, x=6, y=0, color=DOOR_COLOR)

# Hall roof — reddish brown gable
hall_roof = GableRoof(
    width=HALL_W + 2,
    depth=HALL_D + 2,
    ridge="east_west",
    color=Color.REDDISH_BROWN,
    name="hall_roof",
)

hall_assembly = place(hall_roof, on=hall, align="center")

# Position hall inside the courtyard — right side
hall_x = CASTLE_W - TOWER_SIZE - HALL_W - 2
hall_z = TOWER_SIZE + 2
castle_group.add(hall_assembly, x=hall_x, y=ground_y, z=hall_z)


# ══════════════════════════════════════════════════════════════════
# 6. COURTYARD FLOOR — stone floor inside the walls
# ══════════════════════════════════════════════════════════════════
courtyard = FloorSlab(
    width=CASTLE_W - 2 * WALL_DEPTH_STUDS,
    depth=CASTLE_D - 2 * WALL_DEPTH_STUDS,
    color=FLOOR_COLOR,
    name="courtyard_floor",
)
castle_group.add(courtyard, x=WALL_DEPTH_STUDS, y=ground_y, z=WALL_DEPTH_STUDS)


# ══════════════════════════════════════════════════════════════════
# 7. GATEHOUSE ACCENT — extra bricks above the gate for an arch look
# ══════════════════════════════════════════════════════════════════
# Small wall section above the gate to create a gatehouse effect
gatehouse_top = Wall(
    length=8,
    height=2,
    facing="south",
    color=ACCENT_COLOR,
    name="gatehouse_accent",
)
# Position it above the south wall, centered on the gate
gatehouse_x = TOWER_SIZE + gate_x - 2
gatehouse_y = ground_y + CURTAIN_H * PLATES_PER_BRICK
castle_group.add(gatehouse_top, x=gatehouse_x, y=gatehouse_y, z=0)

# Small gable over the gatehouse
gatehouse_roof = GableRoof(
    width=10,
    depth=6,
    ridge="east_west",
    color=ROOF_COLOR,
    name="gatehouse_roof",
)
castle_group.add(
    gatehouse_roof,
    x=gatehouse_x - 1,
    y=gatehouse_y + 2 * PLATES_PER_BRICK,
    z=-1,
)


# ══════════════════════════════════════════════════════════════════
# 8. ASSEMBLE AND EXPORT
# ══════════════════════════════════════════════════════════════════
# Add the castle group on top of the base assembly
base_assembly.add(castle_group, x=2, y=0, z=2)  # offset by 2 for baseplate margin

scene.add(base_assembly)

output_file = "medieval_castle.mpd"
scene.export(output_file)

# Print stats
stats = scene.stats()
print(f"Castle model exported to: {output_file}")
print(f"Total parts: {stats['total_parts']}")
print(f"Unique part types: {stats['unique_parts']}")
print(f"Approximate dimensions: {stats['width_studs']}W × {stats['depth_studs']}D × {stats['height_plates']}H (studs/plates)")
print("\nPart breakdown:")
for part_name, count in sorted(stats['part_counts'].items(), key=lambda x: -x[1]):
    print(f"  {part_name}: {count}")
