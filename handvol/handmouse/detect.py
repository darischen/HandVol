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


EXTEND_RATIO = 1.6   # tip must be this much farther from wrist than its MCP
CURL_RATIO = 1.25    # curled tip stays within this * its MCP distance
TOGETHER_RATIO = 2.0  # index/middle tips closer than this * their MCP gap

# Sign of hand_normal_z that means "palm toward camera". The canonical
# make_u_hand (a user's right hand, MediaPipe label "Left") yields a positive
# normal, so "Left" expects > 0. Flip these if real-world testing shows the
# pose only registers when the back of the hand faces the camera.
PALM_SIGN = {"Left": 1.0, "Right": -1.0}


def _dist_to_wrist(landmarks, idx):
    w = landmarks[WRIST]
    p = landmarks[idx]
    return math.hypot(p.x - w.x, p.y - w.y)


def _extended(landmarks, mcp_idx, tip_idx):
    return _dist_to_wrist(landmarks, tip_idx) > _dist_to_wrist(landmarks, mcp_idx) * EXTEND_RATIO


def _curled(landmarks, mcp_idx, tip_idx):
    return _dist_to_wrist(landmarks, tip_idx) < _dist_to_wrist(landmarks, mcp_idx) * CURL_RATIO


def hand_normal_z(landmarks):
    """Z component of the hand-plane normal, as a 2D cross product of
    wrist->index_MCP and wrist->pinky_MCP. Its sign flips between palm-facing
    and back-facing for a given hand."""
    w = landmarks[WRIST]
    i = landmarks[INDEX_MCP]
    p = landmarks[PINKY_MCP]
    v1x, v1y = i.x - w.x, i.y - w.y
    v2x, v2y = p.x - w.x, p.y - w.y
    return v1x * v2y - v1y * v2x


def palm_facing(landmarks, handedness):
    """True when the palm faces the camera for the given MediaPipe handedness."""
    sign = PALM_SIGN.get(handedness)
    if sign is None:
        return False
    return hand_normal_z(landmarks) * sign > 0


THUMB_TOUCH_RATIO = 0.2  # thumb tip within this * hand_scale of the index base


def thumb_touch(landmarks):
    """True when the thumb pad rests on the side/base of the index finger
    (near its MCP). Engages scroll while index + middle stay straight, so it
    never collides with the bend-based clicks."""
    if not landmarks or len(landmarks) < 21:
        return False
    t = landmarks[THUMB_TIP]
    base = landmarks[INDEX_MCP]
    d = math.hypot(t.x - base.x, t.y - base.y)
    return d < hand_scale(landmarks) * THUMB_TOUCH_RATIO


def detect_u_sign(landmarks, handedness):
    """Strict U pose used to ENTER pointer mode: index + middle extended and
    held together, ring + pinky curled, palm facing the camera."""
    if not landmarks or len(landmarks) < 21:
        return False
    if not palm_facing(landmarks, handedness):
        return False
    if not (_extended(landmarks, INDEX_MCP, INDEX_TIP)
            and _extended(landmarks, MIDDLE_MCP, MIDDLE_TIP)):
        return False
    if not (_curled(landmarks, RING_MCP, RING_TIP)
            and _curled(landmarks, PINKY_MCP, PINKY_TIP)):
        return False
    tip_gap = math.hypot(landmarks[INDEX_TIP].x - landmarks[MIDDLE_TIP].x,
                         landmarks[INDEX_TIP].y - landmarks[MIDDLE_TIP].y)
    mcp_gap = math.hypot(landmarks[INDEX_MCP].x - landmarks[MIDDLE_MCP].x,
                         landmarks[INDEX_MCP].y - landmarks[MIDDLE_MCP].y)
    if mcp_gap == 0 or tip_gap > mcp_gap * TOGETHER_RATIO:
        return False
    return True
