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


_EMOTION_PREFIX = re.compile(r'^(?:\s*\[([^\[\]]+)\])+\s*')
_TAG = re.compile(r'\[([^\[\]]+)\]')


def _as_instruction(tag: str) -> str:
    """把裸的情绪标记包装成自然语言指令。"""
    if tag.startswith("用") or tag.endswith("说"):
        return tag
    if tag.endswith("语气") or tag.endswith("情绪"):
        return f"用{tag}说"
    return f"用{tag}的语气说"


def extract_emotion_and_clean_text(raw_text: str) -> tuple[str, list[str] | None]:
    """从 raw_text 开头提取方括号情绪指令，返回 (clean_text, context_texts)。

    只识别开头的标记，正文中的方括号（引用编号、markdown 链接、list[str] 等）
    保持原样。没有标记时原样返回。

    "[开心] 今天天气真好"  -> ("今天天气真好", ["用开心的语气说"])
    "[开心][快速] 你好"    -> ("你好", ["用开心的语气说", "用快速的语气说"])
    "参考 [1] 和 [2]"      -> ("参考 [1] 和 [2]", None)

    注意：context_texts 仅 2.0 音色（seed-tts-2.0）支持。
    """
    m = _EMOTION_PREFIX.match(raw_text)
    if not m:
        return raw_text, None

    instructions = [_as_instruction(t.strip()) for t in _TAG.findall(m.group(0)) if t.strip()]
    clean_text = raw_text[m.end():].strip()
    # 全是标记、或标记为空 → 当作普通文本，不做处理
    if not clean_text or not instructions:
        return raw_text, None

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

    # 提取开头的 [情绪] 标记并剥离正文
    clean_text, context_texts = extract_emotion_and_clean_text(text)

    # context_texts 不计费，但仅 2.0 音色（seed-tts-2.0）支持；无标记时不带 additions
    additions: Dict[str, Any] = {}
    if context_texts and resource_id == "seed-tts-2.0":
        additions["context_texts"] = context_texts

    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    payload = {
        "user": {"uid": "hermes-agent"},
        "req_params": {
            "text": clean_text,  # 情绪标记已剥离
            "speaker": speaker,
            "audio_params": {
                "format": audio_format,
                "sample_rate": sample_rate,
            },
        },
    }
    if additions:
        # req_params.additions 要求 JSON 序列化后的字符串，而不是对象
        payload["req_params"]["additions"] = json.dumps(additions)

    logger.info(
        "Volcengine TTS: speaker=%s clean_text_len=%d format=%s context=%s",
        speaker, len(clean_text), audio_format, context_texts,
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

        # Check for error (20000000 = end-of-stream OK marker, not an error)
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
