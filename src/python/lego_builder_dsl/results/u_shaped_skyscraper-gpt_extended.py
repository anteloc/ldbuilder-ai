from __future__ import annotations

from pathlib import Path
import sys

# Make the sibling lego_builder package importable when this script sits next to it.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lego_builder import (
    Scene,
    Group,
    FloorSlab,
    WallLayout,
    Column,
    PartType,
    Color,
    place,
)


# Overall proportions in studs.
OUTER_WIDTH = 32
OUTER_DEPTH = 28
WING_THICKNESS = 8
BASE_BAR_DEPTH = 8
INNER_WIDTH = OUTER_WIDTH - 2 * WING_THICKNESS
INNER_DEPTH = OUTER_DEPTH - BASE_BAR_DEPTH

PODIUM_WALL_HEIGHT = 12       # bricks
OFFICE_FLOOR_HEIGHT = 8       # bricks
OFFICE_FLOOR_COUNT = 14
PARAPET_HEIGHT = 2            # bricks

# Refined palette: warm stone podium, bright tower, green-bronze accents.
PODIUM_COLOR = Color.DARK_TAN
PODIUM_TRIM_COLOR = Color.SAND_GREEN
TOWER_FLOOR_COLOR = Color.LIGHT_BLUISH_GREY
TOWER_WALL_COLOR = Color.WHITE
TOWER_ACCENT_COLOR = Color.SAND_GREEN
ROOF_COLOR = Color.DARK_BLUISH_GREY
DOOR_FRAME_COLOR = Color.DARK_BLUISH_GREY
DOOR_PANEL_COLOR = Color.DARK_BLUE
GLASS_COLOR = Color.TRANS_LIGHT_BLUE
PLAZA_COLOR = Color.LIGHT_BLUISH_GREY
MAST_COLOR = Color.DARK_GREY


def add_u_slabs(group: Group, color: int, prefix: str) -> None:
    """Tile a U-shaped floor plate using three rectangular slabs."""
    # South bar
    group.add(
        FloorSlab(
            width=OUTER_WIDTH,
            depth=BASE_BAR_DEPTH,
            color=color,
            fill_part=PartType.PLATE_2X4.value,
            name=f"{prefix}_south_bar",
        ),
        x=0,
        y=0,
        z=0,
    )
    # West wing
    group.add(
        FloorSlab(
            width=WING_THICKNESS,
            depth=INNER_DEPTH,
            color=color,
            fill_part=PartType.PLATE_2X4.value,
            name=f"{prefix}_west_wing",
        ),
        x=0,
        y=0,
        z=BASE_BAR_DEPTH,
    )
    # East wing
    group.add(
        FloorSlab(
            width=WING_THICKNESS,
            depth=INNER_DEPTH,
            color=color,
            fill_part=PartType.PLATE_2X4.value,
            name=f"{prefix}_east_wing",
        ),
        x=OUTER_WIDTH - WING_THICKNESS,
        y=0,
        z=BASE_BAR_DEPTH,
    )


def build_u_shell(name: str, height: int, color: int) -> WallLayout:
    """Create the U-shaped perimeter using the DSL's turtle-style wall layout."""
    shell = WallLayout(
        height=height,
        color=color,
        fill_part=PartType.BRICK_2X4.value,
        name=name,
        initial_direction="east",
    )

    shell.build_wall("south_outer", OUTER_WIDTH)
    shell.turn("north")
    shell.build_wall("east_outer", OUTER_DEPTH)
    shell.turn("west")
    shell.build_wall("east_cap", WING_THICKNESS)
    shell.turn("south")
    shell.build_wall("east_inner", INNER_DEPTH)
    shell.turn("west")
    shell.build_wall("courtyard_south", INNER_WIDTH)
    shell.turn("north")
    shell.build_wall("west_inner", INNER_DEPTH)
    shell.turn("west")
    shell.build_wall("west_cap", WING_THICKNESS)
    shell.turn("south")
    shell.build_wall("west_outer", OUTER_DEPTH)

    return shell


def add_office_windows(shell: WallLayout) -> None:
    """Add a regular glazed curtain-wall rhythm around the tower."""
    # Large outer elevations.
    shell["south_outer"].window_row(y=2, width=2, height=3, count=7, part_type=PartType.WINDOW_1X2X3, spacing=2, color=GLASS_COLOR)
    shell["east_outer"].window_row(y=2, width=2, height=3, count=6, part_type=PartType.WINDOW_1X2X3, spacing=2, color=GLASS_COLOR)
    shell["west_outer"].window_row(y=2, width=2, height=3, count=6, part_type=PartType.WINDOW_1X2X3, spacing=2, color=GLASS_COLOR)

    # Courtyard-facing elevations.
    shell["east_inner"].window_row(y=2, width=2, height=3, count=4, part_type=PartType.WINDOW_1X2X3, spacing=2, color=GLASS_COLOR)
    shell["west_inner"].window_row(y=2, width=2, height=3, count=4, part_type=PartType.WINDOW_1X2X3, spacing=2, color=GLASS_COLOR)
    shell["courtyard_south"].window_row(y=2, width=2, height=3, count=3, part_type=PartType.WINDOW_1X2X3, spacing=2, color=GLASS_COLOR)

    # Short caps at the north ends of the two wings.
    shell["east_cap"].window_row(y=2, width=2, height=3, count=2, part_type=PartType.WINDOW_1X2X3, spacing=2, color=GLASS_COLOR)
    shell["west_cap"].window_row(y=2, width=2, height=3, count=2, part_type=PartType.WINDOW_1X2X3, spacing=2, color=GLASS_COLOR)

    # Colored spandrel/cornice band at the top of each office floor.
    for wall_name in [
        "south_outer",
        "east_outer",
        "west_outer",
        "east_inner",
        "west_inner",
        "courtyard_south",
        "east_cap",
        "west_cap",
    ]:
        shell[wall_name].ledge(
            y=OFFICE_FLOOR_HEIGHT - 1,
            overhang=1,
            color=TOWER_ACCENT_COLOR,
            part_type=PartType.PLATE_2X4,
        )


def add_entry_doors(group: Group) -> None:
    """Add visible recessed door panels behind the door frames."""
    door_positions = [8, 14, 20]
    for idx, x in enumerate(door_positions, start=1):
        group.add(
            Column(
                height=6,
                color=DOOR_PANEL_COLOR,
                part_type=PartType.BRICK_1X4,
                name=f"entry_door_{idx}",
            ),
            x=x,
            y=1,
            z=1,
        )

    # Slim mullions between door bays to make the entrance read as a framed lobby.
    for idx, x in enumerate([12, 18], start=1):
        group.add(
            Column(
                height=6,
                color=DOOR_FRAME_COLOR,
                part_type=PartType.BRICK_1X1,
                name=f"entry_mullion_{idx}",
            ),
            x=x,
            y=1,
            z=1,
        )

    # Low projecting canopy over the entry.
    group.add(
        FloorSlab(
            width=18,
            depth=4,
            color=PODIUM_TRIM_COLOR,
            fill_part=PartType.PLATE_2X4.value,
            name="entry_canopy",
        ),
        x=7,
        y=1 + 6 * 3,
        z=-3,
    )

    # Forecourt in front of the doors.
    group.add(
        FloorSlab(
            width=20,
            depth=4,
            color=PLAZA_COLOR,
            fill_part=PartType.PLATE_2X4.value,
            name="entry_plaza",
        ),
        x=6,
        y=0,
        z=-4,
    )


def make_podium() -> Group:
    podium = Group("podium")
    add_u_slabs(podium, PLAZA_COLOR, "podium_floor")

    shell = build_u_shell("podium_shell", height=PODIUM_WALL_HEIGHT, color=PODIUM_COLOR)

    # Main entrance on the south face: broad lobby glazing with three visible door bays.
    south = shell["south_outer"]
    south.opening(x=2, y=2, width=4, height=3)
    south.insert(PartType.WINDOW_1X4X3, x=2, y=2, color=GLASS_COLOR)
    south.opening(x=8, y=0, width=4, height=6)
    south.insert(PartType.DOOR_1X4X6, x=8, y=0, color=DOOR_FRAME_COLOR)
    south.opening(x=14, y=0, width=4, height=6)
    south.insert(PartType.DOOR_1X4X6, x=14, y=0, color=DOOR_FRAME_COLOR)
    south.opening(x=20, y=0, width=4, height=6)
    south.insert(PartType.DOOR_1X4X6, x=20, y=0, color=DOOR_FRAME_COLOR)
    south.opening(x=26, y=2, width=4, height=3)
    south.insert(PartType.WINDOW_1X4X3, x=26, y=2, color=GLASS_COLOR)

    # Podium glazing around the other elevations.
    for wall_name, count in {
        "east_outer": 5,
        "west_outer": 5,
        "east_inner": 4,
        "west_inner": 4,
        "courtyard_south": 3,
        "east_cap": 2,
        "west_cap": 2,
    }.items():
        shell[wall_name].window_row(
            y=2,
            width=2,
            height=3,
            count=count,
            part_type=PartType.WINDOW_1X2X3,
            spacing=2,
            color=GLASS_COLOR,
        )

    # Podium cornice.
    for wall_name in [
        "south_outer",
        "east_outer",
        "west_outer",
        "east_inner",
        "west_inner",
        "courtyard_south",
        "east_cap",
        "west_cap",
    ]:
        shell[wall_name].ledge(
            y=PODIUM_WALL_HEIGHT - 1,
            overhang=1,
            color=PODIUM_TRIM_COLOR,
            part_type=PartType.PLATE_2X4,
        )

    podium.add(shell, x=0, y=1, z=0)
    add_entry_doors(podium)
    return podium


def make_office_floor() -> Group:
    office = Group("office_floor")
    add_u_slabs(office, TOWER_FLOOR_COLOR, "office_floor")

    shell = build_u_shell("office_shell", height=OFFICE_FLOOR_HEIGHT, color=TOWER_WALL_COLOR)
    add_office_windows(shell)
    office.add(shell, x=0, y=1, z=0)
    return office


def make_roof() -> Group:
    roof = Group("roof")
    add_u_slabs(roof, ROOF_COLOR, "roof")

    parapet = build_u_shell("roof_parapet", height=PARAPET_HEIGHT, color=ROOF_COLOR)
    roof.add(parapet, x=0, y=1, z=0)

    # Simple mechanical mast near the back of the south bar.
    roof.add(
        Column(
            height=10,
            color=MAST_COLOR,
            part_type=PartType.BRICK_1X1,
            name="antenna_mast",
        ),
        x=OUTER_WIDTH // 2,
        y=1 + PARAPET_HEIGHT * 3,
        z=BASE_BAR_DEPTH - 3,
    )
    return roof


def build_scene() -> Scene:
    scene = Scene("U-shaped skyscraper")

    podium = make_podium()
    office_stack = make_office_floor().stack(OFFICE_FLOOR_COUNT)
    tower = place(office_stack, on=podium, align="origin")
    place(make_roof(), on=tower, align="origin")

    scene.add(tower)
    return scene


if __name__ == "__main__":
    scene = build_scene()
    out_path = ROOT / "u_shaped_skyscraper-gpt_extended.mpd"
    scene.export(str(out_path))
    print(f"Exported to: {out_path}")
    print(scene.stats())
