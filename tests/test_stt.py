"""Assert-based unit tests for STT LLM post-processing and context helpers.

Run directly:  python tests/test_stt.py
Or via pytest: python -m pytest tests/test_stt.py -q
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stt import (
    DEFAULT_LLM_SYSTEM_PROMPT,
    _get_ark_api_key,
    _get_hermes_chat_context,
    _llm_postprocess,
    _strip_hidden,
)


def test_get_ark_api_key_from_config():
    assert _get_ark_api_key({"ark_api_key": "test-key-123"}) == "test-key-123"


def test_get_ark_api_key_from_env(monkeypatch=None):
    orig = os.environ.get("VOLCENGINE_ARK_API_KEY")
    try:
        os.environ["VOLCENGINE_ARK_API_KEY"] = "env-key-456"
        assert _get_ark_api_key({}) == "env-key-456"
    finally:
        if orig is None:
            os.environ.pop("VOLCENGINE_ARK_API_KEY", None)
        else:
            os.environ["VOLCENGINE_ARK_API_KEY"] = orig


def test_default_prompt_integrity():
    assert "数字" in DEFAULT_LLM_SYSTEM_PROMPT
    assert "口吃" in DEFAULT_LLM_SYSTEM_PROMPT or "重复词" in DEFAULT_LLM_SYSTEM_PROMPT
    assert "歧义" in DEFAULT_LLM_SYSTEM_PROMPT


def test_llm_postprocess_empty():
    assert _llm_postprocess("", {}, "fake-key") == ""
    assert _llm_postprocess("   ", {}, "fake-key") == "   "


def test_llm_postprocess_fallback_on_invalid_endpoint():
    # When endpoint is unreachable, it should gracefully fall back to raw transcript
    raw = "今天天气真好"
    cfg = {"ark_endpoint": "http://127.0.0.1:59999/invalid", "llm_timeout": 0.2}
    assert _llm_postprocess(raw, cfg, "fake-key") == raw


def test_chat_context_safely_handles_missing_db():
    # Should return empty string without raising exceptions
    orig = os.environ.get("HERMES_HOME")
    try:
        os.environ["HERMES_HOME"] = "/nonexistent/directory"
        res = _get_hermes_chat_context()
        assert isinstance(res, str)
    finally:
        if orig is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = orig


def _make_db(rows):
    """Create a throwaway state.db with given (session_id, role, content) rows."""
    tmp = tempfile.mkdtemp()
    db = Path(tmp) / "state.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT)")
    conn.executemany("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return tmp


def _with_hermes_home(tmp, fn):
    orig = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = tmp
    try:
        return fn()
    finally:
        if orig is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = orig


def test_strip_hidden_elides_large_code_blocks_only():
    small = "前文 ```x = 1``` 后文"
    assert "x = 1" in _strip_hidden(small)  # short block kept verbatim
    big = "前文 ```" + "a = 1\n" * 60 + "``` 后文TAIL"
    out = _strip_hidden(big)
    assert "omitted" in out and "前文" in out and "后文TAIL" in out
    assert "a = 1" not in out


def test_chat_context_adjacent_round_complete():
    # A name deep inside a long user message must survive (no 120-char truncation),
    # and only the adjacent round is injected — older rounds are not.
    long_q = "开头" + "啊" * 200 + "中间提到杨奕旻这个名字" + "结尾" + "嗯" * 50
    rows = [
        ("s1", "user", "更早一轮的问题"),
        ("s1", "assistant", "更早一轮的回复"),
        ("s1", "user", long_q),
        ("s1", "assistant", "这是紧随其后的完整回复"),
    ]
    out = _with_hermes_home(_make_db(rows), _get_hermes_chat_context)
    assert "杨奕旻" in out
    assert "这是紧随其后的完整回复" in out
    assert "更早一轮" not in out


def test_chat_context_user_alone_pairs_previous_reply():
    rows = [
        ("s1", "user", "上一轮问题"),
        ("s1", "assistant", "上一轮回复"),
        ("s1", "user", "刚说的话还没有回复"),
    ]
    out = _with_hermes_home(_make_db(rows), _get_hermes_chat_context)
    assert "刚说的话还没有回复" in out
    assert "上一轮回复" in out


def test_chat_context_fallback_without_user_rows():
    rows = [("s1", "assistant", "助手消息一"), ("s1", "assistant", "助手消息二")]
    out = _with_hermes_home(_make_db(rows), _get_hermes_chat_context)
    assert "助手消息一" in out and "助手消息二" in out


if __name__ == "__main__":
    tests = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and isinstance(fn, types.FunctionType)
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
        except Exception as exc:
            print(f"  [FAIL] {name}: {exc}")
            failed += 1
    if failed:
        print(f"\n{failed}/{len(tests)} tests failed.")
        sys.exit(1)
    else:
        print(f"\nAll {len(tests)} tests passed.")
