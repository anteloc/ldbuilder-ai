
from lego_builder import *

scene = Scene(name="corner_building_realistic_red_white")
building = Group("corner_building")

width = 24
depth = 24
floor_height = 5
floors = 6

current_y = 0

for i in range(floors):
    box = Box(width=width, depth=depth, height=floor_height,
              color=Color.RED, name=f"floor_{i}")

    if i == 0:
        for wall in box.walls():
            wall.color = Color.WHITE
            wall.opening(x=4, y=0, width=6, height=3)
            wall.insert(PartType.DOOR_1X4X6, x=5, y=0)
            wall.ledge(y=4, overhang=1, color=Color.WHITE)
    else:
        for wall in box.walls():
            wall.window_row(
                y=1, width=2, height=3, count=5,
                part_type=PartType.WINDOW_1X2X3
            )
            wall.ledge(y=2, overhang=1, color=Color.WHITE)
            wall.ledge(y=4, overhang=1, color=Color.WHITE)

    slab = FloorSlab(width=width, depth=depth,
                     color=Color.LIGHT_BLUISH_GREY,
                     name=f"slab_{i}")

    floor_group = Group(f"level_{i}")
    floor_group.add(box)
    floor_group.add(slab, y=floor_height * PLATES_PER_BRICK)

    pilaster_positions = [
        (0,0), (width,0), (0,depth), (width,depth),
        (width//2,0), (width//2,depth),
        (0,depth//2), (width,depth//2)
    ]

    for (px,pz) in pilaster_positions:
        col = Column(height=floor_height, color=Color.WHITE,
                     part_type=PartType.BRICK_1X2, name="pilaster")
        floor_group.add(col, x=px, z=pz)

    building.add(floor_group, y=current_y)
    current_y += floor_height * PLATES_PER_BRICK + slab.height_plates

top = Box(width=20, depth=20, height=3,
          color=Color.DARK_RED,
          name="mansard_top")

for wall in top.walls():
    wall.window_row(y=1, width=2, height=2, count=3,
                    part_type=PartType.WINDOW_1X2X2)

building.add(top, x=2, z=2, y=current_y)
current_y += 3 * PLATES_PER_BRICK

dome = Column(height=8, color=Color.DARK_RED, name="dome_core")
building.add(dome, x=width//2, z=depth//2, y=current_y)

scene.add(building)
scene.export("corner_building_realistic_red_white.mpd")
