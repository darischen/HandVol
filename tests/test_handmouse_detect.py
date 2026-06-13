import math

from handvol.handmouse import detect


class LM:
    """Minimal stand-in for a MediaPipe NormalizedLandmark."""
    def __init__(self, x, y, z=0.0):
        self.x = x
        self.y = y
        self.z = z


def make_u_hand():
    """An upright right hand making the ASL 'U': index + middle extended and
    together, ring + pinky curled, thumb tucked to the side (not touching).
    Coordinates are normalized [0,1], y grows downward (image convention)."""
    return [
        LM(0.50, 0.90),  # 0 wrist
        LM(0.42, 0.80),  # 1 thumb cmc
        LM(0.38, 0.72),  # 2 thumb mcp
        LM(0.36, 0.66),  # 3 thumb ip
        LM(0.36, 0.60),  # 4 thumb tip (tucked, away from index base)
        LM(0.45, 0.60),  # 5 index mcp
        LM(0.44, 0.45),  # 6 index pip
        LM(0.43, 0.35),  # 7 index dip
        LM(0.43, 0.25),  # 8 index tip
        LM(0.52, 0.60),  # 9 middle mcp
        LM(0.53, 0.45),  # 10 middle pip
        LM(0.54, 0.35),  # 11 middle dip
        LM(0.54, 0.25),  # 12 middle tip
        LM(0.58, 0.62),  # 13 ring mcp
        LM(0.58, 0.55),  # 14 ring pip
        LM(0.575, 0.60), # 15 ring dip (curled back down)
        LM(0.57, 0.65),  # 16 ring tip (curled, near wrist)
        LM(0.63, 0.64),  # 17 pinky mcp
        LM(0.63, 0.58),  # 18 pinky pip
        LM(0.625, 0.62), # 19 pinky dip
        LM(0.62, 0.66),  # 20 pinky tip (curled)
    ]


def test_mcp_midpoint_is_between_index_and_middle_mcp():
    hand = make_u_hand()
    mx, my = detect.mcp_midpoint(hand)
    assert mx == (0.45 + 0.52) / 2
    assert my == (0.60 + 0.60) / 2


def test_hand_scale_is_wrist_to_mcp_midpoint_distance():
    hand = make_u_hand()
    mx, my = detect.mcp_midpoint(hand)
    expected = math.hypot(mx - 0.50, my - 0.90)
    assert detect.hand_scale(hand) == expected


def test_hand_axis_points_from_wrist_toward_fingers_and_is_unit_length():
    hand = make_u_hand()
    ax, ay = detect.hand_axis(hand)
    assert math.isclose(math.hypot(ax, ay), 1.0, rel_tol=1e-9)
    # Fingers are above the wrist (smaller y), so the axis points up (ay < 0).
    assert ay < 0
