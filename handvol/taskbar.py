"""Trigger the Windows taskbar shortcut ``Win+<slot>``.

A single tap of ``<slot>`` while Win is held focuses (or launches) the pinned
app. Two taps while Win is still held cycles to the next window of that app.
Releasing Win commits the selection — without that release, Windows leaves
the window-preview overlay up.

We use pyautogui directly (not the ``keyboard`` library) because pyautogui
sends raw OS-level key events without any internal modifier-state tracking,
so explicit ``keyDown('winleft')`` / ``keyUp('winleft')`` maps 1:1 to what
Windows actually sees. The ``keyboard`` library was leaving Win stuck because
its ``send(digit, ...)`` calls toggled the modifier internally between taps.
"""
import time

import pyautogui

# pyautogui's default 0.1s PAUSE between calls makes the Win-held cycle
# overlay flicker; we want the taps to feel like a fast double-press.
pyautogui.PAUSE = 0

MODIFIER_WARMUP = 0.05  # let Windows register Win-held before the first tap;
                        # without this, the first digit fires as a plain key
                        # because the keyDown event hasn't reached the OS yet
INTER_TAP_DELAY = 0.05  # short gap so Windows registers two discrete taps


def focus_slot(slot, presses=1):
    """Hold Win, tap ``<slot>`` ``presses`` times, release Win.

    ``presses=1`` → focus/launch the pinned app.
    ``presses=2`` → cycle to the second window of the pinned app.

    Returns 'ok' or 'failed' for logging.
    """
    digit = str(slot)
    try:
        pyautogui.keyDown("winleft")
        try:
            time.sleep(MODIFIER_WARMUP)
            for i in range(presses):
                if i > 0:
                    time.sleep(INTER_TAP_DELAY)
                pyautogui.press(digit)
        finally:
            time.sleep(INTER_TAP_DELAY)  # ensure the last tap registers before releasing Win
            pyautogui.keyUp("winleft")
        return "ok"
    except Exception:
        return "failed"
