"""Assert-based tests for public provider registration and routing.

Run directly:  python3 tests/test_providers.py
The plugin is loaded as a package (like Hermes's loader) with a fake PluginContext.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


def _install_abc_stubs():
    """Provide the ABC modules only when Hermes is not importable (plain python3)."""
    try:
        import agent.tts_provider  # noqa: F401
        import agent.transcription_provider  # noqa: F401
        return
    except ImportError:
        pass

    agent_pkg = types.ModuleType("agent")
    agent_pkg.__path__ = []
    sys.modules.setdefault("agent", agent_pkg)

    tts_base = types.ModuleType("agent.tts_provider")

    class TTSProvider:
        pass

    tts_base.TTSProvider = TTSProvider
    sys.modules["agent.tts_provider"] = tts_base

    stt_base = types.ModuleType("agent.transcription_provider")

    class TranscriptionProvider:
        pass

    stt_base.TranscriptionProvider = TranscriptionProvider
    sys.modules["agent.transcription_provider"] = stt_base


_install_abc_stubs()

_MODULE_NAME = "volcengine_voice_under_test"
_SPEC = importlib.util.spec_from_file_location(
    _MODULE_NAME, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
plugin = importlib.util.module_from_spec(_SPEC)
plugin.__path__ = [str(ROOT)]
sys.modules[_MODULE_NAME] = plugin
_SPEC.loader.exec_module(plugin)

provider_mod = sys.modules[f"{_MODULE_NAME}.provider"]


class FakeCtx:
    def __init__(self):
        self.tts_providers = []
        self.stt_providers = []
        self.hooks = []

    def register_tts_provider(self, provider):
        self.tts_providers.append(provider)

    def register_transcription_provider(self, provider):
        self.stt_providers.append(provider)

    def register_hook(self, name, callback):
        self.hooks.append((name, callback))


def test_register_uses_public_provider_apis():
    ctx = FakeCtx()
    plugin.register(ctx)
    assert [p.name for p in ctx.tts_providers] == ["volcengine"]
    assert [p.name for p in ctx.stt_providers] == ["volcengine"]
    assert ctx.hooks == [("pre_llm_call", provider_mod.pre_llm_voice_context)]


def test_register_does_not_rebind_core_or_import_private_tools():
    ctx = FakeCtx()
    plugin.register(ctx)
    assert not hasattr(provider_mod.tts, "text_to_speech_tool")
    assert not hasattr(provider_mod.stt, "transcribe_audio")
    assert not any(name == "tools" or name.startswith("tools.") for name in sys.modules)


def test_hook_follows_active_tts_provider():
    with patch.object(provider_mod.runtime, "load_tts_config", return_value={"provider": "volcengine"}):
        assert provider_mod.pre_llm_voice_context(session_id="s") == {
            "context": provider_mod._VOICE_INSTRUCTION
        }
    with patch.object(provider_mod.runtime, "load_tts_config", return_value={"provider": "edge"}):
        assert provider_mod.pre_llm_voice_context(session_id="s") is None
    with patch.object(provider_mod.runtime, "load_tts_config", side_effect=RuntimeError("bad config")):
        assert provider_mod.pre_llm_voice_context(session_id="s") is None


def test_tts_provider_routes_to_volcengine_with_config_and_voice():
    provider = provider_mod.VolcengineTTSProvider()
    seen = {}

    def fake_tts(text, output_path, tts_config, *, voice=None):
        seen.update(text=text, output_path=output_path, config=tts_config, voice=voice)
        return output_path

    with patch.object(provider_mod.runtime, "load_tts_config", return_value={
        "volcengine": {"speaker": "zh_female_gentle", "sample_rate": 24000},
    }), patch.object(provider_mod.tts, "_volcengine_tts", fake_tts):
        assert provider.synthesize(
            "[开心] 你好", "/tmp/out.mp3", voice="zh_female_sweet",
        ) == "/tmp/out.mp3"

    assert seen["text"] == "[开心] 你好"
    assert seen["voice"] == "zh_female_sweet"
    assert seen["config"]["volcengine"]["speaker"] == "zh_female_gentle"


def test_tts_provider_rejects_empty_text():
    provider = provider_mod.VolcengineTTSProvider()
    try:
        provider.synthesize("   ", "/tmp/out.mp3")
    except ValueError:
        pass
    else:
        raise AssertionError("empty text must raise")


def test_tts_provider_lists_voices_and_setup_schema():
    provider = provider_mod.VolcengineTTSProvider()
    voices = provider.list_voices()
    assert voices and all(entry["id"] in provider_mod.tts.VOICES for entry in voices)
    schema = provider.get_setup_schema()
    assert schema["env_vars"][0]["key"] == "VOLCENGINE_VOICE_API_KEY"


def test_stt_provider_routes_language_and_ignores_prompt():
    provider = provider_mod.VolcengineTranscriptionProvider()
    seen = {}

    def fake_transcribe(file_path, stt_config, *, api_key=None, language=None):
        seen.update(file_path=file_path, stt_config=stt_config, api_key=api_key, language=language)
        return {"success": True, "transcript": "你好", "provider": "volcengine"}

    with patch.object(provider_mod.runtime, "load_stt_config", return_value={
        "volcengine": {"language": "zh-CN"},
    }), patch.object(provider_mod.runtime, "get_secret", return_value="speech-key"), \
            patch.object(provider_mod.stt, "volcengine_transcribe", fake_transcribe):
        result = provider.transcribe(
            "/tmp/audio.wav", language="en-US", prompt="Hermes, Volcengine",
        )

    assert result == {"success": True, "transcript": "你好", "provider": "volcengine"}
    assert seen["api_key"] == "speech-key"
    assert seen["language"] == "en-US"
    assert seen["stt_config"] == {"volcengine": {"language": "zh-CN"}}


def test_stt_provider_never_raises():
    provider = provider_mod.VolcengineTranscriptionProvider()
    with patch.object(provider_mod.runtime, "load_stt_config", return_value={}), \
            patch.object(provider_mod.runtime, "get_secret", return_value="speech-key"), \
            patch.object(provider_mod.stt, "volcengine_transcribe", side_effect=RuntimeError("boom")):
        result = provider.transcribe("/tmp/audio.wav")
    assert result["success"] is False
    assert result["transcript"] == ""
    assert result["provider"] == "volcengine"
    assert "boom" in result["error"]


def test_stt_provider_missing_key_returns_envelope():
    provider = provider_mod.VolcengineTranscriptionProvider()
    with patch.object(provider_mod.runtime, "load_stt_config", return_value={}), \
            patch.object(provider_mod.runtime, "get_secret", return_value=""), \
            patch.object(provider_mod.stt, "volcengine_transcribe", side_effect=AssertionError("must not call")):
        result = provider.transcribe("/tmp/audio.wav")
    assert result["success"] is False
    assert result["transcript"] == ""
    assert "VOLCENGINE_VOICE_API_KEY" in result["error"]


def test_provider_availability_uses_secret_scope():
    tts_provider = provider_mod.VolcengineTTSProvider()
    stt_provider = provider_mod.VolcengineTranscriptionProvider()
    with patch.object(provider_mod.runtime, "get_secret", return_value="key"):
        assert tts_provider.is_available() is True
        assert stt_provider.is_available() is True
    with patch.object(provider_mod.runtime, "get_secret", return_value=""):
        assert tts_provider.is_available() is False
        assert stt_provider.is_available() is False
    with patch.object(provider_mod.runtime, "get_secret", side_effect=RuntimeError("scope")):
        assert tts_provider.is_available() is False
        assert stt_provider.is_available() is False


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
