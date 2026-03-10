#!/usr/bin/env python3
"""
Generate a large translucent blue globe (tianqiu) vase as an LDraw model.

The vase is built as a hollow rotational body using 1x1 bricks as voxels.
It has:
  - A large spherical body (bulging globe shape)
  - A tall narrow cylindrical neck that flares slightly at the rim
  - Hollow interior (it's a vase, not a solid!)
  - Gradient coloring: darker transparent blue at the bottom,
    lighter transparent blue toward the top/neck
  - Wall thickness of 1-2 voxels

The profile is defined as a radius function of height, then swept
360 degrees to create the rotational body. Only the shell is kept.

Coordinate system (LDraw):
  X = left/right
  Y = up (negative in LDraw)
  Z = front/back

Each voxel = 1 Brick 1x1 = 20 LDU wide, 24 LDU tall
We use 20 LDU spacing on X/Z (stud pitch) and 24 LDU on Y (brick height).
"""

import math
import sys

# ============================================================
# CONFIGURATION
# ============================================================

OUTPUT_FILE = "generated_vase.mpd"
PART = "3005.dat"       # Brick 1x1 (24 LDU tall, 20 LDU wide)

STUD = 20               # LDU horizontal pitch
BRICK_H = 24            # LDU vertical pitch (brick height)

# Vase dimensions in voxel units
VASE_TOTAL_HEIGHT = 60  # Total height in bricks
BODY_MAX_RADIUS = 18    # Max radius of the globe body
NECK_RADIUS = 5         # Radius of the neck
RIM_RADIUS = 6          # Slight flare at the top rim
WALL_THICKNESS = 1.5    # Shell thickness in voxels

# Transparent blue gradient colors (bottom to top)
# Bottom = darkest, top = lightest
COLORS_GRADIENT = [
    33,    # Trans_Dark_Blue       (bottom, darkest)
    33,    # Trans_Dark_Blue
    33,    # Trans_Dark_Blue
    41,    # Trans_Medium_Blue
    41,    # Trans_Medium_Blue
    41,    # Trans_Medium_Blue
    293,   # Trans_Light_Blue_Violet
    293,   # Trans_Light_Blue_Violet
    43,    # Trans_Light_Blue
    43,    # Trans_Light_Blue       (top rim, lightest)
]

# ============================================================
# VASE PROFILE DEFINITION
# ============================================================

def vase_outer_radius(y_norm):
    """
    Define the outer radius of the vase at normalized height y_norm (0=bottom, 1=top).
    
    Profile:
      0.00 - 0.05: Small base (radius ~6, slight foot)
      0.05 - 0.55: Globe body (swelling to max radius ~18)
      0.55 - 0.65: Shoulder (radius decreasing from ~18 to ~6)
      0.65 - 0.90: Neck (narrow cylinder, radius ~5)
      0.90 - 1.00: Rim (slight flare to ~6)
    """
    if y_norm < 0.0 or y_norm > 1.0:
        return 0
    
    # Base/foot
    if y_norm < 0.05:
        t = y_norm / 0.05
        return 4 + t * 3  # 4 -> 7
    
    # Globe body (using a sine-like curve for smooth bulge)
    if y_norm < 0.55:
        t = (y_norm - 0.05) / 0.50
        # Sine curve from 0 to pi gives nice bulge
        r = 7 + (BODY_MAX_RADIUS - 7) * math.sin(t * math.pi)
        return r
    
    # Shoulder transition (globe to neck)
    if y_norm < 0.65:
        t = (y_norm - 0.55) / 0.10
        r_start = 7 + (BODY_MAX_RADIUS - 7) * math.sin(1.0 * math.pi)  # ~7
        # Actually recalculate: at y_norm=0.55, t_body=1.0, sin(pi)=0 -> r=7
        # So shoulder goes from ~7 down to neck radius
        # Let's use a cosine ease
        r = NECK_RADIUS + (7 - NECK_RADIUS) * (1 - t)
        return r
    
    # Neck (narrow cylinder with very slight taper)
    if y_norm < 0.90:
        t = (y_norm - 0.65) / 0.25
        return NECK_RADIUS + t * 0.3  # Very slight widening
    
    # Rim (flares out slightly)
    t = (y_norm - 0.90) / 0.10
    r = (NECK_RADIUS + 0.3) + t * (RIM_RADIUS - NECK_RADIUS)
    return r


def vase_inner_radius(y_norm):
    """Inner radius = outer radius minus wall thickness. 0 means solid."""
    outer = vase_outer_radius(y_norm)
    if outer <= WALL_THICKNESS + 0.5:
        return 0  # Too thin to hollow
    inner = outer - WALL_THICKNESS
    
    # Ensure the base is solid (no hole at bottom)
    if y_norm < 0.04:
        return 0
    
    return max(0, inner)


def get_color_for_height(y_norm):
    """Get the gradient color based on normalized height."""
    idx = int(y_norm * (len(COLORS_GRADIENT) - 1))
    idx = max(0, min(len(COLORS_GRADIENT) - 1, idx))
    return COLORS_GRADIENT[idx]


# ============================================================
# VOXEL GENERATION
# ============================================================

def generate_vase():
    """Generate all voxels for the vase by sweeping the profile."""
    voxels = {}  # (vx, vy, vz) -> color_code
    
    for vy in range(VASE_TOTAL_HEIGHT):
        y_norm = vy / (VASE_TOTAL_HEIGHT - 1)
        
        outer_r = vase_outer_radius(y_norm)
        inner_r = vase_inner_radius(y_norm)
        color = get_color_for_height(y_norm)
        
        if outer_r < 0.5:
            continue  # No voxel at this height
        
        # Maximum integer radius to check
        max_r_int = int(math.ceil(outer_r)) + 1
        
        for vx in range(-max_r_int, max_r_int + 1):
            for vz in range(-max_r_int, max_r_int + 1):
                dist = math.sqrt(vx * vx + vz * vz)
                
                # Check if this voxel is within the shell
                if dist <= outer_r and dist >= inner_r:
                    voxels[(vx, vy, vz)] = color
                    
                # For the very top layer, add the rim opening
                # (don't fill the top if it's the neck - keep it open)
    
    # Make sure the top is open (it's a vase!)
    top_y = VASE_TOTAL_HEIGHT - 1
    y_norm_top = 1.0
    inner_top = vase_inner_radius(y_norm_top)
    # Remove any voxels inside the opening at the top
    # (they shouldn't exist due to inner_r, but just in case)
    
    return voxels


def hollow_check(voxels):
    """
    Optional: Remove completely hidden interior voxels.
    A voxel is hidden if all 6 neighbors exist.
    """
    directions = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
    visible = {}
    for pos, color in voxels.items():
        x, y, z = pos
        exposed = False
        for dx, dy, dz in directions:
            if (x+dx, y+dy, z+dz) not in voxels:
                exposed = True
                break
        if exposed:
            visible[pos] = color
    return visible


# ============================================================
# LDraw OUTPUT
# ============================================================

def write_ldraw(voxels, filename):
    """Write voxels as an LDraw MPD file."""
    with open(filename, 'w') as f:
        f.write("0 FILE vase.ldr\n")
        f.write("0 Transparent Blue Globe Vase\n")
        f.write("0 Name: vase.ldr\n")
        f.write("0 Author: Claude\n")
        f.write("0 !LDRAW_ORG Model\n")
        f.write("0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt\n\n")
        
        # Sort by Y layer (bottom to top) for build order
        sorted_voxels = sorted(voxels.items(), key=lambda v: (v[0][1], v[0][0], v[0][2]))
        
        current_y = None
        layer_count = 0
        for (vx, vy, vz), color in sorted_voxels:
            if vy != current_y:
                if current_y is not None:
                    f.write("0 STEP\n")
                current_y = vy
                layer_count += 1
            
            # Convert voxel coords to LDraw coords
            lx = vx * STUD
            ly = -(vy * BRICK_H)  # LDraw Y is inverted (negative = up)
            lz = vz * STUD
            
            f.write(f"1 {color} {lx} {ly} {lz} 1 0 0 0 1 0 0 0 1 {PART}\n")
        
        f.write("0 STEP\n\n")
    
    return layer_count


# ============================================================
# PREVIEW GENERATION
# ============================================================

def generate_preview(voxels, filename):
    """Generate a front-view preview image."""
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not available, skipping preview")
        return
    
    # Color map
    color_rgb = {
        33:  (0, 32, 160),    # Trans_Dark_Blue
        41:  (85, 154, 183),   # Trans_Medium_Blue
        43:  (174, 233, 239),  # Trans_Light_Blue
        293: (107, 171, 228),  # Trans_Light_Blue_Violet
    }
    
    SCALE = 6
    
    xs = [p[0] for p in voxels]
    ys = [p[1] for p in voxels]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    W = max_x - min_x + 1
    H = max_y - min_y + 1
    
    # Front view: project onto X-Y plane (min Z wins)
    front = {}
    for (vx, vy, vz), color in voxels.items():
        key = (vx, vy)
        if key not in front or vz < front[key][0]:
            front[key] = (vz, color)
    
    img = Image.new("RGB", (W * SCALE, H * SCALE), (240, 240, 240))
    px = img.load()
    for (vx, vy), (_, color) in front.items():
        rgb = color_rgb.get(color, (100, 150, 200))
        for dy in range(SCALE):
            for dx in range(SCALE):
                ix = (vx - min_x) * SCALE + dx
                iy = (max_y - vy) * SCALE + dy  # flip Y
                if 0 <= ix < img.width and 0 <= iy < img.height:
                    edge = dx == 0 or dy == 0
                    if edge:
                        px[ix, iy] = tuple(max(0, c - 40) for c in rgb)
                    else:
                        px[ix, iy] = rgb
    
    img.save(filename)
    print(f"Preview saved to {filename}")
    
    # Side cross-section view
    side = {}
    for (vx, vy, vz), color in voxels.items():
        if vx == 0:  # Center slice
            key = (vz, vy)
            side[key] = color
    
    zs_side = [p[0] for p in side]
    if zs_side:
        min_z, max_z = min(zs_side), max(zs_side)
        D = max_z - min_z + 1
        img2 = Image.new("RGB", (D * SCALE, H * SCALE), (240, 240, 240))
        px2 = img2.load()
        for (vz, vy), color in side.items():
            rgb = color_rgb.get(color, (100, 150, 200))
            for dy in range(SCALE):
                for dz in range(SCALE):
                    ix = (vz - min_z) * SCALE + dz
                    iy = (max_y - vy) * SCALE + dy
                    if 0 <= ix < img2.width and 0 <= iy < img2.height:
                        px2[ix, iy] = rgb
        img2.save(filename.replace("front", "cross_section"))
        print(f"Cross-section saved to {filename.replace('front', 'cross_section')}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("TRANSPARENT BLUE GLOBE VASE GENERATOR")
    print("=" * 60)
    
    # Step 1: Generate profile info
    print("\nVase profile (radius at each height):")
    for i in range(0, VASE_TOTAL_HEIGHT, 5):
        y_norm = i / (VASE_TOTAL_HEIGHT - 1)
        outer = vase_outer_radius(y_norm)
        inner = vase_inner_radius(y_norm)
        color = get_color_for_height(y_norm)
        bar = "#" * int(outer)
        hole = "." * int(inner) if inner > 0 else ""
        print(f"  Y={i:3d} (h={y_norm:.2f}): R_out={outer:5.1f}  R_in={inner:5.1f}  color={color}  {bar}")
    
    # Step 2: Generate voxels
    print("\nGenerating voxels...")
    voxels = generate_vase()
    print(f"  Raw voxels: {len(voxels)}")
    
    # Step 3: Remove hidden interior
    print("Removing hidden voxels...")
    voxels = hollow_check(voxels)
    print(f"  Visible voxels: {len(voxels)}")
    
    # Step 4: Statistics
    from collections import Counter
    color_counts = Counter(voxels.values())
    print(f"\nColor breakdown:")
    color_names = {33: "Trans_Dark_Blue", 41: "Trans_Medium_Blue",
                   43: "Trans_Light_Blue", 293: "Trans_Light_Blue_Violet"}
    for code, count in color_counts.most_common():
        print(f"  {color_names.get(code, str(code))}: {count}")
    
    xs = [p[0] for p in voxels]
    ys = [p[1] for p in voxels]
    zs = [p[2] for p in voxels]
    print(f"\nBounding box: X[{min(xs)},{max(xs)}] Y[{min(ys)},{max(ys)}] Z[{min(zs)},{max(zs)}]")
    print(f"Dimensions: {max(xs)-min(xs)+1} x {max(ys)-min(ys)+1} x {max(zs)-min(zs)+1} voxels")
    print(f"Physical size: {(max(xs)-min(xs)+1)*20} x {(max(ys)-min(ys)+1)*24} x {(max(zs)-min(zs)+1)*20} LDU")
    
    # Step 5: Write LDraw file
    print(f"\nWriting LDraw file to {OUTPUT_FILE}...")
    layers = write_ldraw(voxels, OUTPUT_FILE)
    print(f"  Written {len(voxels)} bricks across {layers} layers")
    
    # Step 6: Generate preview
    print("\nGenerating previews...")
    generate_preview(voxels, "vase_front.png")
    
    print(f"\n{'=' * 60}")
    print(f"DONE! Total pieces: {len(voxels)}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
