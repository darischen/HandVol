from handvol.handmouse.pointer import OneEuroFilter


def test_constant_input_returns_constant():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0, d_cutoff=1.0)
    t = 0.0
    out = []
    for _ in range(10):
        out.append(f(0.5, t))
        t += 1 / 30
    assert all(abs(v - 0.5) < 1e-9 for v in out)


def test_output_moves_toward_a_step_input_but_lags():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0, d_cutoff=1.0)
    t = 0.0
    f(0.0, t)            # establish baseline at 0
    t += 1 / 30
    first = f(1.0, t)    # step to 1.0
    assert 0.0 < first < 1.0          # lagged, not instant
    prev = first
    for _ in range(30):
        t += 1 / 30
        cur = f(1.0, t)
        assert cur >= prev - 1e-9     # monotonically approaches the target
        prev = cur
    assert prev > 0.9                 # converges close to 1.0


def test_reset_restores_initial_behavior():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0, d_cutoff=1.0)
    f(0.0, 0.0)
    f(1.0, 1 / 30)
    f.reset()
    assert f(0.7, 0.0) == 0.7         # first call after reset returns input


from handvol.handmouse.pointer import AbsoluteMapper


def test_absolute_center_of_active_region_maps_to_screen_center():
    m = AbsoluteMapper(screen_w=1920, screen_h=1080, active=0.65)
    x, y = m.map((0.5, 0.5), just_acquired=True)
    assert x == 960
    assert y == 540


def test_absolute_active_region_edge_maps_to_screen_edge():
    m = AbsoluteMapper(screen_w=1920, screen_h=1080, active=0.65)
    lo = (1 - 0.65) / 2  # 0.175
    x0, y0 = m.map((lo, lo), just_acquired=False)
    x1, y1 = m.map((1 - lo, 1 - lo), just_acquired=False)
    assert (x0, y0) == (0, 0)
    assert (x1, y1) == (1920, 1080)


def test_absolute_lift_shifts_active_region_up():
    m = AbsoluteMapper(screen_w=1000, screen_h=1000, active=0.65, lift=0.15)
    # Screen bottom now maps to a higher (smaller-y) hand position than the
    # un-lifted 0.825, making the taskbar easier to reach.
    _, y = m.map((0.5, 0.825 - 0.15), just_acquired=False)
    assert y == 1000
    # Frame center now maps below screen center because the box moved up.
    _, yc = m.map((0.5, 0.5), just_acquired=False)
    assert yc > 500


def test_absolute_clamps_outside_active_region():
    m = AbsoluteMapper(screen_w=1920, screen_h=1080, active=0.65)
    x, y = m.map((0.0, 0.0), just_acquired=False)
    assert (x, y) == (0, 0)
    x, y = m.map((1.0, 1.0), just_acquired=False)
    assert (x, y) == (1920, 1080)


from handvol.handmouse.pointer import RelativeMapper


def test_relative_first_map_after_acquire_does_not_jump():
    m = RelativeMapper(screen_w=1920, screen_h=1080, gain=1.0)
    m.set_cursor(900, 500)
    x, y = m.map((0.2, 0.2), just_acquired=True)
    assert (x, y) == (900, 500)  # establishes reference, no move


def test_relative_accumulates_deltas():
    m = RelativeMapper(screen_w=1920, screen_h=1080, gain=1.0)
    m.set_cursor(900, 500)
    m.map((0.5, 0.5), just_acquired=True)        # reference
    x, y = m.map((0.6, 0.5), just_acquired=False)  # +0.1 of width
    assert x == 900 + int(round(0.1 * 1920))
    assert y == 500


def test_relative_clutch_resets_reference_on_reacquire():
    m = RelativeMapper(screen_w=1920, screen_h=1080, gain=1.0)
    m.set_cursor(900, 500)
    m.map((0.5, 0.5), just_acquired=True)
    m.map((0.7, 0.5), just_acquired=False)       # cursor moves right
    moved_x, moved_y = m.map((0.2, 0.2), just_acquired=True)  # re-acquire elsewhere
    assert (moved_x, moved_y) == (m.cursor_x, m.cursor_y)  # no jump on reacquire


def test_relative_clamps_to_screen_bounds():
    m = RelativeMapper(screen_w=1920, screen_h=1080, gain=10.0)
    m.set_cursor(0, 0)
    m.map((0.5, 0.5), just_acquired=True)
    x, y = m.map((1.0, 1.0), just_acquired=False)
    assert (x, y) == (1920, 1080)


from handvol.handmouse.pointer import BendTrigger


def test_bend_trigger_engages_below_engage_and_holds_through_hysteresis():
    t = BendTrigger(engage=100, release=130)
    assert t.update(170) is False    # straight
    assert t.update(95) is True      # crosses engage -> bent
    assert t.update(120) is True     # in the hysteresis band -> still bent
    assert t.update(135) is False    # crosses release -> straight again


def test_bend_trigger_no_chatter_in_band():
    t = BendTrigger(engage=100, release=130)
    t.update(170)
    states = [t.update(a) for a in (105, 110, 115, 120, 125)]
    assert states == [False, False, False, False, False]  # never engaged in band


from handvol.handmouse.pointer import HandPointer, PointerAction
from test_handmouse_detect import make_u_hand, LM


def _mapper_stub():
    return AbsoluteMapper(screen_w=1000, screen_h=1000, active=0.65)


def test_process_returns_move_with_no_click_for_plain_u():
    hp = HandPointer(_mapper_stub(), k=1.0)
    hp.acquire()
    action = hp.process(make_u_hand(), t=0.0)
    assert isinstance(action, PointerAction)
    assert action.move is not None
    assert action.left_edge is None
    assert action.right_edge is None
    assert action.scroll == 0


def _hook_index(hand):
    """Mutate a hand so the index finger curls: the tip drops toward the MCP,
    which the monotonic curl metric reads as a clear click."""
    hand[7] = LM(0.45, 0.50)   # index dip curling down
    hand[8] = LM(0.45, 0.54)   # index tip near the MCP
    return hand


def test_process_emits_left_down_then_up_on_index_bend_cycle():
    hp = HandPointer(_mapper_stub(), k=1.0)
    hp.acquire()
    hp.process(make_u_hand(), t=0.0)             # straight baseline
    bent = _hook_index(make_u_hand())
    a_down = hp.process(bent, t=0.033)
    assert a_down.left_edge == "down"
    a_hold = hp.process(bent, t=0.066)
    assert a_hold.left_edge is None               # held, no repeat (drag)
    a_up = hp.process(make_u_hand(), t=0.099)     # straighten
    assert a_up.left_edge == "up"


def test_process_scrolls_and_suppresses_clicks_while_thumb_raised():
    hp = HandPointer(_mapper_stub(), k=1.0, scroll_gain=1000.0)
    hp.acquire()
    ext = make_u_hand()
    ext[4] = LM(0.34, 0.20)                        # thumb raised -> scroll engages
    hp.process(ext, t=0.0)                          # establish scroll anchor
    # Hand drops below the anchor; displacement drives scroll velocity.
    moved = [LM(p.x, p.y + 0.1, p.z) for p in ext]
    action = hp.process(moved, t=0.1)
    assert action.move is None                      # no cursor move while scrolling
    assert action.left_edge is None
    assert action.scroll != 0


def test_release_sends_up_for_held_button():
    hp = HandPointer(_mapper_stub(), k=1.0)
    hp.acquire()
    hp.process(make_u_hand(), t=0.0)
    bent = _hook_index(make_u_hand())
    hp.process(bent, t=0.033)                       # left down (held)
    ups = hp.release()
    assert ("left", "up") in ups


def test_click_pins_cursor_within_deadzone_then_drags_past_it():
    hp = HandPointer(_mapper_stub(), k=1.0)
    hp.acquire()
    hp.process(make_u_hand(), t=0.0)
    free = hp.process(make_u_hand(), t=0.033)        # last free cursor position
    # Click while the hand wobbles slightly (within the deadzone).
    bent = [LM(p.x + 0.01, p.y + 0.01, p.z) for p in _hook_index(make_u_hand())]
    down = hp.process(bent, t=0.066)
    assert down.left_edge == "down"
    assert down.move == free.move                     # pinned, not nudged by the bend
    # Keep holding but move far: over a few frames the smoothed point clears
    # the deadzone and the pin releases into a drag.
    dragged = [LM(p.x, p.y - 0.2, p.z) for p in _hook_index(make_u_hand())]
    a = None
    for i in range(10):
        a = hp.process(dragged, t=0.1 + i * 0.033)
    assert a.left_edge is None                        # still held
    assert a.move != down.move                        # cursor follows the drag


def test_scroll_engage_releases_a_held_button():
    hp = HandPointer(_mapper_stub(), k=1.0)
    hp.acquire()
    hp.process(make_u_hand(), t=0.0)              # straight baseline
    bent = _hook_index(make_u_hand())
    down = hp.process(bent, t=0.033)
    assert down.left_edge == "down"               # left button held
    # Now raise the thumb to start scrolling, hand still U.
    raised = make_u_hand()
    raised[4] = LM(0.34, 0.20)                     # thumb raised
    action = hp.process(raised, t=0.066)
    assert action.left_edge == "up"               # held button released on scroll engage
    assert action.move is None
    # And it is not still considered held.
    assert hp.release() == []
