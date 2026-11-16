"""
Volcengine (Doubao) Voice Plugin for Hermes Agent.

Registers ``volcengine`` on Hermes's public provider surfaces:

* ``ctx.register_tts_provider(...)`` — Doubao TTS 2.0
* ``ctx.register_transcription_provider(...)`` — Doubao Bigmodel ASR
* ``ctx.register_hook("pre_llm_call", ...)`` — voice-friendly reply guidance

Usage:
  1. Set VOLCENGINE_VOICE_API_KEY in the active profile's Hermes home .env
     (default ~/.hermes/.env)
  2. Set config.yaml:
       tts.provider: volcengine
       stt.provider: volcengine
  3. Enable: hermes plugins enable volcengine-voice
  4. Restart Hermes gateway

No Hermes core function, method, module attribute or private table is rebound;
the tool dispatch stays owned by Hermes.
"""

import logging

from .provider import (
    VolcengineTranscriptionProvider,
    VolcengineTTSProvider,
    pre_llm_voice_context,
)

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    """Register both providers and the voice-context hook."""
    ctx.register_tts_provider(VolcengineTTSProvider())
    ctx.register_transcription_provider(VolcengineTranscriptionProvider())
    ctx.register_hook("pre_llm_call", pre_llm_voice_context)
    logger.info("volcengine-voice: registered TTS/STT providers and pre_llm_call hook")
