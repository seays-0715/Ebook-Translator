from src.translation.tokens import count_tokens, estimate_tokens
from src.utils.power import after_completion_action, SleepPreventer


def test_estimate_and_count():
    assert estimate_tokens("") == 0
    assert count_tokens("") == 0
    n = count_tokens("Hello world. 你好世界。")
    assert n > 0


def test_sleep_preventer_context():
    with SleepPreventer() as p:
        assert p._active
    assert not p._active


def test_after_completion_nothing():
    after_completion_action("nothing")
    after_completion_action("unknown_value")
