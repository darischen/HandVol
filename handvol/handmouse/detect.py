import math

# MediaPipe hand landmark indices.
WRIST = 0
THUMB_MCP = 2
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


def fingertip_curl(landmarks, mcp_idx, pip_idx, tip_idx):
    """Ratio of the tip-to-PIP distance over the PIP-to-MCP base length.

    A straight finger is ~1.3 or higher; the ratio drops well below 1 when the
    top of the finger hooks (tip, dip, pip cluster together) while the MCP->PIP
    base segment stays straight. This detects a comfortable fingertip half-bend
    rather than a full fist curl. Scale- and tilt-invariant because it is a
    ratio of two bone-length distances."""
    mcp = landmarks[mcp_idx]
    pip = landmarks[pip_idx]
    tip = landmarks[tip_idx]
    base = math.hypot(pip.x - mcp.x, pip.y - mcp.y)
    if base == 0:
        return 999.0
    return math.hypot(tip.x - pip.x, tip.y - pip.y) / base


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


THUMB_EXTEND_RATIO = 2.0  # thumb tip this much farther from wrist than its MCP


def thumb_extension_ratio(landmarks):
    """Thumb tip distance from the wrist over the thumb-MCP distance. Roughly 1
    when the thumb is tucked against the hand and grows as it is raised, so a
    higher engage threshold demands a more deliberate raise."""
    mcp_d = _dist_to_wrist(landmarks, THUMB_MCP)
    if mcp_d == 0:
        return 0.0
    return _dist_to_wrist(landmarks, THUMB_TIP) / mcp_d


def thumb_extended(landmarks, ratio=THUMB_EXTEND_RATIO):
    """True when the thumb is clearly raised (tip well beyond its own MCP from
    the wrist), as opposed to tucked or resting alongside the hand. A raised
    thumb engages scroll; otherwise the U stays in pointer + click mode. Index
    and middle stay straight either way, so this never collides with clicks."""
    if not landmarks or len(landmarks) < 21:
        return False
    return thumb_extension_ratio(landmarks) > ratio


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
