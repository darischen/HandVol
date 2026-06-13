import math

# MediaPipe hand landmark indices.
WRIST = 0
THUMB_TIP = 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_TIP = 13, 16
PINKY_MCP, PINKY_TIP = 17, 20


def mcp_midpoint(landmarks):
    """(x, y) midpoint of the index and middle MCP knuckles."""
    a = landmarks[INDEX_MCP]
    b = landmarks[MIDDLE_MCP]
    return ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)


def hand_scale(landmarks):
    """Distance from the wrist to the MCP midpoint. Used to normalize all
    other distances so detection is invariant to how close the hand is."""
    mx, my = mcp_midpoint(landmarks)
    w = landmarks[WRIST]
    return math.hypot(mx - w.x, my - w.y)


def hand_axis(landmarks):
    """Unit vector pointing from the wrist toward the MCP midpoint — the
    direction the hand 'points'. Rotation-invariant basis for projection."""
    mx, my = mcp_midpoint(landmarks)
    w = landmarks[WRIST]
    dx, dy = mx - w.x, my - w.y
    length = math.hypot(dx, dy)
    if length == 0:
        return (0.0, -1.0)
    return (dx / length, dy / length)


def projected_point(landmarks, k=1.0):
    """Cursor point in normalized frame coords. Starts at the MCP midpoint and
    projects forward along the hand axis by k * hand_scale, so it sits up near
    the fingertips while being computed only from the wrist and knuckles. This
    keeps it steady when a fingertip curls to click."""
    mx, my = mcp_midpoint(landmarks)
    ax, ay = hand_axis(landmarks)
    scale = hand_scale(landmarks)
    return (mx + ax * k * scale, my + ay * k * scale)


def pip_angle(landmarks, mcp_idx, pip_idx, tip_idx):
    """Angle in degrees at the PIP joint, between the bones MCP->PIP and
    PIP->TIP. A straight finger is near 180 degrees; a bent finger drops well
    below. Angle-based, so it reads the same across hand tilt and hand size."""
    mcp = landmarks[mcp_idx]
    pip = landmarks[pip_idx]
    tip = landmarks[tip_idx]
    v1x, v1y = mcp.x - pip.x, mcp.y - pip.y
    v2x, v2y = tip.x - pip.x, tip.y - pip.y
    n1 = math.hypot(v1x, v1y)
    n2 = math.hypot(v2x, v2y)
    if n1 == 0 or n2 == 0:
        return 180.0
    cos = (v1x * v2x + v1y * v2y) / (n1 * n2)
    cos = max(-1.0, min(1.0, cos))
    return math.degrees(math.acos(cos))
