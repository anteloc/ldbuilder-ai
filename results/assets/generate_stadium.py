#!/usr/bin/env python3
"""
LEGO Stadium Generator

Design overview:
  - Oval footprint: ~48 studs long × 32 studs wide (384 × 256 LDU)
  - Pitch (playing field): central green 32×20 stud area
  - Four stands: North, South (long), East, West (end stands)
  - Each stand: 3 tiers of seating stepping upward/inward
  - Exterior: arched facades with windows all around
  - Corner sections: round corner columns
  - 4 floodlight pylons at corners
  - Roof canopy over top tier

LDraw coordinate system:
  Y is DOWN (negative Y = up)
  Ground plane at Y=0
  Building goes UPWARD (Y decreasing)

Parts used:
  - 3811: Baseplate 32×32 (for pitch sections)
  - 3035: Plate 4×8 (seating rows)
  - 3036: Plate 6×8 (seating rows)
  - 3030: Plate 4×10
  - 4477: Plate 1×10
  - 3008: Brick 1×8
  - 3009: Brick 1×6
  - 3010: Brick 1×4
  - 3001: Brick 2×4
  - 2465: Brick 1×16
  - 4282: Plate 2×16
  - 14707: Arch 1×12×3 Raised (entrance arches)
  - 16577: Arch 1×8×2 Raised (smaller arches)
  - 2339: Arch 1×5×4
  - 2577: Brick 4×4 Corner Round (corner columns)
  - 15332: Fence Spindled 1×4×2 (pitch boundary)
  - 30077: Fence 1×6×2
  - 2493b: Window 1×4×5 (facade windows)
  - 2494: Glass for Window 1×4×5
  - 4162: Tile 1×8 (roof edge)
  - 3957a: Antenna (floodlight)
  - 4589: Cone 1×1 (floodlight top)
  - 3942c: Cone 2×2×2 (pylon cap)
  - 11290: Slope Brick Curved 2×8×2 Double (canopy roof)
  - 3685: Slope Brick 75 2×2×3 (steep wall sections)
  - 3455: Arch 1×6
  - 6091: Brick 2×1×1.333 Curved Top
  - 88292: Arch 1×3×2 Ogee (decorative)
  - 21229: Fence Quarter Round (corners)
  - 15626: Panel 4×16×10 with Gate (main entrance)
"""

# Colors
GREEN = 2        # Grass pitch
BRIGHT_GREEN = 10 # Pitch markings
WHITE = 15       # Lines, seats
GREY = 71        # Light bluish grey - stands structure
DARK_GREY = 72   # Dark details
RED = 4          # Accent color
YELLOW = 14      # Seats / accents
BLUE = 1         # Away-end seats
TRANS_CLEAR = 47 # Windows
BLACK = 0        # Base

ID = "1 0 0 0 1 0 0 0 1"
# Common rotation matrices
ROT90Y  = "0 0 -1 0 1 0 1 0 0"   # 90° around Y
ROT180Y = "-1 0 0 0 1 0 0 0 -1"  # 180° around Y  
ROT270Y = "0 0 1 0 1 0 -1 0 0"   # 270° around Y (-90°)
# Face-forward (outward) orientations - for parts placed on walls
FACE_N  = "1 0 0 0 1 0 0 0 1"    # facing +Z (north exterior)
FACE_S  = "-1 0 0 0 1 0 0 0 -1"  # facing -Z (south exterior)
FACE_E  = "0 0 -1 0 1 0 1 0 0"   # facing +X (east)
FACE_W  = "0 0 1 0 1 0 -1 0 0"   # facing -X (west)

def p(color, x, y, z, mat, part):
    return f"1 {color} {x} {y} {z} {mat} {part}"

lines = []

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
lines += [
    "0 FILE generated_stadium.mpd",
    "0 Football Stadium",
    "0 Name: generated_stadium.mpd",
    "0 Author: Claude",
    "0 !LDRAW_ORG Model",
    "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt",
    "",
    "1 16 0 0 0 1 0 0 0 1 0 0 0 1 stadium_main.ldr",
    "", "", "",
]

# ─────────────────────────────────────────────
# MAIN ASSEMBLY
# ─────────────────────────────────────────────
lines += [
    "0 FILE stadium_main.ldr",
    "0 Stadium Main",
    "0 Name: stadium_main.ldr",
    "0 Author: Claude",
    "0 !LDRAW_ORG Model",
    "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt",
    "",
    "0 STEP",
    "1 16 0 0 0 1 0 0 0 1 0 0 0 1 stadium_pitch.ldr",
    "0 STEP",
    "1 16 0 0 0 1 0 0 0 1 0 0 0 1 stadium_stand_north.ldr",
    "0 STEP",
    "1 16 0 0 0 1 0 0 0 1 0 0 0 1 stadium_stand_south.ldr",
    "0 STEP",
    "1 16 0 0 0 1 0 0 0 1 0 0 0 1 stadium_stand_east.ldr",
    "0 STEP",
    "1 16 0 0 0 1 0 0 0 1 0 0 0 1 stadium_stand_west.ldr",
    "0 STEP",
    "1 16 0 0 0 1 0 0 0 1 0 0 0 1 stadium_corners.ldr",
    "0 STEP",
    "1 16 0 0 0 1 0 0 0 1 0 0 0 1 stadium_exterior.ldr",
    "0 STEP",
    "1 16 0 0 0 1 0 0 0 1 0 0 0 1 stadium_floodlights.ldr",
    "", "", "",
]

# ─────────────────────────────────────────────
# PITCH  (playing field)
# ─────────────────────────────────────────────
# Stadium internal footprint: 320 × 200 LDU (40 × 25 studs)
# Pitch: 240 × 160 LDU centred
# Use 4 × 32×32 baseplates (3811) in a 2×2 grid
lines += [
    "0 FILE stadium_pitch.ldr",
    "0 Pitch",
    "0 Name: stadium_pitch.ldr",
    "0 Author: Claude",
    "0 !LDRAW_ORG Model",
    "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt",
    "",
    "0 STEP",
    "0 Four baseplates form the grass pitch",
]
for (bx, bz) in [(-128, -128), (128, -128), (-128, 128), (128, 128)]:
    lines.append(p(GREEN, bx, 8, bz, ID, "3811.dat"))

# Pitch markings — white plates on top of green base
lines += [
    "",
    "0 STEP",
    "0 Centre circle — white ring plates",
]
# Centre spot
lines.append(p(WHITE, 0, 0, 0, ID, "3958.dat"))  # 6×6 plate centre
# Centre line — row of 1×10 plates along Z=0, spanning X
for xoff in range(-80, 90, 80):
    lines.append(p(WHITE, xoff, 0, 0, ROT90Y, "4477.dat"))  # 1×10 along X→Z
# Penalty boxes — white plate outlines
for side_z, mat in [(-120, ID), (120, ROT180Y)]:
    for xoff in [-40, 40]:
        lines.append(p(WHITE, xoff, 0, side_z, ID, "3710.dat"))  # 1×4 front posts
    lines.append(p(WHITE, 0, 0, side_z, ID, "3666.dat"))         # 1×6 goal line
# Goal area plates
for side_z in [-140, 140]:
    lines.append(p(WHITE, 0, 0, side_z, ID, "3020.dat"))  # 2×4 goal zone
lines += ["", "", ""]

# ─────────────────────────────────────────────
# STAND BUILDER FUNCTION
# ─────────────────────────────────────────────
def make_stand(name, label, tier_configs, seat_color_rows, facing_mat, stand_x_positions, stand_z_positions, length_brick, length_plate):
    """
    Generates a complete stand submodel.
    
    tier_configs: list of (tier_y, tier_depth_z, wall_height) tuples
    seat_color_rows: list of colors for seat rows bottom to top
    facing_mat: matrix for parts facing outward
    stand_x_positions: list of X positions for repeated columns of seats
    stand_z_positions: base Z position (front edge of stand)
    length_brick: brick part for the long back wall
    length_plate: plate part for floor
    """
    sl = [
        f"0 FILE {name}",
        f"0 {label}",
        f"0 Name: {name}",
        "0 Author: Claude",
        "0 !LDRAW_ORG Model",
        "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt",
        "",
    ]
    return sl

# ─────────────────────────────────────────────
# NORTH STAND  (Z = -200, facing south = +Z)
# 3 tiers, long side
# ─────────────────────────────────────────────
lines += [
    "0 FILE stadium_stand_north.ldr",
    "0 North Stand",
    "0 Name: stadium_stand_north.ldr",
    "0 Author: Claude",
    "0 !LDRAW_ORG Model",
    "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt",
    "",
]

# Stand spans X = -200 to +200 (400 LDU = 50 studs wide)
# Base wall at Z = -200, tiers step toward pitch (increasing Z)
# Tier 1 (pitch level): Z=-200 to -160, Y=0 to -24 (1 brick high)
# Tier 2 (mid):         Z=-160 to -120, Y=-24 to -64 (2 bricks high)  
# Tier 3 (top):         Z=-120 to -80,  Y=-64 to -128 (3 bricks high)
# Back wall:            Z=-200, Y=0 to -128 (full height exterior)

# Tier seat rows — alternating yellow/blue/red for visual stadium look
SEAT_COLS = [(c, RED, YELLOW, BLUE, WHITE) for c in range(5)]  # 5 colors cycling

lines.append("0 STEP")
lines.append("0 Tier 1 floor — pitch level")
for bx in range(-200, 210, 40):  # every 40 LDU (5 studs)
    lines.append(p(GREY, bx, 0, -180, ID, "3035.dat"))  # Plate 4×8 (32 wide, 64 deep → rotated)

lines.append("0 STEP")
lines.append("0 Tier 1 riser wall")
for bx in range(-200, 210, 80):
    lines.append(p(GREY, bx, -8, -160, FACE_S, "3008.dat"))   # Brick 1×8 riser

lines.append("0 STEP")
lines.append("0 Tier 1 seats")
for bx in range(-200, 210, 40):
    lines.append(p(RED, bx, -8, -180, ID, "3035.dat"))    # Red seats tier 1

lines.append("0 STEP")
lines.append("0 Tier 2 floor")
for bx in range(-200, 210, 40):
    lines.append(p(GREY, bx, -24, -140, ID, "3035.dat"))

lines.append("0 STEP")
lines.append("0 Tier 2 riser wall")
for bx in range(-200, 210, 80):
    lines.append(p(GREY, bx, -32, -120, FACE_S, "3008.dat"))
    lines.append(p(GREY, bx, -56, -120, FACE_S, "3008.dat"))

lines.append("0 STEP")
lines.append("0 Tier 2 seats")
for bx in range(-200, 210, 40):
    lines.append(p(YELLOW, bx, -32, -140, ID, "3035.dat"))  # Yellow seats tier 2

lines.append("0 STEP")
lines.append("0 Tier 3 floor")
for bx in range(-200, 210, 40):
    lines.append(p(GREY, bx, -64, -100, ID, "3035.dat"))

lines.append("0 STEP")
lines.append("0 Tier 3 riser wall")
for bx in range(-200, 210, 80):
    lines.append(p(GREY, bx, -72, -80, FACE_S, "3008.dat"))
    lines.append(p(GREY, bx, -96, -80, FACE_S, "3008.dat"))
    lines.append(p(GREY, bx, -120, -80, FACE_S, "3008.dat"))

lines.append("0 STEP")
lines.append("0 Tier 3 seats")
for bx in range(-200, 210, 40):
    lines.append(p(BLUE, bx, -72, -100, ID, "3035.dat"))   # Blue seats tier 3

lines.append("0 STEP")
lines.append("0 Back wall exterior — full height")
for bx in range(-200, 210, 80):
    for wy in range(0, -128, -24):
        lines.append(p(GREY, bx, wy - 8, -200, FACE_S, "3008.dat"))

lines.append("0 STEP")
lines.append("0 Roof canopy")
for bx in range(-200, 210, 40):
    lines.append(p(WHITE, bx, -128, -140, ID, "3035.dat"))   # Roof plate
for bx in range(-200, 210, 80):
    lines.append(p(WHITE, bx, -136, -120, FACE_S, "11290.dat"))  # Curved canopy front

lines += ["", "", ""]

# ─────────────────────────────────────────────
# SOUTH STAND (Z = +200, mirror of North, facing -Z)
# ─────────────────────────────────────────────
lines += [
    "0 FILE stadium_stand_south.ldr",
    "0 South Stand",
    "0 Name: stadium_stand_south.ldr",
    "0 Author: Claude",
    "0 !LDRAW_ORG Model",
    "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt",
    "",
]

lines.append("0 STEP")
for bx in range(-200, 210, 40):
    lines.append(p(GREY, bx, 0, 180, ID, "3035.dat"))

lines.append("0 STEP")
for bx in range(-200, 210, 80):
    lines.append(p(GREY, bx, -8, 160, FACE_N, "3008.dat"))

lines.append("0 STEP")
for bx in range(-200, 210, 40):
    lines.append(p(RED, bx, -8, 180, ID, "3035.dat"))

lines.append("0 STEP")
for bx in range(-200, 210, 40):
    lines.append(p(GREY, bx, -24, 140, ID, "3035.dat"))

lines.append("0 STEP")
for bx in range(-200, 210, 80):
    lines.append(p(GREY, bx, -32, 120, FACE_N, "3008.dat"))
    lines.append(p(GREY, bx, -56, 120, FACE_N, "3008.dat"))

lines.append("0 STEP")
for bx in range(-200, 210, 40):
    lines.append(p(YELLOW, bx, -32, 140, ID, "3035.dat"))

lines.append("0 STEP")
for bx in range(-200, 210, 40):
    lines.append(p(GREY, bx, -64, 100, ID, "3035.dat"))

lines.append("0 STEP")
for bx in range(-200, 210, 80):
    lines.append(p(GREY, bx, -72, 80, FACE_N, "3008.dat"))
    lines.append(p(GREY, bx, -96, 80, FACE_N, "3008.dat"))
    lines.append(p(GREY, bx, -120, 80, FACE_N, "3008.dat"))

lines.append("0 STEP")
for bx in range(-200, 210, 40):
    lines.append(p(BLUE, bx, -72, 100, ID, "3035.dat"))

lines.append("0 STEP")
for bx in range(-200, 210, 80):
    for wy in range(0, -128, -24):
        lines.append(p(GREY, bx, wy - 8, 200, FACE_N, "3008.dat"))

lines.append("0 STEP")
for bx in range(-200, 210, 40):
    lines.append(p(WHITE, bx, -128, 140, ID, "3035.dat"))
for bx in range(-200, 210, 80):
    lines.append(p(WHITE, bx, -136, 120, FACE_N, "11290.dat"))

lines += ["", "", ""]

# ─────────────────────────────────────────────
# EAST STAND (X = +240, facing -X = west)
# Shorter end stand, 2 tiers
# ─────────────────────────────────────────────
lines += [
    "0 FILE stadium_stand_east.ldr",
    "0 East Stand",
    "0 Name: stadium_stand_east.ldr",
    "0 Author: Claude",
    "0 !LDRAW_ORG Model",
    "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt",
    "",
]

lines.append("0 STEP")
for bz in range(-160, 170, 40):
    lines.append(p(GREY, 220, 0, bz, ROT90Y, "3035.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 80):
    lines.append(p(GREY, 200, -8, bz, FACE_W, "3008.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 40):
    lines.append(p(RED, 220, -8, bz, ROT90Y, "3035.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 40):
    lines.append(p(GREY, 180, -24, bz, ROT90Y, "3035.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 80):
    lines.append(p(GREY, 160, -32, bz, FACE_W, "3008.dat"))
    lines.append(p(GREY, 160, -56, bz, FACE_W, "3008.dat"))
    lines.append(p(GREY, 160, -80, bz, FACE_W, "3008.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 40):
    lines.append(p(YELLOW, 180, -32, bz, ROT90Y, "3035.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 80):
    for wy in range(0, -104, -24):
        lines.append(p(GREY, 240, wy - 8, bz, FACE_W, "3008.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 40):
    lines.append(p(WHITE, 200, -104, bz, ROT90Y, "3035.dat"))
for bz in range(-160, 170, 80):
    lines.append(p(WHITE, 180, -112, bz, FACE_W, "11290.dat"))

lines += ["", "", ""]

# ─────────────────────────────────────────────
# WEST STAND (X = -240, mirror of East)
# ─────────────────────────────────────────────
lines += [
    "0 FILE stadium_stand_west.ldr",
    "0 West Stand",
    "0 Name: stadium_stand_west.ldr",
    "0 Author: Claude",
    "0 !LDRAW_ORG Model",
    "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt",
    "",
]

lines.append("0 STEP")
for bz in range(-160, 170, 40):
    lines.append(p(GREY, -220, 0, bz, ROT90Y, "3035.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 80):
    lines.append(p(GREY, -200, -8, bz, FACE_E, "3008.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 40):
    lines.append(p(RED, -220, -8, bz, ROT90Y, "3035.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 40):
    lines.append(p(GREY, -180, -24, bz, ROT90Y, "3035.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 80):
    lines.append(p(GREY, -160, -32, bz, FACE_E, "3008.dat"))
    lines.append(p(GREY, -160, -56, bz, FACE_E, "3008.dat"))
    lines.append(p(GREY, -160, -80, bz, FACE_E, "3008.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 40):
    lines.append(p(YELLOW, -180, -32, bz, ROT90Y, "3035.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 80):
    for wy in range(0, -104, -24):
        lines.append(p(GREY, -240, wy - 8, bz, FACE_E, "3008.dat"))

lines.append("0 STEP")
for bz in range(-160, 170, 40):
    lines.append(p(WHITE, -200, -104, bz, ROT90Y, "3035.dat"))
for bz in range(-160, 170, 80):
    lines.append(p(WHITE, -180, -112, bz, FACE_E, "11290.dat"))

lines += ["", "", ""]

# ─────────────────────────────────────────────
# CORNERS  (4 corner sections join the stands)
# ─────────────────────────────────────────────
lines += [
    "0 FILE stadium_corners.ldr",
    "0 Corner Sections",
    "0 Name: stadium_corners.ldr",
    "0 Author: Claude",
    "0 !LDRAW_ORG Model",
    "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt",
    "",
    "0 STEP",
    "0 Four corner tower columns using Brick 4x4 Corner Round (2577)",
]

corner_configs = [
    (+200, -200, ID),        # NE
    (-200, -200, ROT180Y),   # NW  
    (+200, +200, ROT180Y),   # SE
    (-200, +200, ID),        # SW
]
for (cx, cz, mat) in corner_configs:
    for wy in range(0, -128, -24):
        lines.append(p(GREY, cx, wy - 24, cz, mat, "2577.dat"))
    # Corner seats — small sections
    lines.append(p(RED, cx, 0, cz, mat, "3003.dat"))
    lines.append(p(RED, cx, -24, cz, mat, "3003.dat"))
    # Corner fence quarter-round
    lines.append(p(WHITE, cx, -128, cz, mat, "21229.dat"))

lines += ["", "", ""]

# ─────────────────────────────────────────────
# EXTERIOR FACADE
# ─────────────────────────────────────────────
lines += [
    "0 FILE stadium_exterior.ldr",
    "0 Exterior Facade",
    "0 Name: stadium_exterior.ldr",
    "0 Author: Claude",
    "0 !LDRAW_ORG Model",
    "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt",
    "",
]

# North exterior facade (Z = -200, Y = 0 to -128)
# Large arches at ground level, windows above
lines.append("0 STEP")
lines.append("0 North facade arches (Arch 1x12x3 Raised = 14707)")
# Place arches across north face every 100 LDU
for bx in range(-150, 160, 100):
    lines.append(p(GREY, bx, 0, -200, FACE_S, "14707.dat"))

lines.append("0 STEP")
lines.append("0 North facade windows")
for bx in range(-160, 170, 80):
    lines.append(p(GREY, bx, -56, -200, FACE_S, "2493b.dat"))
    lines.append(p(TRANS_CLEAR, bx, -56, -200, FACE_S, "2494.dat"))

lines.append("0 STEP")
lines.append("0 North facade top band")
for bx in range(-200, 210, 80):
    lines.append(p(RED, bx, -128, -200, FACE_S, "4162.dat"))

# South exterior facade (Z = +200)
lines.append("0 STEP")
lines.append("0 South facade")
for bx in range(-150, 160, 100):
    lines.append(p(GREY, bx, 0, 200, FACE_N, "14707.dat"))
for bx in range(-160, 170, 80):
    lines.append(p(GREY, bx, -56, 200, FACE_N, "2493b.dat"))
    lines.append(p(TRANS_CLEAR, bx, -56, 200, FACE_N, "2494.dat"))
for bx in range(-200, 210, 80):
    lines.append(p(RED, bx, -128, 200, FACE_N, "4162.dat"))

# East exterior facade (X = +240)
lines.append("0 STEP")
lines.append("0 East facade — main entrance with gate panel")
lines.append(p(GREY, 240, 0, 0, FACE_W, "15626.dat"))   # Gate panel centred
for bz in range(-160, 170, 100):
    if abs(bz) > 40:  # skip centre where gate is
        lines.append(p(GREY, 240, 0, bz, FACE_W, "16577.dat"))  # Smaller arches
for bz in range(-160, 170, 80):
    if abs(bz) > 40:
        lines.append(p(GREY, 240, -56, bz, FACE_W, "2493b.dat"))
        lines.append(p(TRANS_CLEAR, 240, -56, bz, FACE_W, "2494.dat"))
for bz in range(-160, 170, 80):
    lines.append(p(RED, 240, -104, bz, FACE_W, "4162.dat"))

# West exterior facade (X = -240)
lines.append("0 STEP")
lines.append("0 West facade")
lines.append(p(GREY, -240, 0, 0, FACE_E, "15626.dat"))
for bz in range(-160, 170, 100):
    if abs(bz) > 40:
        lines.append(p(GREY, -240, 0, bz, FACE_E, "16577.dat"))
for bz in range(-160, 170, 80):
    if abs(bz) > 40:
        lines.append(p(GREY, -240, -56, bz, FACE_E, "2493b.dat"))
        lines.append(p(TRANS_CLEAR, -240, -56, bz, FACE_E, "2494.dat"))
for bz in range(-160, 170, 80):
    lines.append(p(RED, -240, -104, bz, FACE_E, "4162.dat"))

# Pitch-side perimeter fence (inside the stadium, around the grass)
lines.append("0 STEP")
lines.append("0 Pitch perimeter fence")
for bx in range(-160, 170, 40):
    lines.append(p(WHITE, bx, 0, -160, FACE_S, "15332.dat"))
    lines.append(p(WHITE, bx, 0, 160, FACE_N, "15332.dat"))
for bz in range(-120, 130, 40):
    lines.append(p(WHITE, -160, 0, bz, FACE_E, "15332.dat"))
    lines.append(p(WHITE, 160, 0, bz, FACE_W, "15332.dat"))

lines += ["", "", ""]

# ─────────────────────────────────────────────
# FLOODLIGHT PYLONS  (4 corner towers)
# ─────────────────────────────────────────────
lines += [
    "0 FILE stadium_floodlights.ldr",
    "0 Floodlight Pylons",
    "0 Name: stadium_floodlights.ldr",
    "0 Author: Claude",
    "0 !LDRAW_ORG Model",
    "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt",
    "",
    "0 STEP",
    "0 Four corner floodlight pylons",
]

pylon_corners = [
    (+260, +220),
    (-260, +220),
    (+260, -220),
    (-260, -220),
]

for (px, pz) in pylon_corners:
    # Pylon base
    lines.append(p(DARK_GREY, px, 0, pz, ID, "3003.dat"))    # 2×2 base
    # Pylon shaft — stack of 1×1 round bricks (use 3062b)
    for wy in range(-8, -200, -24):
        lines.append(p(DARK_GREY, px, wy, pz, ID, "3062b.dat"))
    # Pylon cap
    lines.append(p(RED, px, -200, pz, ID, "3942c.dat"))       # 2×2×2 cone
    # Floodlight arms — cross pattern
    lines.append(p(YELLOW, px - 10, -208, pz, ID, "3004.dat"))   # 1×2 arm left
    lines.append(p(YELLOW, px + 10, -208, pz, ID, "3004.dat"))   # 1×2 arm right
    lines.append(p(YELLOW, px, -208, pz - 10, ROT90Y, "3004.dat"))  # 1×2 arm front
    lines.append(p(YELLOW, px, -208, pz + 10, ROT90Y, "3004.dat"))  # 1×2 arm rear
    # Floodlight bulbs
    for (lx, lz) in [(px-10, pz), (px+10, pz), (px, pz-10), (px, pz+10)]:
        lines.append(p(YELLOW, lx, -216, lz, ID, "4589.dat"))  # Cone 1×1 = light
    # Top antenna
    lines.append(p(WHITE, px, -224, pz, ID, "3957a.dat"))

lines += ["", ""]

output = "\n".join(lines)
print(output)
