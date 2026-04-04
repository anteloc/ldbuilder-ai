"""
spiral_wall.py
==============
Builds a square spiral made of walls using a single WallLayout.

The WallLayout works like a Logo turtle: start at the centre, turn,
build a wall, turn, build a longer wall, etc. Each 90° turn followed
by a longer wall produces the classic square spiral expanding outward.

Square spiral segment lengths (studs), starting from the centre:
  Each pair of segments grows by STEP studs.
  Pattern: s, s, s+step, s+step, s+2*step, ...

        ┌──────────────────────┐
        │                      │
        │   ┌──────────────┐   │
        │   │              │   │
        │   │   ┌──────┐   │   │
        │   │   │      │   │   │
        │   │   │  ·→  │   │   │  ← turtle starts here
        │   │   │      │   │   │
        │   │   └──    │   │   │
        │   │          │   │   │
        │   └──────────┘   │   │
        │                  │   │
        └──────────────────┘       ← last wall is open (spiral end)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lego_builder"))

from lego_builder import Scene, Color

# ─── Configuration ────────────────────────────────────────────────────────────

NUM_TURNS   = 4     # full 360° turns  (4 segments each)
FIRST_SEG   = 6     # length of first segment in studs
STEP        = 6     # growth per half-turn in studs (must be >= 2, the wall depth)
WALL_HEIGHT = 5     # wall height in brick-rows
WALL_COLOR  = Color.RED

# ─── Build ────────────────────────────────────────────────────────────────────

def build_spiral(output_path="square_spiral.mpd"):
    scene = Scene("square_spiral")

    wl = scene.wall_layout(
        height=WALL_HEIGHT,
        color=WALL_COLOR,
        name="spiral",
        initial_direction="east",
    )

    # Direction cycle for a square spiral
    CYCLE = ["east", "north", "west", "south"]

    total_segments = NUM_TURNS * 4

    for i in range(total_segments):
        direction = CYCLE[i % 4]
        length    = FIRST_SEG + (i // 2) * STEP

        wl.build_wall(f"w{i}", length)
        print(f"  seg {i:2d}: {direction:5s}  len={length} studs")

        if i < total_segments - 1:
            wl.turn(CYCLE[(i + 1) % 4])

    stats = scene.stats()
    print(f"\nTotal parts : {stats['total_parts']}")
    print(f"Width       : ~{stats['width_studs']} studs")
    print(f"Depth       : ~{stats['depth_studs']} studs")

    scene.export(output_path)
    print(f"Exported → {output_path}")

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "square_spiral.mpd"
    build_spiral(out)
