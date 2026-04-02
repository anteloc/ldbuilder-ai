"""
Smoke test: Terraced Row Houses
================================
Four attached houses in a row, testing attach() for lateral composition.
Each house is slightly different in color but same structure.
"""

from lego_builder import (
    Scene, Box, Group, FloorSlab, GableRoof,
    PartType, Color, place, attach,
)

scene = Scene("row_houses")


def make_house(color: int, name: str) -> Group:
    """Build one row house unit: 2 stories + gable roof."""

    # Ground floor
    house = Box(width=8, depth=12, height=6, color=color, name=f"{name}_walls")

    # Front: door and window
    house.south.opening(x=1, y=0, width=4, height=6)
    house.south.insert(PartType.DOOR_1X4X6, x=1, y=0)
    house.south.opening(x=5, y=2, width=2, height=2)
    house.south.insert(PartType.WINDOW_1X2X2, x=5, y=2)

    # Back: two windows
    house.north.window_row(y=2, width=2, height=2, count=2,
                            part_type=PartType.WINDOW_1X2X2)

    # Second floor
    floor2 = Box(width=8, depth=12, height=6, color=color, name=f"{name}_f2")
    floor2.south.window_row(y=2, width=2, height=2, count=2,
                             part_type=PartType.WINDOW_1X2X2)
    floor2.north.window_row(y=2, width=2, height=2, count=2,
                             part_type=PartType.WINDOW_1X2X2)

    # Ceiling between floors
    ceiling = FloorSlab(8, 12, color=Color.LIGHT_GREY, name=f"{name}_ceil")

    # Roof
    roof = GableRoof(width=8, depth=12, ridge="north_south",
                      color=Color.DARK_BLUISH_GREY, name=f"{name}_roof")

    # Assemble
    house_group = Group(name)
    house_group.add(house, x=0, y=0, z=0)
    house_group.add(ceiling, x=0, y=house.height_plates, z=0)
    house_group.add(floor2, x=0, y=house.height_plates + 1, z=0)  # +1 for ceiling plate
    top_y = house.height_plates + 1 + floor2.height_plates
    house_group.add(roof, x=0, y=top_y, z=0)

    return house_group


# Build four houses in alternating colors
house1 = make_house(Color.RED, "house1")
house2 = make_house(Color.TAN, "house2")
house3 = make_house(Color.RED, "house3")
house4 = make_house(Color.TAN, "house4")

# Chain them together using attach
row = scene.group("row", [house1])
attach(house2, to=row, face="east", align="flush_south")
attach(house3, to=row, face="east", align="flush_south", offset=(8, 0))
attach(house4, to=row, face="east", align="flush_south", offset=(16, 0))

# Actually, the above attaches at cumulative east edges.
# Let me fix: attach each to the growing row group.

# Export
output_file = scene.export("/home/claude/ldraw-project/row_houses.mpd")

stats = scene.stats()
print(f"Row Houses: {stats['total_parts']} parts")
print(f"Dimensions: {stats['width_studs']}w x {stats['depth_studs']}d x {stats['height_plates']}h")
print(f"\nPart breakdown:")
for part, count in sorted(stats['part_counts'].items(), key=lambda x: -x[1]):
    print(f"  {part}: {count}")
print(f"\nExported to: {output_file}")
