
from lego_builder import *

scene = Scene(name="updated_skyscraper_scene")

width = 24
depth = 24
floors = 12
floor_height = 6

building = Group("updated_skyscraper")
current_y = 0

for i in range(floors):
    box = Box(
        width=width,
        depth=depth,
        height=floor_height,
        color=Color.LIGHT_BLUISH_GREY,
        name=f"floor_{i}",
    )

    if i == 0:
        for wall in box.walls():
            wall.opening(x=4, y=0, width=4, height=6)
            wall.insert(PartType.DOOR_1X4X6, x=4, y=0)
            wall.opening(x=10, y=0, width=4, height=6)
            wall.insert(PartType.DOOR_1X4X6, x=10, y=0)
            wall.ledge(y=5, overhang=1, color=Color.WHITE)
    else:
        for wall in box.walls():
            wall.window_row(
                y=1,
                width=2,
                height=3,
                count=6,
                part_type=PartType.WINDOW_1X2X3,
            )
            wall.ledge(y=5, overhang=1, color=Color.WHITE)

    slab = FloorSlab(
        width=width,
        depth=depth,
        color=Color.DARK_BLUISH_GREY,
        name=f"slab_{i}",
    )

    floor_group = Group(f"level_{i}")
    floor_group.add(box)
    floor_group.add(slab, y=floor_height * PLATES_PER_BRICK)

    building.add(floor_group, y=current_y)
    current_y += floor_height * PLATES_PER_BRICK + slab.height_plates

crown = Box(
    width=18,
    depth=18,
    height=4,
    color=Color.WHITE,
    name="crown",
)
for wall in crown.walls():
    wall.window_row(
        y=1,
        width=2,
        height=2,
        count=4,
        part_type=PartType.WINDOW_1X2X2,
    )
    wall.ledge(y=3, overhang=1, color=Color.LIGHT_BLUISH_GREY)

building.add(crown, x=3, z=3, y=current_y)
current_y += 4 * PLATES_PER_BRICK

roof = FloorSlab(
    width=18,
    depth=18,
    color=Color.BLACK,
    name="roof",
)
building.add(roof, x=3, z=3, y=current_y)

scene.add(building)
scene.export("updated_skyscraper.mpd")
