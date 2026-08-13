"""Assert-based tests for extract_emotion_and_clean_text.

Run directly:  python tests/test_tts.py
Or via pytest: python -m pytest tests/test_tts.py -q
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tts import extract_emotion_and_clean_text


def test_no_emotion_returns_unchanged():
    assert extract_emotion_and_clean_text("今天天气真好") == ("今天天气真好", None)


def test_leading_emotion():
    assert extract_emotion_and_clean_text("[开心] 今天天气真好") == ("今天天气真好", ["用开心的语气说"])


def test_multiple_leading_emotions():
    assert extract_emotion_and_clean_text("[开心][快速] 你好") == ("你好", ["用开心的语气说", "用快速的语气说"])


def test_brackets_in_body_untouched():
    assert extract_emotion_and_clean_text("参考 [1] 和 [2]") == ("参考 [1] 和 [2]", None)
    assert extract_emotion_and_clean_text("详见 [Hermes Agent](https://example.com)") == (
        "详见 [Hermes Agent](https://example.com)", None,
    )
    assert extract_emotion_and_clean_text("配置项是 list[str]，注意类型") == ("配置项是 list[str]，注意类型", None)
    assert extract_emotion_and_clean_text("他说：“[笑]”，然后走了") == ("他说：“[笑]”，然后走了", None)


def test_emotion_then_body_brackets():
    assert extract_emotion_and_clean_text("[开心] 参考 [1] 和 [2]") == ("参考 [1] 和 [2]", ["用开心的语气说"])


def test_explicit_instruction_not_doubled():
    assert extract_emotion_and_clean_text("[开心的语气] 你好") == ("你好", ["用开心的语气说"])
    assert extract_emotion_and_clean_text("[用开心的语气说] 你好") == ("你好", ["用开心的语气说"])


def test_only_tags_or_blank_tag_unchanged():
    assert extract_emotion_and_clean_text("[开心]") == ("[开心]", None)
    assert extract_emotion_and_clean_text("[ ] 你好") == ("[ ] 你好", None)


def test_leading_whitespace_allowed():
    assert extract_emotion_and_clean_text("  [开心] 你好") == ("你好", ["用开心的语气说"])


if __name__ == "__main__":
    tests = [
        (name, fn) for name, fn in sorted(globals().items())
        if name.startswith("test_") and isinstance(fn, types.FunctionType)
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {name}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
