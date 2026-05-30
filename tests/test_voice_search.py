from handvol.voice_search import SilenceDetector, Phase, resolve_destination


def test_starts_in_waiting_phase():
    d = SilenceDetector()
    assert d.phase is Phase.WAITING_FOR_SPEECH


def test_timeout_when_no_speech():
    d = SilenceDetector(initial_silence_frames=5)
    for _ in range(5):
        d.feed(is_speech=False)
    assert d.phase is Phase.TIMEOUT


def test_enters_speech_after_debounce():
    d = SilenceDetector(speech_start_frames=3)
    d.feed(is_speech=True)
    d.feed(is_speech=True)
    assert d.phase is Phase.WAITING_FOR_SPEECH  # not yet
    d.feed(is_speech=True)
    assert d.phase is Phase.IN_SPEECH


def test_short_burst_does_not_trigger_speech():
    d = SilenceDetector(speech_start_frames=3)
    d.feed(is_speech=True)
    d.feed(is_speech=False)  # gap resets the debounce
    d.feed(is_speech=True)
    d.feed(is_speech=True)
    # only 2 consecutive speech frames so far -> still waiting
    assert d.phase is Phase.WAITING_FOR_SPEECH


def test_done_after_silence_in_speech():
    d = SilenceDetector(speech_start_frames=2, silence_end_frames=4)
    # Enter speech
    d.feed(is_speech=True)
    d.feed(is_speech=True)
    assert d.phase is Phase.IN_SPEECH
    # Brief silence (not enough)
    for _ in range(3):
        d.feed(is_speech=False)
    assert d.phase is Phase.IN_SPEECH
    # Total of 4 consecutive silence frames -> DONE
    d.feed(is_speech=False)
    assert d.phase is Phase.DONE


def test_speech_during_silence_resets_silence_counter():
    d = SilenceDetector(speech_start_frames=1, silence_end_frames=4)
    d.feed(is_speech=True)
    assert d.phase is Phase.IN_SPEECH
    d.feed(is_speech=False)
    d.feed(is_speech=False)
    d.feed(is_speech=True)  # resets
    d.feed(is_speech=False)
    d.feed(is_speech=False)
    d.feed(is_speech=False)
    assert d.phase is Phase.IN_SPEECH  # only 3 silence frames since last speech


def test_feed_after_done_is_noop():
    d = SilenceDetector(speech_start_frames=1, silence_end_frames=1)
    d.feed(is_speech=True)
    d.feed(is_speech=False)
    assert d.phase is Phase.DONE
    d.feed(is_speech=True)
    assert d.phase is Phase.DONE  # terminal


# --- resolve_destination: "go to X" command parsing ------------------------

def test_no_command_prefix_returns_none():
    # Plain search query: caller should paste it verbatim.
    assert resolve_destination("weather in new york") is None


def test_exact_alias_resolves_to_url():
    assert resolve_destination("go to gemini") == "https://gemini.google.com"


def test_synonym_alias_resolves():
    assert resolve_destination("go to insta") == "https://instagram.com"


def test_fuzzy_match_snaps_to_nearest_site():
    # Whisper mishears "gemini" — fuzzy match should still land on it.
    assert resolve_destination("go to gemoney") == "https://gemini.google.com"


def test_dot_com_tail_is_stripped():
    assert resolve_destination("go to youtube dot com") == "https://youtube.com"
    assert resolve_destination("go to youtube.com") == "https://youtube.com"


def test_unknown_site_falls_back_to_bare_target():
    # Option B: known prefix, unknown site -> search just the target word.
    assert resolve_destination("go to spotify") == "spotify"


def test_alternate_prefixes_work():
    assert resolve_destination("open github") == "https://github.com"
    assert resolve_destination("navigate to reddit") == "https://reddit.com"


def test_prefix_match_is_case_insensitive():
    assert resolve_destination("Go To GitHub") == "https://github.com"


def test_prefix_alone_with_no_target_returns_none():
    assert resolve_destination("go to") is None


def test_prefix_must_be_followed_by_space():
    # "gotham" must not trigger the "goto" prefix.
    assert resolve_destination("gotham city") is None
