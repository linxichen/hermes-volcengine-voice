"""
Volcengine (Doubao) Text-to-Speech via V3 HTTP Chunked API.

Uses: POST https://openspeech.bytedance.com/api/v3/tts/unidirectional
Auth: X-Api-Key + X-Api-Resource-Id: seed-tts-2.0
"""
import json
import logging
import os
import uuid
from typing import Dict, Any

logger = logging.getLogger(__name__)

# ── Voice presets ──────────────────────────────────────────────────────
# Full list: https://www.volcengine.com/docs/6561/1257544
# All voices use seed-tts-2.0 (Doubao TTS 2.0)
VOICES: Dict[str, str] = {
    "zh_female_conversation": "zh_female_shuangkuaisisi_uranus_bigtts",  # 爽快思思 2.0
    "zh_female_gentle":       "zh_female_vv_uranus_bigtts",              # Vivi 2.0（温柔女声）
    "zh_female_sweet":        "zh_female_tianmeixiaoyuan_uranus_bigtts", # 甜美小源 2.0
    "zh_male_conversation":   "zh_male_M392_conversation_wvae_bigtts",   # 对话男声（保留1.0）
    "zh_male_ruya":           "zh_male_ruyayichen_uranus_bigtts",        # 儒雅逸辰 2.0
}

# Map speakers to their required resource ID
# seed-tts-2.0: 2.0 voices (preferred). seed-tts-1.0: legacy 1.0 voices.
SPEAKER_RESOURCE_MAP: Dict[str, str] = {
    "zh_female_shuangkuaisisi_uranus_bigtts": "seed-tts-2.0",
    "zh_female_vv_uranus_bigtts": "seed-tts-2.0",
    "zh_female_tianmeixiaoyuan_uranus_bigtts": "seed-tts-2.0",
    "zh_male_ruyayichen_uranus_bigtts": "seed-tts-2.0",
    "zh_male_M392_conversation_wvae_bigtts": "seed-tts-1.0",
}

DEFAULT_SPEAKER = VOICES["zh_female_conversation"]
DEFAULT_RESOURCE_ID = "seed-tts-2.0"
API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


def _volcengine_tts(
    text: str,
    output_path: str,
    tts_config: Dict[str, Any] | None = None,
) -> str:
    """Generate speech via Volcengine V3 HTTP Chunked TTS.

    Returns the output_path on success. Raises on failure.
    """
    import requests

    api_key = os.getenv("VOLCENGINE_VOICE_API_KEY", "")
    if not api_key:
        raise ValueError("VOLCENGINE_VOICE_API_KEY not set")

    cfg = tts_config.get("volcengine", {}) if tts_config else {}
    speaker_raw = cfg.get("speaker", DEFAULT_SPEAKER)
    # Resolve short name → voice_type (e.g. zh_female_conversation → zh_female_shuangkuaisisi_uranus_bigtts)
    speaker = VOICES.get(speaker_raw, speaker_raw)
    sample_rate = cfg.get("sample_rate", 24000)
    audio_format = "mp3" if output_path.endswith(".mp3") else "ogg_opus"

    # Resolve resource_id: config override > speaker map > default
    resource_id = cfg.get("resource_id") or SPEAKER_RESOURCE_MAP.get(speaker, DEFAULT_RESOURCE_ID)

    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    payload = {
        "user": {"uid": "hermes-agent"},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": audio_format,
                "sample_rate": sample_rate,
            },
        },
    }

    logger.info(
        "Volcengine TTS: speaker=%s text_len=%d format=%s",
        speaker, len(text), audio_format,
    )

    resp = requests.post(API_URL, json=payload, headers=headers, stream=True, timeout=60)
    resp.raise_for_status()

    # Streamed JSON-line response: each line is a JSON object with base64 data
    audio_chunks: list[bytes] = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Volcengine TTS: unparseable line: %.100s", line)
            continue

        data_b64 = chunk.get("data", "")
        if data_b64:
            import base64
            audio_chunks.append(base64.b64decode(data_b64))

        # Check for error
        code = chunk.get("code", 0)
        if code != 0:
            msg = chunk.get("message", "unknown error")
            raise RuntimeError(f"Volcengine TTS error {code}: {msg}")

    if not audio_chunks:
        raise RuntimeError("Volcengine TTS returned no audio data")

    with open(output_path, "wb") as f:
        for buf in audio_chunks:
            f.write(buf)

    logger.info("Volcengine TTS: saved %d bytes to %s", os.path.getsize(output_path), output_path)
    return output_path
