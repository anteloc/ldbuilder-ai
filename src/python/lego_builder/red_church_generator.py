from lego_builder import (
    Scene,
    Group,
    Box,
    FloorSlab,
    GableRoof,
    Column,
    Wall,
    Color,
    PartType,
)


OUTPUT_FILE = "red_church_claude.mpd"


def build_red_church() -> Scene:
    scene = Scene("Red Church")
    church = Group("church")

    # Overall footprint / site
    foundation = FloorSlab(width=30, depth=48, color=Color.LIGHT_BLUISH_GREY, name="foundation")
    church.add(foundation, x=0, y=0, z=0)

    # Main nave
    nave = Box(width=22, depth=28, height=10, color=Color.RED, name="nave")
    nave.south.opening(x=9, y=0, width=4, height=6)
    nave.south.insert(PartType.DOOR_1X4X6, x=9, y=0)
    nave.south.opening(x=9, y=6, width=4, height=3)
    nave.south.insert(PartType.WINDOW_1X4X3, x=9, y=6)
    nave.south.ledge(y=9, overhang=1, color=Color.DARK_RED)

    nave.north.window_row(y=3, width=2, height=3, count=3,
                          part_type=PartType.WINDOW_1X2X3, spacing="even")
    nave.north.ledge(y=9, overhang=1, color=Color.DARK_RED)

    nave.east.window_row(y=3, width=2, height=3, count=3,
                         part_type=PartType.WINDOW_1X2X3, spacing=2)
    nave.east.ledge(y=9, overhang=1, color=Color.DARK_RED)

    nave.west.window_row(y=3, width=2, height=3, count=3,
                         part_type=PartType.WINDOW_1X2X3, spacing=2)
    nave.west.ledge(y=9, overhang=1, color=Color.DARK_RED)

    church.add(nave, x=4, y=1, z=14)

    nave_roof = GableRoof(width=22, depth=28, ridge="north_south", color=Color.DARK_RED, name="nave_roof")
    church.add(nave_roof, x=4, y=1 + nave.height_plates, z=14)

    # Front tower / steeple base
    tower = Box(width=8, depth=10, height=14, color=Color.RED, name="tower")
    tower.south.opening(x=2, y=0, width=4, height=6)
    tower.south.insert(PartType.DOOR_1X4X6, x=2, y=0)
    tower.south.opening(x=2, y=8, width=4, height=3)
    tower.south.insert(PartType.WINDOW_1X4X3, x=2, y=8)

    tower.north.opening(x=3, y=9, width=2, height=3)
    tower.north.insert(PartType.WINDOW_1X2X3, x=3, y=9)
    tower.east.opening(x=4, y=9, width=2, height=3)
    tower.east.insert(PartType.WINDOW_1X2X3, x=4, y=9)
    tower.west.opening(x=4, y=9, width=2, height=3)
    tower.west.insert(PartType.WINDOW_1X2X3, x=4, y=9)

    tower.south.ledge(y=13, overhang=1, color=Color.DARK_RED)
    tower.north.ledge(y=13, overhang=1, color=Color.DARK_RED)
    tower.east.ledge(y=13, overhang=1, color=Color.DARK_RED)
    tower.west.ledge(y=13, overhang=1, color=Color.DARK_RED)

    church.add(tower, x=11, y=1, z=4)

    tower_roof = GableRoof(width=8, depth=10, ridge="east_west", color=Color.DARK_RED, name="tower_roof")
    church.add(tower_roof, x=11, y=1 + tower.height_plates, z=4)

    # Simple cross above the tower roof.
    cross = Group("cross")
    cross_vertical = Column(height=4, color=Color.YELLOW, part_type=PartType.BRICK_1X1, name="cross_vertical")
    cross_beam = FloorSlab(width=3, depth=1, color=Color.YELLOW, name="cross_beam")
    cross.add(cross_vertical, x=1, y=0, z=0)
    cross.add(cross_beam, x=0, y=6, z=0)
    church.add(cross, x=13, y=1 + tower.height_plates + tower_roof.height_plates + 1, z=8)

    # Entrance steps.
    step1 = FloorSlab(width=8, depth=3, color=Color.LIGHT_GREY, name="step1")
    step2 = FloorSlab(width=6, depth=2, color=Color.LIGHT_GREY, name="step2")
    church.add(step1, x=10, y=0, z=1)
    church.add(step2, x=11, y=1, z=2)

    scene.add(church)
    return scene


if __name__ == "__main__":
    scene = build_red_church()
    out = scene.export(OUTPUT_FILE)
    print(f"Wrote {out}")
    print(scene.stats())
