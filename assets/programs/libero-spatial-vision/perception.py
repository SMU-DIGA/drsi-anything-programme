"""Explicit (non-learned) RGB-D perception helpers."""

import numpy as np
import cv2

TABLE_Z = 0.90


def backproject(depth, K, E):
    """Depth image (metres, z-depth) -> HxWx3 world points. E is camera-to-world (OpenCV axes)."""
    depth = np.asarray(depth, float)
    if depth.ndim == 3:
        depth = depth[..., 0]
    H, W = depth.shape
    v, u = np.mgrid[0:H, 0:W]
    x = (u - K[0, 2]) * depth / K[0, 0]
    y = (v - K[1, 2]) * depth / K[1, 1]
    pc = np.stack([x, y, depth], -1)
    return pc @ E[:3, :3].T + E[:3, 3]


def masks(img, P):
    """Pixel masks of bowl-coloured (neutral / bluish grey) and plate-coloured points."""
    img = np.asarray(img)
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    S = hsv[..., 1].astype(int)
    V = hsv[..., 2].astype(int)
    R = img[..., 0].astype(int)
    B = img[..., 2].astype(int)
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    in_ws = (np.abs(x) < 0.45) & (np.abs(y) < 0.55) & (z > TABLE_Z - 0.05) & (z < 1.25)
    bowl = (S < 30) & (B - R >= -2) & (V > 15) & (V < 215) & in_ws & (z > TABLE_Z + 0.004)
    # plate: bright, nearly unsaturated, flat, slightly warm/neutral
    plate = (V > 140) & (S < 40) & (R - B >= -1) & in_ws & (z < TABLE_Z + 0.04)
    return bowl, plate
