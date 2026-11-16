"""Volcengine (Doubao) providers registered on Hermes's public plugin surfaces.

TTS is a :class:`agent.tts_provider.TTSProvider` named ``volcengine``; STT is a
:class:`agent.transcription_provider.TranscriptionProvider` with the same name.
Hermes's dispatchers own the tool envelopes and error handling, so the classes
here only implement the backends. ``pre_llm_call`` stays a normal plugin hook.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from agent.transcription_provider import TranscriptionProvider
from agent.tts_provider import TTSProvider

from . import runtime, stt, tts

logger = logging.getLogger(__name__)

_VOICE_INSTRUCTION = (
    "You are responding via voice. Keep replies concise (2-4 sentences), "
    "use natural conversational tone, avoid markdown formatting that doesn't "
    "read well aloud (no tables, no code blocks unless asked), and speak "
    "directly to the user without meta-commentary. "
    "When you want to control the speaking style, prefix your TTS text with "
    "one or more [emotion] markers, e.g. '[开心] 今天天气真好' or "
    "'[开心][快速] 你好'; the bracketed part is a non-billed style "
    "instruction and is stripped from the spoken text."
)


def pre_llm_voice_context(
    session_id: Optional[str] = None,
    user_message: Any = None,
    conversation_history: Any = None,
    is_first_turn: Optional[bool] = None,
    model: Optional[str] = None,
    platform: Optional[str] = None,
    **kwargs: Any,
):
    """Inject voice-friendly instructions when ``tts.provider`` is volcengine."""
    try:
        if runtime.active_tts_provider() == "volcengine":
            return {"context": _VOICE_INSTRUCTION}
    except Exception:
        logger.debug("volcengine-voice: voice context hook failed", exc_info=True)
    return None


class VolcengineTTSProvider(TTSProvider):
    """Doubao TTS via the V3 HTTP chunked API."""

    @property
    def name(self) -> str:
        return "volcengine"

    @property
    def display_name(self) -> str:
        return "Volcengine Doubao"

    def is_available(self) -> bool:
        try:
            return bool(runtime.get_secret("VOLCENGINE_VOICE_API_KEY"))
        except Exception:
            return False

    def list_voices(self) -> list[dict[str, Any]]:
        return [
            {
                "id": short_name,
                "display": tts.VOICE_DISPLAY.get(short_name, short_name),
                "language": "zh-CN",
            }
            for short_name in tts.VOICES
        ]

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": self.display_name,
            "badge": "火山引擎",
            "tag": "TTS",
            "env_vars": [
                {
                    "key": "VOLCENGINE_VOICE_API_KEY",
                    "prompt": "Volcengine Speech API Key (not an Ark LLM key)",
                    "url": "https://console.volcengine.com/speech",
                }
            ],
        }

    def synthesize(
        self,
        text: str,
        output_path: str,
        *,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        format: str = "mp3",
        **extra: Any,
    ) -> str:
        if not text or not text.strip():
            raise ValueError("Text is required")

        # The dispatcher already chunks to the provider's text cap; keep the old
        # plugin's direct-call guard for callers that bypass it.
        if len(text) > tts.MAX_TEXT_LENGTH:
            logger.warning(
                "Volcengine TTS: truncating %d chars to %d",
                len(text), tts.MAX_TEXT_LENGTH,
            )
            text = text[: tts.MAX_TEXT_LENGTH]

        tts_config = runtime.load_tts_config()
        tts._volcengine_tts(text, output_path, tts_config, voice=voice)
        return output_path


class VolcengineTranscriptionProvider(TranscriptionProvider):
    """Doubao Bigmodel ASR over the V3 WebSocket protocol."""

    @property
    def name(self) -> str:
        return "volcengine"

    @property
    def display_name(self) -> str:
        return "Volcengine Doubao"

    def is_available(self) -> bool:
        try:
            return bool(runtime.get_secret("VOLCENGINE_VOICE_API_KEY"))
        except Exception:
            return False

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": self.display_name,
            "badge": "火山引擎",
            "tag": "STT",
            "env_vars": [
                {
                    "key": "VOLCENGINE_VOICE_API_KEY",
                    "prompt": "Volcengine Speech API Key (not an Ark LLM key)",
                    "url": "https://console.volcengine.com/speech",
                }
            ],
        }

    def transcribe(
        self,
        file_path: str,
        *,
        model: Optional[str] = None,
        language: Optional[str] = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Return the documented envelope; never raise."""
        try:
            stt_config = runtime.load_stt_config()
            api_key = runtime.get_secret("VOLCENGINE_VOICE_API_KEY")
            if not api_key:
                return _stt_error(
                    "VOLCENGINE_VOICE_API_KEY not set. Add it to the active "
                    "profile's Hermes home .env (default ~/.hermes/.env) or set "
                    "the environment variable."
                )
            if extra.get("prompt"):
                # The Volcengine ASR request has no documented prompt/vocabulary
                # field; keep the text untouched rather than sending it somewhere
                # the API does not support.
                logger.debug("Volcengine STT: ignoring prompt hint (%d chars)", len(str(extra["prompt"])))
            if model:
                logger.debug("Volcengine STT: ignoring model override %r", model)
            return stt.volcengine_transcribe(
                file_path,
                stt_config,
                api_key=api_key,
                language=language,
            )
        except Exception as exc:
            logger.error("Volcengine STT provider failed: %s", exc, exc_info=True)
            return _stt_error(f"Volcengine STT failed: {exc}")


def _stt_error(message: str) -> dict[str, Any]:
    return {
        "success": False,
        "transcript": "",
        "provider": "volcengine",
        "error": message,
    }
