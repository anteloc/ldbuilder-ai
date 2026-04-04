import os
import sys
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = os.path.join(SCRIPT_DIR, 'lego_builder.zip')
EXTRACT_DIR = os.path.join(SCRIPT_DIR, '_lego_builder_runtime')

if not os.path.isdir(os.path.join(EXTRACT_DIR, 'lego_builder')):
    with zipfile.ZipFile(ZIP_PATH, 'r') as zf:
        zf.extractall(EXTRACT_DIR)

if EXTRACT_DIR not in sys.path:
    sys.path.insert(0, EXTRACT_DIR)

from lego_builder import Scene, Color, PartType


def build_four_room_house(output_path: str = 'four_room_house_no_roof.mpd'):
    """Build an open-top house with 4 interior rooms and no roof.

    Layout:
    - 26 x 26 stud outer footprint
    - outer perimeter walls, height 6 bricks
    - central north/south partition wall
    - two east/west partition walls meeting the central wall
    - a door in the front wall and door openings in each partition
    - windows on the exterior walls
    """
    scene = Scene('four_room_house_no_roof')

    width = 26
    depth = 26
    wall_height = 6

    # Foundation / visible floor to inspect the interior.
    scene.floor_slab(width=width, depth=depth, color=Color.LIGHT_BLUISH_GREY, name='floor')

    # Outer shell.
    house = scene.box(width=width, depth=depth, height=wall_height, color=Color.TAN, name='house')

    # Front entrance centered on the south wall.
    house.south.opening(x=11, y=0, width=4, height=6)
    house.south.insert(PartType.DOOR_1X4X6, x=11, y=0, color=Color.REDDISH_BROWN)

    # Exterior windows for each room.
    house.north.window_row(y=2, width=4, height=3, count=2, part_type=PartType.WINDOW_1X4X3)
    house.west.window_row(y=2, width=4, height=3, count=2, part_type=PartType.WINDOW_1X4X3)
    house.east.window_row(y=2, width=4, height=3, count=2, part_type=PartType.WINDOW_1X4X3)

    # Add simple trim near the top.
    for wall in house.walls():
        wall.ledge(y=6, overhang=1, color=Color.DARK_TAN)

    # Interior partitions.
    # One full north/south wall down the center.
    center_wall = scene.wall(length=22, height=wall_height, facing='west', color=Color.WHITE, name='center_partition')
    center_wall.opening(x=9, y=0, width=4, height=6)
    center_wall.insert(PartType.DOOR_1X4X6, x=9, y=0, color=Color.WHITE)
    scene.add(center_wall, x=12, z=2)

    # Horizontal partitions split left/right so they butt into the center wall without overlap.
    west_partition = scene.wall(length=10, height=wall_height, facing='south', color=Color.WHITE, name='west_partition')
    west_partition.opening(x=3, y=0, width=4, height=6)
    west_partition.insert(PartType.DOOR_1X4X6, x=3, y=0, color=Color.WHITE)
    scene.add(west_partition, x=2, z=12)

    east_partition = scene.wall(length=10, height=wall_height, facing='south', color=Color.WHITE, name='east_partition')
    east_partition.opening(x=3, y=0, width=4, height=6)
    east_partition.insert(PartType.DOOR_1X4X6, x=3, y=0, color=Color.WHITE)
    scene.add(east_partition, x=14, z=12)

    # Export open-top model.
    scene.export(output_path)
    return scene.stats()


if __name__ == '__main__':
    stats = build_four_room_house()
    print('Built four-room house without a roof.')
    print('Stats:', stats)
