from handvol.state import (
    GestureStateMachine, State, Event,
    U_SIGN, POINTER_ENTER_FRAMES, POINTER_EXIT_FRAMES,
)
from handvol.state import POINTING_UP, MIDDLE_FINGER


def test_enters_pointer_after_enter_frames_of_u_sign():
    sm = GestureStateMachine()
    events = [sm.step(U_SIGN) for _ in range(POINTER_ENTER_FRAMES)]
    assert sm.state is State.POINTER
    assert events[-1] is Event.ENTER_POINTER
    assert all(e is Event.NONE for e in events[:-1])


def test_pointer_update_each_frame_while_held():
    sm = GestureStateMachine()
    for _ in range(POINTER_ENTER_FRAMES):
        sm.step(U_SIGN)
    assert sm.step(U_SIGN) is Event.POINTER_UPDATE


def test_click_poses_keep_pointer_alive():
    sm = GestureStateMachine()
    for _ in range(POINTER_ENTER_FRAMES):
        sm.step(U_SIGN)
    # Bending a finger to click looks like Pointing_Up or middle_finger.
    assert sm.step(POINTING_UP) is Event.POINTER_UPDATE
    assert sm.step(MIDDLE_FINGER) is Event.POINTER_UPDATE
    assert sm.state is State.POINTER


def test_exits_pointer_after_exit_frames_of_non_pose():
    sm = GestureStateMachine()
    for _ in range(POINTER_ENTER_FRAMES):
        sm.step(U_SIGN)
    events = [sm.step("None") for _ in range(POINTER_EXIT_FRAMES)]
    assert events[-1] is Event.EXIT_POINTER
    assert sm.state is State.IDLE


def test_ambiguous_pose_keeps_pointer_alive():
    # A half-bend click frame often reads as Victory; it must not drop POINTER.
    from handvol.state import VICTORY
    sm = GestureStateMachine()
    for _ in range(POINTER_ENTER_FRAMES):
        sm.step(U_SIGN)
    for _ in range(POINTER_EXIT_FRAMES + 2):
        assert sm.step(VICTORY) is Event.POINTER_UPDATE
    assert sm.state is State.POINTER


def test_open_palm_exits_pointer():
    from handvol.state import PALM
    sm = GestureStateMachine()
    for _ in range(POINTER_ENTER_FRAMES):
        sm.step(U_SIGN)
    events = [sm.step(PALM) for _ in range(POINTER_EXIT_FRAMES)]
    assert events[-1] is Event.EXIT_POINTER
    assert sm.state is State.IDLE


def test_pointing_up_in_idle_still_toggles_preview_not_pointer():
    sm = GestureStateMachine()
    from handvol.state import TOGGLE_FRAMES
    events = [sm.step(POINTING_UP) for _ in range(TOGGLE_FRAMES)]
    assert events[-1] is Event.TOGGLE_PREVIEW


def test_pointer_enabled_suppresses_pointing_up_and_middle_finger():
    from handvol.state import TOGGLE_FRAMES, HOLD_SECONDS
    import time as _time
    sm = GestureStateMachine(pointer_enabled=True)
    # Pointing_Up no longer toggles preview.
    events = [sm.step(POINTING_UP) for _ in range(TOGGLE_FRAMES + 2)]
    assert Event.TOGGLE_PREVIEW not in events
    # A held middle finger no longer fires restart, even past the hold time.
    sm2 = GestureStateMachine(pointer_enabled=True)
    sm2.step(MIDDLE_FINGER)
    sm2._middle_start_t -= HOLD_SECONDS + 1  # simulate a long hold
    assert sm2.step(MIDDLE_FINGER) is not Event.RESTART_PC
    assert sm2.get_hold_progress() is None
