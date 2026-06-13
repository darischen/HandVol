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
