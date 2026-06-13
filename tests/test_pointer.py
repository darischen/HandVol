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


def test_absolute_clamps_outside_active_region():
    m = AbsoluteMapper(screen_w=1920, screen_h=1080, active=0.65)
    x, y = m.map((0.0, 0.0), just_acquired=False)
    assert (x, y) == (0, 0)
    x, y = m.map((1.0, 1.0), just_acquired=False)
    assert (x, y) == (1920, 1080)
