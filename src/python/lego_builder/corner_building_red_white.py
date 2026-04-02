
from lego_builder import *

scene = Scene(name="corner_building_red_white")
building = Group("corner_building")

width = 24
depth = 24
floor_height = 5
floors = 6

current_y = 0

for i in range(floors):
    color = Color.RED if i % 2 == 0 else Color.WHITE

    box = Box(width=width, depth=depth, height=floor_height,
              color=color, name=f"floor_{i}")

    if i == 0:
        for wall in box.walls():
            wall.opening(x=4, y=0, width=6, height=3)
            wall.insert(PartType.DOOR_1X4X6, x=5, y=0)
    else:
        for wall in box.walls():
            wall.window_row(
                y=1, width=2, height=3, count=5,
                part_type=PartType.WINDOW_1X2X3
            )
            wall.ledge(y=4, overhang=1, color=Color.WHITE if color==Color.RED else Color.RED)

    slab = FloorSlab(width=width, depth=depth,
                     color=Color.DARK_BLUISH_GREY,
                     name=f"slab_{i}")

    floor_group = Group(f"level_{i}")
    floor_group.add(box)
    floor_group.add(slab, y=floor_height * PLATES_PER_BRICK)

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

dome = Column(height=6, color=Color.DARK_RED, name="dome_core")
building.add(dome, x=width//2, z=depth//2, y=current_y)

scene.add(building)
scene.export("corner_building_red_white.mpd")
