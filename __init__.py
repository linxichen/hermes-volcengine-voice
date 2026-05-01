"""
Volcengine (Doubao) Voice Plugin for Hermes Agent.

Monkey-patches the TTS dispatch to add 'volcengine' as a provider.
STT integration is TODO (requires WebSocket binary protocol for ASR).

Usage:
  1. Set VOLCENGINE_VOICE_API_KEY in ~/.hermes/.env
  2. Set config.yaml:
       tts.provider: volcengine
       tts.volcengine.speaker: zh_female_conversation  (optional)
  3. Restart Hermes gateway
"""
import logging

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    """Monkey-patch the TTS dispatch to support volcengine provider."""

    # ── Patch TTS ──────────────────────────────────────────────────
    import tools.tts_tool as tts_module

    _original_tts = tts_module.text_to_speech_tool

    def patched_text_to_speech(text: str, output_path=None):
        """Wrapped TTS: if provider is 'volcengine', route to Doubao API."""
        tts_config = tts_module._load_tts_config()
        provider = tts_module._get_provider(tts_config)

        if provider != "volcengine":
            return _original_tts(text, output_path)

        # ── Volcengine path ─────────────────────────────────────
        import datetime
        import json as _json
        import os as _os
        from pathlib import Path as _Path

        from hermes_plugins.volcengine_voice.tts import _volcengine_tts

        if not text or not text.strip():
            return tts_module.tool_error("Text is required", success=False)

        # Truncate long text
        max_len = 5000
        if len(text) > max_len:
            logger.warning("Volcengine TTS: truncating %d chars to %d", len(text), max_len)
            text = text[:max_len]

        # Determine output path
        if output_path:
            file_path = _Path(output_path).expanduser()
        else:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = _Path(tts_module.DEFAULT_OUTPUT_DIR)
            out_dir.mkdir(parents=True, exist_ok=True)
            file_path = out_dir / f"tts_{timestamp}.mp3"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_str = str(file_path)

        try:
            _volcengine_tts(text, file_str, tts_config)
        except Exception as e:
            logger.error("Volcengine TTS failed: %s", e)
            return _json.dumps({
                "success": False,
                "error": f"Volcengine TTS error: {e}",
            }, ensure_ascii=False)

        media_tag = f"MEDIA:{file_str}"
        return _json.dumps({
            "success": True,
            "file_path": file_str,
            "media_tag": media_tag,
            "provider": "volcengine",
        }, ensure_ascii=False)

    # Replace the function reference in the module
    tts_module.text_to_speech_tool = patched_text_to_speech
    logger.info("volcengine-voice: patched text_to_speech_tool ← volcengine provider")

    # ── Patch STT ──────────────────────────────────────────────────
    import tools.transcription_tools as stt_module

    _original_transcribe = stt_module.transcribe_audio

    def patched_transcribe_audio(file_path, model=None):
        """Wrapped STT: if provider is 'volcengine', route to Doubao ASR."""
        stt_config = stt_module._load_stt_config()
        provider = stt_module._get_provider(stt_config)

        if provider != "volcengine":
            return _original_transcribe(file_path, model)

        from hermes_plugins.volcengine_voice.stt import volcengine_transcribe

        logger.info("Volcengine STT: transcribing %s...", file_path)
        return volcengine_transcribe(file_path, stt_config)

    stt_module.transcribe_audio = patched_transcribe_audio
    logger.info("volcengine-voice: patched transcribe_audio ← volcengine provider")
