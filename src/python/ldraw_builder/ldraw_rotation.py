"""
Euler angles → LDraw 3×3 rotation matrix.

Inverse of ldraw_math.ldraw_type1_matrix_to_euler_yxz.

Convention (matches ldraw_math.py):
  Intrinsic Y-X-Z order:  R = Ry(yaw) · Rx(pitch) · Rz(roll)
  All input angles in degrees.
  Output is a row-major 3×3 matrix as used in the LDraw Type-1 line:
      1 <color> x y z  a b c  d e f  g h i  <file>
  where [a b c / d e f / g h i] transforms local → world:
      u' = a·u + b·v + c·w + x
      v' = d·u + e·v + f·w + y
      w' = g·u + h·v + i·w + z

LDraw coordinate system: right-handed, -Y is "up".
"""

import math

# Type alias for readability
Matrix3x3 = list[list[float]]


def identity() -> Matrix3x3:
    """Identity rotation — part placed with no rotation."""
    return [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]


def from_euler(yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0) -> Matrix3x3:
    """
    Build a LDraw row-major 3×3 rotation matrix from Euler angles (degrees).

    Intrinsic Y-X-Z order: R = Ry(yaw) · Rx(pitch) · Rz(roll)

    Matches the decomposition used in ldraw_math.ldraw_type1_matrix_to_euler_yxz,
    so round-tripping through that function recovers the original angles.

    yaw   — rotation around Y (turn left/right when viewed from above)
    pitch — rotation around X (tilt forward/back)
    roll  — rotation around Z (tilt sideways)
    """
    if yaw == 0.0 and pitch == 0.0 and roll == 0.0:
        return identity()

    y = math.radians(yaw)
    x = math.radians(pitch)
    z = math.radians(roll)

    cy, sy = math.cos(y), math.sin(y)
    cx, sx = math.cos(x), math.sin(x)
    cz, sz = math.cos(z), math.sin(z)

    # R = Ry · Rx · Rz  (derived analytically)
    return [
        [ cy*cz + sy*sx*sz,  -cy*sz + sy*sx*cz,  sy*cx],
        [ cx*sz,              cx*cz,             -sx   ],
        [-sy*cz + cy*sx*sz,   sy*sz + cy*sx*cz,  cy*cx],
    ]
