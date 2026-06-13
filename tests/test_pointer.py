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
