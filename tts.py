"""
Volcengine (Doubao) Text-to-Speech via V3 HTTP Chunked API.

Uses: POST https://openspeech.bytedance.com/api/v3/tts/unidirectional
Auth: X-Api-Key + X-Api-Resource-Id: seed-tts-2.0
"""
import json
import logging
import os
import re
import uuid
from typing import Dict, Any, List, Optional

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


def extract_emotion_and_clean_text(raw_text: str) -> tuple[str, Optional[List[str]]]:
    """
    从 raw_text 中提取方括号内的情绪指令，返回 (clean_text, context_texts)
    例如: "[开心的语气] 今天天气真好" -> ("今天天气真好", ["用开心的语气说"])
    支持多个指令: "[开心][快速] 你好" -> ("你好", ["用开心的语气说", "用快速的语气说"])
    只支持2.0!!!
    """
    pattern = r'\[([^\]]+)\]'
    matches = re.findall(pattern, raw_text)
    if not matches:
        return raw_text, None

    instructions = []
    for m in matches:
        m = m.strip()
        if not m.startswith("用"):
            m = f"用{m}的语气说"
        instructions.append(m)

    # 移除所有方括号及其内容
    clean_text = re.sub(pattern, '', raw_text).strip()
    # 如果去除后为空，保留原文本（防止全标记情况）
    if not clean_text:
        clean_text = raw_text

    return clean_text, instructions


def _volcengine_tts(
    text: str,
    output_path: str,
    tts_config: Dict[str, Any] | None = None,
) -> str:
    """Generate speech via Volcengine V3 HTTP Chunked TTS.

    Returns the output_path on success. Raises on failure.
    """
    import requests
    import base64

    api_key = os.getenv("VOLCENGINE_VOICE_API_KEY", "")
    if not api_key:
        raise ValueError("VOLCENGINE_VOICE_API_KEY not set")

    cfg = tts_config.get("volcengine", {}) if tts_config else {}
    speaker_raw = cfg.get("speaker", DEFAULT_SPEAKER)
    speaker = VOICES.get(speaker_raw, speaker_raw)
    sample_rate = cfg.get("sample_rate", 24000)
    audio_format = "mp3" if output_path.endswith(".mp3") else "ogg_opus"

    resource_id = cfg.get("resource_id") or SPEAKER_RESOURCE_MAP.get(speaker, DEFAULT_RESOURCE_ID)

    # ---------- 新增：提取情绪指令并清理文本 ----------
    clean_text, context_texts = extract_emotion_and_clean_text(text)

    # 构建 additions 字典
    additions = {
        "disable_markdown_filter": False,
        "disable_emoji_filter": False,
        "enable_latex_tn": True,
    }
    if context_texts:
        additions["context_texts"] = context_texts

    additions_json = json.dumps(additions)

    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
        "Connection": "keep-alive",
        "X-Control-Require-Usage-Tokens-Return": "*",  # 可选，但官方示例推荐
    }

    payload = {
        "user": {"uid": "hermes-agent"},
        "req_params": {
            "text": clean_text,          # 使用纯净文本（情绪标记已剥离）
            "speaker": speaker,
            "audio_params": {
                "format": audio_format,
                "sample_rate": sample_rate,
            },
            "additions": additions_json,
        },
    }

    logger.info(
        "Volcengine TTS: speaker=%s clean_text_len=%d format=%s context=%s",
        speaker, len(clean_text), audio_format, context_texts,
    )

    resp = requests.post(API_URL, json=payload, headers=headers, stream=True, timeout=60)
    resp.raise_for_status()

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
            audio_chunks.append(base64.b64decode(data_b64))

        code = chunk.get("code", 0)
        if code != 0 and code != 20000000:
            msg = chunk.get("message", "unknown error")
            raise RuntimeError(f"Volcengine TTS error {code}: {msg}")

    if not audio_chunks:
        raise RuntimeError("Volcengine TTS returned no audio data")

    with open(output_path, "wb") as f:
        for buf in audio_chunks:
            f.write(buf)

    logger.info("Volcengine TTS: saved %d bytes to %s", os.path.getsize(output_path), output_path)
    return output_path