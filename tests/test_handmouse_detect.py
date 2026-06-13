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


def test_projected_point_lands_ahead_of_mcp_toward_fingers():
    hand = make_u_hand()
    mx, my = detect.mcp_midpoint(hand)
    px, py = detect.projected_point(hand, k=1.0)
    # The projected point sits beyond the MCP midpoint in the finger direction
    # (upward => smaller y), i.e. nearer the fingertips.
    assert py < my
    # It stays roughly under the fingers horizontally.
    assert abs(px - mx) < 0.1


def test_projected_point_is_stable_when_a_fingertip_bends():
    straight = make_u_hand()
    bent = make_u_hand()
    # Simulate a left-click: curl the index tip down toward the palm.
    bent[detect.INDEX_TIP] = LM(0.45, 0.55)
    bent[detect.INDEX_DIP] = LM(0.45, 0.58)
    p_straight = detect.projected_point(straight, k=1.0)
    p_bent = detect.projected_point(bent, k=1.0)
    # Cursor barely moves because it is built from wrist + knuckles, not tips.
    assert math.hypot(p_bent[0] - p_straight[0], p_bent[1] - p_straight[1]) < 0.01


def test_pip_angle_straight_finger_near_180():
    hand = make_u_hand()
    angle = detect.pip_angle(hand, detect.INDEX_MCP, detect.INDEX_PIP, detect.INDEX_TIP)
    assert angle > 150


def test_pip_angle_bent_finger_is_small():
    hand = make_u_hand()
    # Curl the index: tip folds back toward the MCP.
    hand[detect.INDEX_DIP] = LM(0.45, 0.55)
    hand[detect.INDEX_TIP] = LM(0.47, 0.62)
    angle = detect.pip_angle(hand, detect.INDEX_MCP, detect.INDEX_PIP, detect.INDEX_TIP)
    assert angle < 110


def test_hand_normal_z_flips_sign_when_hand_is_mirrored():
    hand = make_u_hand()
    z = detect.hand_normal_z(hand)
    mirrored = [LM(1.0 - lm.x, lm.y, lm.z) for lm in hand]
    zm = detect.hand_normal_z(mirrored)
    assert (z > 0) != (zm > 0)


def test_detect_u_sign_true_for_canonical_u():
    hand = make_u_hand()
    # In this mirrored selfie pipeline MediaPipe labels the user's right hand
    # as "Left" (same convention capture.py's side-thumb detector relies on).
    assert detect.detect_u_sign(hand, "Left") is True


def test_detect_u_sign_false_when_fingers_spread_like_victory():
    hand = make_u_hand()
    # Spread the tips far apart -> Victory, not U.
    hand[detect.INDEX_TIP] = LM(0.30, 0.25)
    hand[detect.MIDDLE_TIP] = LM(0.70, 0.25)
    assert detect.detect_u_sign(hand, "Left") is False


def test_detect_u_sign_false_when_ring_extended():
    hand = make_u_hand()
    hand[detect.RING_TIP] = LM(0.60, 0.25)  # ring now extended
    assert detect.detect_u_sign(hand, "Left") is False


def test_detect_u_sign_false_for_wrong_handedness():
    hand = make_u_hand()
    # Same coords but the opposite handedness => palm-facing check rejects.
    assert detect.detect_u_sign(hand, "Right") is False


def test_thumb_touch_false_when_thumb_tucked():
    hand = make_u_hand()
    assert detect.thumb_touch(hand) is False


def test_thumb_touch_true_when_thumb_pad_near_index_base():
    hand = make_u_hand()
    # Move the thumb tip onto the index MCP (knuckle/base), index still straight.
    hand[detect.THUMB_TIP] = LM(0.45, 0.60)
    assert detect.thumb_touch(hand) is True
