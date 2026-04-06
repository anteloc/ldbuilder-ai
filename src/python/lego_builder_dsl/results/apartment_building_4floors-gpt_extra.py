from __future__ import annotations

from pathlib import Path
import sys
import zipfile

# Make the sibling lego_builder package importable when this script sits next to it.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lego_builder import (
    Scene,
    Group,
    Box,
    FloorSlab,
    WallLayout,
    Column,
    PartType,
    Color,
    place,
)


# Overall dimensions in studs.
BUILDING_WIDTH = 28
BUILDING_DEPTH = 20
FLOOR_HEIGHT = 8          # bricks
FLOOR_COUNT = 4
PARAPET_HEIGHT = 2        # bricks

# Interior apartment layout (inside the 2-stud-thick exterior shell).
INNER_X = 2
INNER_Z = 2
INNER_WIDTH = BUILDING_WIDTH - 4   # 24
INNER_DEPTH = BUILDING_DEPTH - 4   # 16
PARTY_WALL_X = 13                  # 11-stud apt + 2-stud wall + 11-stud apt
ROOM_DIVIDER_Z = 9                 # 7-stud room + 2-stud wall + 7-stud room
APARTMENT_WIDTH = 11
ROOM_DEPTH = 7

# Colors: warm residential palette.
SITE_COLOR = Color.LIGHT_BLUISH_GREY
BASE_COLOR = Color.DARK_TAN
WALL_COLOR = Color.TAN
TRIM_COLOR = Color.WHITE
ACCENT_COLOR = Color.SAND_GREEN
ROOF_COLOR = Color.DARK_BLUISH_GREY
WINDOW_COLOR = Color.TRANS_LIGHT_BLUE
DOOR_FRAME_COLOR = Color.DARK_BLUISH_GREY
DOOR_PANEL_COLOR = Color.DARK_RED
INTERIOR_WALL_COLOR = Color.WHITE
STAIR_TOWER_COLOR = Color.LIGHT_BLUISH_GREY
RAILING_COLOR = Color.SAND_GREEN
HVAC_COLOR = Color.DARK_GREY


def add_floor_plate(group: Group, name: str, color: int) -> None:
    group.add(
        FloorSlab(
            width=BUILDING_WIDTH,
            depth=BUILDING_DEPTH,
            color=color,
            fill_part=PartType.PLATE_2X4.value,
            name=name,
        ),
        x=0,
        y=0,
        z=0,
    )


def add_perimeter_windows(shell: Box, include_entry: bool = False) -> None:
    """Add a regular apartment-window rhythm to the exterior shell."""
    if include_entry:
        # Ground floor south elevation with centered main entry and apartment windows.
        south = shell.south
        for x in [2, 7, 17, 22]:
            south.opening(x=x, y=2, width=4, height=3)
            south.insert(PartType.WINDOW_1X4X3, x=x, y=2, color=WINDOW_COLOR)
        south.opening(x=12, y=0, width=4, height=6)
        south.insert(PartType.DOOR_1X4X6, x=12, y=0, color=DOOR_FRAME_COLOR)
    else:
        shell.south.window_row(
            y=2,
            width=4,
            height=3,
            count=4,
            part_type=PartType.WINDOW_1X4X3,
            spacing=2,
            color=WINDOW_COLOR,
        )

    shell.north.window_row(
        y=2,
        width=4,
        height=3,
        count=4,
        part_type=PartType.WINDOW_1X4X3,
        spacing=2,
        color=WINDOW_COLOR,
    )

    for wall in [shell.east, shell.west]:
        wall.window_row(
            y=2,
            width=2,
            height=3,
            count=3,
            part_type=PartType.WINDOW_1X2X3,
            spacing="even",
            color=WINDOW_COLOR,
        )

    # Light trim band at the top of the floor.
    for wall in shell.walls():
        wall.ledge(
            y=FLOOR_HEIGHT - 1,
            overhang=1,
            color=ACCENT_COLOR,
            part_type=PartType.PLATE_2X4,
        )


def make_apartment_partitions(name: str) -> Group:
    """Create two apartments, each split into two rooms."""
    partitions = Group(name)

    # Central party wall separating the two apartments.
    party = WallLayout(
        height=FLOOR_HEIGHT,
        color=INTERIOR_WALL_COLOR,
        fill_part=PartType.BRICK_2X4.value,
        name=f"{name}_party",
        initial_direction="north",
    )
    party.build_wall("party_wall", INNER_DEPTH)
    partitions.add(party, x=PARTY_WALL_X, y=1, z=INNER_Z)

    # West apartment room divider (living room / bedroom).
    west_divider = WallLayout(
        height=FLOOR_HEIGHT,
        color=INTERIOR_WALL_COLOR,
        fill_part=PartType.BRICK_2X4.value,
        name=f"{name}_west_divider",
        initial_direction="east",
    )
    west_divider.build_wall("room_split", APARTMENT_WIDTH)
    west_divider["room_split"].opening(x=8, y=0, width=2, height=6)
    partitions.add(west_divider, x=INNER_X, y=1, z=ROOM_DIVIDER_Z)

    # East apartment room divider.
    east_divider = WallLayout(
        height=FLOOR_HEIGHT,
        color=INTERIOR_WALL_COLOR,
        fill_part=PartType.BRICK_2X4.value,
        name=f"{name}_east_divider",
        initial_direction="east",
    )
    east_divider.build_wall("room_split", APARTMENT_WIDTH)
    east_divider["room_split"].opening(x=1, y=0, width=2, height=6)
    partitions.add(east_divider, x=15, y=1, z=ROOM_DIVIDER_Z)

    return partitions


def add_entry_details(group: Group) -> None:
    """Add visible front doors, steps, and a small canopy to the main entry."""
    # Door leaf behind the frame.
    group.add(
        Column(
            height=6,
            color=DOOR_PANEL_COLOR,
            part_type=PartType.BRICK_1X4,
            name="main_door_leaf",
        ),
        x=12,
        y=1,
        z=1,
    )

    # Small canopy above the entrance.
    group.add(
        FloorSlab(
            width=6,
            depth=3,
            color=ACCENT_COLOR,
            fill_part=PartType.PLATE_2X4.value,
            name="entry_canopy",
        ),
        x=11,
        y=1 + 6 * 3,
        z=-2,
    )

    # Front stoop / sidewalk.
    group.add(
        FloorSlab(
            width=12,
            depth=4,
            color=SITE_COLOR,
            fill_part=PartType.PLATE_2X4.value,
            name="entry_stoop",
        ),
        x=8,
        y=0,
        z=-4,
    )


def add_balconies(group: Group) -> None:
    """Add two shallow balconies on the south elevation for upper floors."""
    balcony_y = 1
    balcony_z = -3
    for idx, x in enumerate([3, 17], start=1):
        group.add(
            FloorSlab(
                width=8,
                depth=3,
                color=ACCENT_COLOR,
                fill_part=PartType.PLATE_2X4.value,
                name=f"balcony_{idx}",
            ),
            x=x,
            y=balcony_y,
            z=balcony_z,
        )
        # Slender support posts so the slabs read as attached balconies.
        group.add(
            Column(
                height=FLOOR_HEIGHT,
                color=TRIM_COLOR,
                part_type=PartType.BRICK_1X1,
                name=f"balcony_support_left_{idx}",
            ),
            x=x,
            y=0,
            z=balcony_z,
        )
        group.add(
            Column(
                height=FLOOR_HEIGHT,
                color=TRIM_COLOR,
                part_type=PartType.BRICK_1X1,
                name=f"balcony_support_right_{idx}",
            ),
            x=x + 7,
            y=0,
            z=balcony_z,
        )


        front_rail = WallLayout(
            height=2,
            color=RAILING_COLOR,
            fill_part=PartType.BRICK_1X4.value,
            name=f"balcony_front_rail_{idx}",
            initial_direction="east",
        )
        front_rail.build_wall("front", 8)
        group.add(front_rail, x=x, y=1 + 3, z=balcony_z)


def make_ground_floor() -> Group:
    floor = Group("ground_floor")
    add_floor_plate(floor, "ground_floor_plate", SITE_COLOR)

    shell = Box(
        width=BUILDING_WIDTH,
        depth=BUILDING_DEPTH,
        height=FLOOR_HEIGHT,
        color=BASE_COLOR,
        fill_part=PartType.BRICK_2X4.value,
        name="ground_shell",
    )
    add_perimeter_windows(shell, include_entry=True)
    floor.add(shell, x=0, y=1, z=0)

    floor.add(make_apartment_partitions("ground_apartments"), x=0, y=0, z=0)
    add_entry_details(floor)
    return floor


def make_residential_floor() -> Group:
    floor = Group("residential_floor")
    add_floor_plate(floor, "residential_floor_plate", TRIM_COLOR)

    shell = Box(
        width=BUILDING_WIDTH,
        depth=BUILDING_DEPTH,
        height=FLOOR_HEIGHT,
        color=WALL_COLOR,
        fill_part=PartType.BRICK_2X4.value,
        name="residential_shell",
    )
    add_perimeter_windows(shell, include_entry=False)
    floor.add(shell, x=0, y=1, z=0)

    floor.add(make_apartment_partitions("upper_apartments"), x=0, y=0, z=0)
    add_balconies(floor)
    return floor


def make_roof() -> Group:
    roof = Group("roof")
    add_floor_plate(roof, "roof_plate", ROOF_COLOR)

    parapet = Box(
        width=BUILDING_WIDTH,
        depth=BUILDING_DEPTH,
        height=PARAPET_HEIGHT,
        color=ROOF_COLOR,
        fill_part=PartType.BRICK_2X4.value,
        name="roof_parapet",
    )
    for wall in parapet.walls():
        wall.ledge(y=PARAPET_HEIGHT - 1, overhang=1, color=TRIM_COLOR, part_type=PartType.PLATE_2X4)
    roof.add(parapet, x=0, y=1, z=0)

    # Small rooftop utility block.
    roof.add(
        Box(
            width=8,
            depth=6,
            height=4,
            color=STAIR_TOWER_COLOR,
            fill_part=PartType.BRICK_2X4.value,
            name="roof_bulkhead",
        ),
        x=10,
        y=1,
        z=7,
    )

    roof.add(
        Column(
            height=6,
            color=HVAC_COLOR,
            part_type=PartType.BRICK_1X1,
            name="roof_vent",
        ),
        x=22,
        y=1,
        z=14,
    )
    return roof


def make_site() -> Group:
    site = Group("site")
    site.add(
        FloorSlab(
            width=BUILDING_WIDTH + 8,
            depth=BUILDING_DEPTH + 8,
            color=SITE_COLOR,
            fill_part=PartType.PLATE_2X4.value,
            name="site_pad",
        ),
        x=-4,
        y=0,
        z=-4,
    )
    return site


def build_scene() -> Scene:
    scene = Scene("4-floor apartment building")
    scene.add(make_site())

    ground = make_ground_floor()
    upper_stack = make_residential_floor().stack(FLOOR_COUNT - 1)
    building = place(upper_stack, on=ground, align="origin")
    place(make_roof(), on=building, align="origin")

    scene.add(building)
    return scene


if __name__ == "__main__":
    scene = build_scene()
    out_path = ROOT / "apartment_building_4floors-gpt_extra.mpd"
    scene.export(str(out_path))
    print(f"Exported to: {out_path}")
    print(scene.stats())
