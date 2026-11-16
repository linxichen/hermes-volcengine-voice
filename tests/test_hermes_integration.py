"""Real-Hermes integration test.

Loads the plugin through Hermes's real plugin loader, then exercises the public
``text_to_speech`` tool path and ``transcribe_audio(file, source="desktop")``.
Volcengine network calls are mocked; the speech and Ark keys are placed only in
an isolated ``$HERMES_HOME/.env``. Skips cleanly when Hermes is not importable.

Run:  ~/.hermes/hermes-agent/venv/bin/python tests/test_hermes_integration.py
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
import types
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERMES_SRC = Path(os.environ.get("HERMES_SRC", Path.home() / ".hermes" / "hermes-agent"))
_ENV_KEYS = (
    "HERMES_HOME",
    "VOLCENGINE_VOICE_API_KEY",
    "VOLCENGINE_ARK_API_KEY",
    "VOLCENGINE_CODING_API_KEY",
    "ARK_API_KEY",
)

_CONFIG = """\
plugins:
  enabled:
    - volcengine-voice
tts:
  provider: volcengine
  volcengine:
    speaker: zh_female_gentle
    sample_rate: 24000
    format: mp3
    speech_rate: 1.0
stt:
  provider: volcengine
  volcengine:
    language: zh-CN
    enable_itn: true
    enable_punc: true
"""


def _save_env() -> dict[str, str | None]:
    return {key: os.environ.get(key) for key in _ENV_KEYS}


def _restore_env(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _prepare_home(home: Path) -> None:
    (home / "plugins").mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(_CONFIG, encoding="utf-8")
    (home / ".env").write_text(
        "VOLCENGINE_VOICE_API_KEY=speech-key-from-dotenv\n"
        "ARK_API_KEY=ark-key-from-dotenv\n",
        encoding="utf-8",
    )
    target = home / "plugins" / "volcengine-voice"
    try:
        os.symlink(ROOT, target, target_is_directory=True)
    except OSError:
        shutil.copytree(
            ROOT, target,
            ignore=shutil.ignore_patterns(".git", ".tmp", "__pycache__", "tests", "docs"),
        )


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def iter_lines(self, decode_unicode: bool = False):
        audio = b"ID3\x04\x00\x00\x00\x00\x00\x00fake-mp3-audio"
        yield json.dumps({"code": 0, "data": base64.b64encode(audio).decode("ascii")})


def main() -> int:
    saved = _save_env()
    for key in _ENV_KEYS:
        os.environ.pop(key, None)

    tmp = tempfile.TemporaryDirectory(prefix="hermes-volcengine-it-")
    home = Path(tmp.name)
    os.environ["HERMES_HOME"] = str(home)
    try:
        _prepare_home(home)

        if HERMES_SRC.is_dir() and str(HERMES_SRC) not in sys.path:
            sys.path.insert(0, str(HERMES_SRC))
        try:
            from hermes_cli.env_loader import load_hermes_dotenv
            from hermes_cli.plugins import get_plugin_manager
        except Exception as exc:
            print(f"SKIP: Hermes is not importable ({exc})")
            return 0

        load_hermes_dotenv(hermes_home=home)
        assert os.environ.get("VOLCENGINE_VOICE_API_KEY") == "speech-key-from-dotenv"
        assert os.environ.get("ARK_API_KEY") == "ark-key-from-dotenv"

        manager = get_plugin_manager()
        manager.discover_and_load()
        loaded = manager._plugins.get("volcengine-voice")
        print("plugin loaded:", bool(loaded), "enabled:", getattr(loaded, "enabled", None),
              "error:", getattr(loaded, "error", None))
        assert loaded is not None and loaded.enabled and not loaded.error, getattr(loaded, "error", None)

        from agent import transcription_registry, tts_registry

        tts_provider = tts_registry.get_provider("volcengine")
        stt_provider = transcription_registry.get_provider("volcengine")
        print("tts provider:", type(tts_provider).__name__ if tts_provider else None,
              "stt provider:", type(stt_provider).__name__ if stt_provider else None)
        assert tts_provider is not None and tts_provider.name == "volcengine"
        assert stt_provider is not None and stt_provider.name == "volcengine"

        try:
            import requests
        except ImportError:
            requests = types.ModuleType("requests")
            sys.modules["requests"] = requests

        captured: dict = {}

        def fake_post(url, json=None, headers=None, **kwargs):
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = json
            return _FakeResponse()

        requests.post = fake_post

        from tools.tts_tool import text_to_speech_tool

        tts_result = json.loads(
            text_to_speech_tool("[开心] 你好", output_path=str(home / "tts-probe.mp3"))
        )
        print("tts result:", json.dumps(tts_result, ensure_ascii=False))
        assert tts_result["success"] is True, tts_result
        assert tts_result["provider"] == "volcengine", tts_result
        assert captured["headers"]["X-Api-Key"] == "speech-key-from-dotenv"
        assert captured["payload"]["req_params"]["text"] == "你好"
        assert json.loads(captured["payload"]["req_params"]["additions"]) == {
            "context_texts": ["用开心的语气说"],
        }

        import hermes_plugins.volcengine_voice.stt as plugin_stt

        seen: dict = {}

        def fake_transcribe(**kwargs):
            seen.update(kwargs)
            return "你好世界 100"

        def _must_not_run(*args, **kwargs):
            raise AssertionError("LLM post-processing must stay off without explicit opt-in")

        plugin_stt._transcribe_volcengine = fake_transcribe
        plugin_stt._llm_postprocess = _must_not_run

        from tools.transcription_tools import transcribe_audio

        wav_path = home / "probe.wav"
        with wave.open(str(wav_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * 1600)

        stt_result = transcribe_audio(str(wav_path), source="desktop")
        print("stt result:", json.dumps(stt_result, ensure_ascii=False))
        assert stt_result["success"] is True, stt_result
        assert stt_result["provider"] == "volcengine", stt_result
        assert stt_result["transcript"] == "你好世界 100", stt_result
        assert seen["api_key"] == "speech-key-from-dotenv"
        assert seen["language"] == "zh-CN"
        assert seen["enable_itn"] is True and seen["enable_punc"] is True

        print("INTEGRATION TEST PASSED")
        return 0
    finally:
        _restore_env(saved)
        tmp.cleanup()


if __name__ == "__main__":
    sys.exit(main())
