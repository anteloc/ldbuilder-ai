# labyrinth_demo.py
#
# Generates a LEGO labyrinth as an LDraw .mpd model.
#
# Assumes this script lives alongside the uploaded modules:
#   scene.py, structures.py, parts.py
#
# If you wrapped these files into a package, change imports accordingly.

# from scene import Scene
# from structures import FloorSlab, WallLayout
# from parts import Color
from lego_builder import Scene, FloorSlab, WallLayout, Color
# import * from lego_builder

def build_labyrinth() -> Scene:
    scene = Scene("labyrinth")

    # Base / ground
    base = FloorSlab(
        width=40,
        depth=40,
        color=Color.LIGHT_GREY,
        name="labyrinth_floor",
    )
    scene.add(base)

    # Outer border of the labyrinth.
    # WallLayout starts at (0, 0, 0) and builds connected walls by turning
    # and extending in cardinal directions. 
    border = WallLayout(
        height=4,  # 4 brick rows tall
        color=Color.WHITE,
        name="outer_border",
        initial_direction="east",
    )
    border.build_wall("south_edge", 40)
    border.turn("north")
    border.build_wall("east_edge", 40)
    border.turn("west")
    border.build_wall("north_edge", 40)
    border.turn("south")
    border.build_wall("west_edge", 40)

    scene.add(border)

    # Internal maze walls.
    # Each layout is a connected path of joined walls.
    # We position them on the floor with scene.add(..., x=..., z=...).
    wall_color = Color.WHITE
    wall_height = 4

    # Path A
    a = WallLayout(height=wall_height, color=wall_color, name="maze_a", initial_direction="east")
    a.build_wall("a1", 24)
    a.turn("north")
    a.build_wall("a2", 8)
    a.turn("west")
    a.build_wall("a3", 10)
    a.turn("north")
    a.build_wall("a4", 8)
    a.turn("east")
    a.build_wall("a5", 6)
    scene.add(a, x=4, y=0, z=4)

    # Path B
    b = WallLayout(height=wall_height, color=wall_color, name="maze_b", initial_direction="north")
    b.build_wall("b1", 20)
    b.turn("east")
    b.build_wall("b2", 8)
    b.turn("south")
    b.build_wall("b3", 6)
    b.turn("east")
    b.build_wall("b4", 8)
    b.turn("north")
    b.build_wall("b5", 10)
    scene.add(b, x=8, y=0, z=6)

    # Path C
    c = WallLayout(height=wall_height, color=wall_color, name="maze_c", initial_direction="east")
    c.build_wall("c1", 12)
    c.turn("south")
    c.build_wall("c2", 8)
    c.turn("east")
    c.build_wall("c3", 10)
    c.turn("north")
    c.build_wall("c4", 14)
    scene.add(c, x=6, y=0, z=18)

    # Path D
    d = WallLayout(height=wall_height, color=wall_color, name="maze_d", initial_direction="north")
    d.build_wall("d1", 10)
    d.turn("west")
    d.build_wall("d2", 8)
    d.turn("north")
    d.build_wall("d3", 8)
    d.turn("east")
    d.build_wall("d4", 14)
    scene.add(d, x=24, y=0, z=10)

    # Path E
    e = WallLayout(height=wall_height, color=wall_color, name="maze_e", initial_direction="east")
    e.build_wall("e1", 8)
    e.turn("north")
    e.build_wall("e2", 10)
    e.turn("west")
    e.build_wall("e3", 6)
    e.turn("north")
    e.build_wall("e4", 8)
    e.turn("east")
    e.build_wall("e5", 12)
    scene.add(e, x=18, y=0, z=22)

    # Small end-cap dead-end branches for a more maze-like feel
    f = WallLayout(height=wall_height, color=wall_color, name="maze_f", initial_direction="north")
    f.build_wall("f1", 6)
    f.turn("east")
    f.build_wall("f2", 4)
    scene.add(f, x=30, y=0, z=6)

    g = WallLayout(height=wall_height, color=wall_color, name="maze_g", initial_direction="east")
    g.build_wall("g1", 6)
    g.turn("south")
    g.build_wall("g2", 6)
    scene.add(g, x=10, y=0, z=30)

    return scene


if __name__ == "__main__":
    scene = build_labyrinth()
    output_path = scene.export("labyrinth.mpd")
    print(f"Exported: {output_path}")

    # Optional: if stats() is present in your current scene.py, this helps
    # confirm the model was generated. :contentReference[oaicite:4]{index=4}
    try:
        print(scene.stats())
    except Exception:
        pass