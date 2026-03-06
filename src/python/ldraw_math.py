from __future__ import annotations

import math
from typing import Iterable, Tuple, List

def ldraw_type1_matrix_to_euler_yxz(
    m: Iterable[Iterable[float]],
    *,
    degrees: bool = True,
    assume_ldraw_row_major: bool = True,
) -> Tuple[float, float, float]:
    """
    Extract Euler angles matching the description:
      yaw   = rotation around Y (vertical)
      pitch = rotation around X (side-to-side)
      roll  = rotation around Z (front-to-back)

    Using intrinsic Y-X-Z order:
        R = Ry(yaw) * Rx(pitch) * Rz(roll)

    Returns (yaw_y, pitch_x, roll_z).
    """

    # --- copy + validate ---
    M: List[List[float]] = [[float(x) for x in row] for row in m]
    if len(M) != 3 or any(len(row) != 3 for row in M):
        raise ValueError("Input must be a 3x3 matrix")

    if not assume_ldraw_row_major:
        M = [[M[r][c] for r in range(3)] for c in range(3)]

    # --- Orthonormalize to remove scale/shear (polar decomposition) ---
    try:
        import numpy as np  # type: ignore

        A = np.array(M, dtype=float)
        U, _, Vt = np.linalg.svd(A)
        R = U @ Vt
        if np.linalg.det(R) < 0:
            U[:, -1] *= -1
            R = U @ Vt

        r00, r01, r02 = float(R[0, 0]), float(R[0, 1]), float(R[0, 2])
        r10, r11, r12 = float(R[1, 0]), float(R[1, 1]), float(R[1, 2])
        r20, r21, r22 = float(R[2, 0]), float(R[2, 1]), float(R[2, 2])

    except Exception:
        # Lightweight fallback orthonormalization (rows)
        def dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
        def norm(v): return math.sqrt(dot(v, v))
        def sub(a, b): return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]
        def mul(v, s): return [v[0]*s, v[1]*s, v[2]*s]
        def cross(a, b):
            return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]

        x = M[0][:]
        y = M[1][:]

        nx = norm(x)
        if nx == 0:
            raise ValueError("Degenerate matrix")
        x = mul(x, 1.0 / nx)

        y = sub(y, mul(x, dot(x, y)))
        ny = norm(y)
        if ny == 0:
            raise ValueError("Degenerate matrix")
        y = mul(y, 1.0 / ny)

        z = cross(x, y)

        r00, r01, r02 = x[0], x[1], x[2]
        r10, r11, r12 = y[0], y[1], y[2]
        r20, r21, r22 = z[0], z[1], z[2]

    # --- Extract intrinsic Y-X-Z: R = Ry(yaw)*Rx(pitch)*Rz(roll) ---
    # From the derived form:
    #   r12 = -sin(pitch)
    #   r02 = sin(yaw)*cos(pitch)
    #   r22 = cos(yaw)*cos(pitch)
    #   r10 = cos(pitch)*sin(roll)
    #   r11 = cos(pitch)*cos(roll)

    sp = -r12
    sp = max(-1.0, min(1.0, sp))
    pitch = math.asin(sp)
    cp = math.cos(pitch)

    eps = 1e-9
    if abs(cp) > eps:
        yaw = math.atan2(r02, r22)
        roll = math.atan2(r10, r11)
    else:
        # Gimbal lock: cos(pitch) ~ 0, yaw/roll coupled.
        # Choose roll = 0 and solve yaw from the remaining terms.
        roll = 0.0
        yaw = math.atan2(-r20, r00)

    if degrees:
        return (math.degrees(yaw), math.degrees(pitch), math.degrees(roll))
    return (yaw, pitch, roll)


# # FIXME most likely wrong, according to GPT-5.2, see another implementation below
# def ldraw_type1_matrix_to_euler_xyz(
#     m: Iterable[Iterable[float]],
#     *,
#     degrees: bool = True,
#     assume_ldraw_row_major: bool = True,
# ) -> Tuple[float, float, float]:
#     """
#     Compute rotation (Euler angles) from the 3x3 a..i matrix of an LDraw type-1 line.

#     LDraw spec: type-1 line is
#         1 <colour> x y z a b c d e f g h i <file>
#     where a..i are the top-left 3x3 of the transform matrix and represent
#     rotation + scaling. :contentReference[oaicite:1]{index=1}

#     This function:
#       1) builds the 3x3 matrix from input,
#       2) removes scaling/shear using an SVD-based orthonormalization (polar decomposition),
#       3) returns Euler angles in XYZ intrinsic order (roll=X, pitch=Y, yaw=Z).
#          (Equivalent to extrinsic ZYX, depending on your convention.)

#     Parameters
#     ----------
#     m:
#         3x3 matrix as nested iterables.
#         If you parse directly from a..i, you likely want:
#             [[a, b, c],
#              [d, e, f],
#              [g, h, i]]
#         which matches the point transform equations:
#             u' = a*u + b*v + c*w + x
#             v' = d*u + e*v + f*w + y
#             w' = g*u + h*v + i*w + z   :contentReference[oaicite:2]{index=2}
#     degrees:
#         If True, returns angles in degrees; else radians.
#     assume_ldraw_row_major:
#         If True, uses the matrix as provided above. If your code stores
#         vectors as columns and you built the transpose, set this False.

#     Returns
#     -------
#     (roll_x, pitch_y, yaw_z):
#         Euler angles in XYZ intrinsic rotation order.
#     """
#     # --- Basic validation & copy to float matrix ---
#     M: List[List[float]] = [[float(x) for x in row] for row in m]
#     if len(M) != 3 or any(len(row) != 3 for row in M):
#         raise ValueError("Input must be a 3x3 matrix")

#     # If caller built a column-major version, transpose here
#     if not assume_ldraw_row_major:
#         M = [[M[r][c] for r in range(3)] for c in range(3)]

#     # --- Orthonormalize to extract rotation (remove scale/shear) ---
#     # We implement a small 3x3 SVD using numpy if available; otherwise do a robust Gram-Schmidt.
#     try:
#         import numpy as np  # type: ignore

#         A = np.array(M, dtype=float)
#         U, _, Vt = np.linalg.svd(A)
#         R = U @ Vt

#         # Fix improper rotation (reflection) if det(R) < 0
#         if np.linalg.det(R) < 0:
#             U[:, -1] *= -1
#             R = U @ Vt

#         r00, r01, r02 = float(R[0, 0]), float(R[0, 1]), float(R[0, 2])
#         r10, r11, r12 = float(R[1, 0]), float(R[1, 1]), float(R[1, 2])
#         r20, r21, r22 = float(R[2, 0]), float(R[2, 1]), float(R[2, 2])

#     except Exception:
#         # Fallback: Gram-Schmidt on rows (reasonable for near-rotation matrices)
#         def dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
#         def norm(v): return math.sqrt(dot(v, v))
#         def sub(a, b): return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]
#         def mul(v, s): return [v[0]*s, v[1]*s, v[2]*s]
#         def cross(a, b):
#             return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]

#         x = M[0][:]
#         y = M[1][:]
#         # Orthonormalize x, then y, then z = x × y
#         nx = norm(x)
#         if nx == 0:
#             raise ValueError("Degenerate matrix: first basis vector has zero length")
#         x = mul(x, 1.0 / nx)

#         y = sub(y, mul(x, dot(x, y)))
#         ny = norm(y)
#         if ny == 0:
#             raise ValueError("Degenerate matrix: second basis vector collapses after orthogonalization")
#         y = mul(y, 1.0 / ny)

#         z = cross(x, y)

#         r00, r01, r02 = x[0], x[1], x[2]
#         r10, r11, r12 = y[0], y[1], y[2]
#         r20, r21, r22 = z[0], z[1], z[2]

#     # --- Convert rotation matrix to Euler XYZ (intrinsic) ---
#     # For intrinsic XYZ:
#     #   R = Rz(yaw) * Ry(pitch) * Rx(roll)   (extrinsic)  <->  intrinsic XYZ
#     # Common stable extraction:
#     sy = -r20
#     sy = max(-1.0, min(1.0, sy))
#     pitch = math.asin(sy)

#     # Check for gimbal lock
#     cos_pitch = math.cos(pitch)
#     eps = 1e-9
#     if abs(cos_pitch) > eps:
#         roll = math.atan2(r21, r22)
#         yaw = math.atan2(r10, r00)
#     else:
#         # Gimbal lock: pitch ~= +/-90deg
#         # roll and yaw become coupled; set yaw=0 and derive roll from other terms
#         yaw = 0.0
#         roll = math.atan2(-r01, r11)

#     if degrees:
#         return (math.degrees(roll), math.degrees(pitch), math.degrees(yaw))
#     return (roll, pitch, yaw)



