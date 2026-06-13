from handvol.handmouse.mouse import Monitor, VirtualScreen, to_absolute, Mouse


def test_to_absolute_maps_monitor_corner_to_zero():
    mon = Monitor(left=0, top=0, width=1920, height=1080)
    virt = VirtualScreen(left=0, top=0, width=1920, height=1080)
    ax, ay = to_absolute(0, 0, mon, virt)
    assert (ax, ay) == (0, 0)


def test_to_absolute_maps_monitor_far_corner_to_65535():
    mon = Monitor(left=0, top=0, width=1920, height=1080)
    virt = VirtualScreen(left=0, top=0, width=1920, height=1080)
    ax, ay = to_absolute(1920, 1080, mon, virt)
    assert ax == 65535
    assert ay == 65535


def test_to_absolute_accounts_for_secondary_monitor_offset():
    # Primary on the right of a second monitor: virtual origin is negative.
    mon = Monitor(left=0, top=0, width=1920, height=1080)
    virt = VirtualScreen(left=-1920, top=0, width=3840, height=1080)
    ax, _ = to_absolute(0, 0, mon, virt)
    # Local (0,0) is at virtual x=0, which is halfway across a 3840 desktop.
    assert ax == round(1920 * 65535 / 3839)


def test_mouse_sink_records_move_and_click_sequence():
    mon = Monitor(left=0, top=0, width=1920, height=1080)
    virt = VirtualScreen(left=0, top=0, width=1920, height=1080)
    sink = []
    m = Mouse(mon, virt, sink=sink)
    m.move_to(960, 540)
    m.left_down()
    m.left_up()
    m.scroll(3)
    assert sink[0][0] == "move"
    assert sink[1] == ("left_down",)
    assert sink[2] == ("left_up",)
    assert sink[3] == ("scroll", 3)
