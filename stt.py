"""Volcengine STT provider — Doubao (豆包) Bigmodel ASR.

Uses the V3 WebSocket streaming speech recognition API.
Docs: https://www.volcengine.com/docs/6561/1354869

Protocol: binary WebSocket with 4-byte header + 4-byte size + payload.
"""

from __future__ import annotations

import json
import logging
import os
import struct
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

ASR_ENDPOINT = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
RESOURCE_ID = "volc.seedasr.sauc.duration"  # model 2.0, duration billing

# WebSocket binary protocol constants
HEADER_SIZE = 4
SIZE_FIELD_SIZE = 4
PROTOCOL_VERSION = 0b0001
HEADER_SIZE_CODE = 0b0001  # 4 bytes = 1 × 4

# Message types
MSG_FULL_CLIENT_REQUEST = 0b0001
MSG_AUDIO_ONLY = 0b0010
MSG_FULL_SERVER_RESPONSE = 0b1001
MSG_ERROR = 0b1111

# Flags
FLAG_NO_SEQUENCE = 0b0000
FLAG_POSITIVE_SEQUENCE = 0b0001
FLAG_LAST_PACKET = 0b0010
FLAG_LAST_NEGATIVE_SEQUENCE = 0b0011

# Serialization
SERIALIZATION_NONE = 0b0000
SERIALIZATION_JSON = 0b0001

# Compression
COMPRESSION_NONE = 0b0000
COMPRESSION_GZIP = 0b0001


# ── Public API ─────────────────────────────────────────────────────────────


def volcengine_transcribe(
    audio_path: str,
    stt_config: dict[str, Any],
    **kwargs,
) -> dict[str, Any]:
    """Transcribe an audio file via Volcengine ASR.

    Returns a dict matching Hermes STT tool contract:
      {"success": true, "transcript": "...", ...}
    """
    api_key = _get_api_key()
    vc_config = stt_config.get("volcengine", {})

    language = vc_config.get("language", "zh-CN")
    enable_itn = vc_config.get("enable_itn", True)
    enable_punc = vc_config.get("enable_punc", True)

    # Validate audio file
    if not os.path.isfile(audio_path):
        return {"success": False, "error": f"Audio file not found: {audio_path}"}

    file_size = os.path.getsize(audio_path)
    if file_size > 512 * 1024 * 1024:  # 512MB max
        return {"success": False, "error": f"Audio too large: {file_size} bytes (max 512MB)"}

    try:
        transcript = _transcribe_volcengine(
            audio_path=audio_path,
            api_key=api_key,
            language=language,
            enable_itn=enable_itn,
            enable_punc=enable_punc,
        )
    except Exception as exc:
        logger.error("Volcengine ASR failed: %s", exc)
        return {"success": False, "error": f"Volcengine ASR failed: {exc}"}

    if not transcript:
        return {"success": False, "error": "Volcengine ASR returned empty transcript"}

    return {
        "success": True,
        "transcript": transcript,
        "provider": "volcengine",
    }


# ── Internal ───────────────────────────────────────────────────────────────


def _extract_asr_text(result: dict[str, Any]) -> str:
    """Extract transcript text from Volcengine ASR response.

    The current (v3) response structure is:
      {"result": {"text": "transcription here", "utterances": [...]}}

    Also handles older payload_msg format for backwards compatibility.
    The ``result`` field can be a dict with ``text`` key, a string, or a
    list of dicts/strings.
    """
    # 1. Try current v3 format: {"result": {"text": "..."}}
    inner = result.get("result")
    if isinstance(inner, dict):
        text = inner.get("text", "")
        if text:
            return text.strip()
        # Try utterances if no top-level text
        utterances = inner.get("utterances", [])
        if utterances:
            parts = []
            for u in utterances:
                if isinstance(u, dict):
                    t = u.get("text", "")
                    if t:
                        parts.append(t.strip())
            return "".join(parts)
    elif isinstance(inner, list):
        parts = []
        for item in inner:
            if isinstance(item, dict):
                t = item.get("text", "")
            elif isinstance(item, str):
                t = item
            if t:
                parts.append(t.strip())
        return "".join(parts)
    elif isinstance(inner, str) and inner:
        return inner.strip()

    # 2. Fallback: old payload_msg format
    payload_msg = result.get("payload_msg", {})
    inner = payload_msg.get("result", "")
    if isinstance(inner, str):
        return inner.strip()
    if isinstance(inner, list):
        parts = []
        for item in inner:
            if isinstance(item, dict):
                t = item.get("text", "")
            elif isinstance(item, str):
                t = item
            else:
                continue
            if t:
                parts.append(t.strip())
        return "".join(parts)
    return str(inner).strip() if inner else ""


def _get_api_key() -> str:
    key = os.getenv("VOLCENGINE_VOICE_API_KEY", "")
    if not key:
        raise ValueError(
            "VOLCENGINE_VOICE_API_KEY not set. "
            "Add it to ~/.hermes/env.d/volcengine.env or set the environment variable."
        )
    return key


def _transcribe_volcengine(
    audio_path: str,
    api_key: str,
    language: str,
    enable_itn: bool,
    enable_punc: bool,
) -> str:
    """Send audio to Volcengine ASR via WebSocket and return transcript."""
    import asyncio

    # Read audio file
    with open(audio_path, "rb") as f:
        audio_data = f.read()

    # Determine audio format from file extension
    ext = os.path.splitext(audio_path)[1].lower()
    format_map = {
        ".mp3": "mp3",
        ".wav": "wav",
        ".ogg": "ogg",
        ".opus": "ogg",
        ".webm": "ogg",
        ".m4a": "mp4",
        ".aac": "aac",
        ".flac": "flac",
    }
    audio_format = format_map.get(ext, "mp3")

    async def _do_transcribe() -> str:
        import websockets as _ws

        headers = {
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": RESOURCE_ID,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Sequence": "-1",
        }

        async with _ws.connect(
            ASR_ENDPOINT,
            additional_headers=headers,
            max_size=64 * 1024 * 1024,  # 64MB
        ) as ws:
            # 1. Send Full Client Request
            request: dict[str, Any] = {
                "user": {"uid": "hermes-agent"},
                "audio": {
                    "format": audio_format,
                    "rate": 16000,
                },
                "request": {
                    "model_name": "bigmodel",
                    "enable_itn": enable_itn,
                    "enable_punc": enable_punc,
                    "enable_nonstream": True,  # async mode needs this for full-text result
                },
            }
            if language:
                request["audio"]["language"] = language

            payload = json.dumps(request).encode("utf-8")
            import gzip
            payload = gzip.compress(payload)

            header = _build_header(
                msg_type=MSG_FULL_CLIENT_REQUEST,
                flags=FLAG_NO_SEQUENCE,
                serialization=SERIALIZATION_JSON,
                compression=COMPRESSION_GZIP,
            )
            await ws.send(header + struct.pack(">I", len(payload)) + payload)

            # 2. Send Audio Only Request (all audio in one chunk for file mode)
            header = _build_header(
                msg_type=MSG_AUDIO_ONLY,
                flags=FLAG_NO_SEQUENCE,
                serialization=SERIALIZATION_NONE,
                compression=COMPRESSION_NONE,
            )
            await ws.send(header + struct.pack(">I", len(audio_data)) + audio_data)

            # 3. Send last packet (negative sequence = end)
            header = _build_header(
                msg_type=MSG_AUDIO_ONLY,
                flags=FLAG_LAST_PACKET,
                serialization=SERIALIZATION_NONE,
                compression=COMPRESSION_NONE,
            )
            await ws.send(header + struct.pack(">I", 0))

            # 4. Receive results
            transcript_parts: list[str] = []
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    logger.warning("Volcengine ASR: timed out waiting for response")
                    break
                except _ws.exceptions.ConnectionClosedOK as exc:
                    # Server cleanly closed — this is normal completion
                    logger.debug("Volcengine ASR: server closed: %s", exc)
                    break
                except _ws.exceptions.ConnectionClosedError as exc:
                    logger.warning("Volcengine ASR: server closed with error: %s", exc)
                    break

                if isinstance(raw, str):
                    # Text frame — try parsing as JSON response
                    try:
                        result = json.loads(raw)
                        text = _extract_asr_text(result)
                        if text:
                            transcript_parts.append(text)
                    except json.JSONDecodeError:
                        logger.debug("Volcengine ASR: non-JSON text response: %s", raw[:200])
                    continue

                # Parse binary response
                if len(raw) < HEADER_SIZE + SIZE_FIELD_SIZE:
                    logger.debug("Volcengine ASR: short frame (%d bytes), skipping", len(raw))
                    continue

                hdr = raw[:HEADER_SIZE]
                msg_type = (hdr[1] >> 4) & 0x0F
                flags = (hdr[1]) & 0x0F

                # Full Server Response format per Volcengine docs:
                #   Header (4B) | [Sequence (4B, if flags=0b0001 or 0b0011)] | Payload size (4B) | Payload
                # Flags 0b0000/0b0010: no sequence, offset 4 = payload size
                # Flags 0b0001/0b0011: has sequence, offset 4 = sequence, offset 8 = payload size
                has_sequence = (flags == FLAG_POSITIVE_SEQUENCE) or (flags == FLAG_LAST_NEGATIVE_SEQUENCE)
                payload_offset = HEADER_SIZE + (SIZE_FIELD_SIZE if has_sequence else 0)

                if len(raw) < payload_offset + SIZE_FIELD_SIZE:
                    logger.debug("Volcengine ASR: short frame (%d bytes), skipping", len(raw))
                    continue

                size = struct.unpack(">I", raw[payload_offset:payload_offset + SIZE_FIELD_SIZE])[0]
                pl = raw[payload_offset + SIZE_FIELD_SIZE:payload_offset + SIZE_FIELD_SIZE + size]

                if msg_type == MSG_FULL_SERVER_RESPONSE:
                    try:
                        # Decompress if needed
                        compression = hdr[2] & 0x0F
                        if compression == COMPRESSION_GZIP:
                            try:
                                pl = gzip.decompress(pl)
                            except Exception:
                                logger.debug("Volcengine ASR: gzip decompress failed, trying raw")
                                pass

                        if not pl:
                            logger.debug("Volcengine ASR: empty payload in FULL_SERVER_RESPONSE")
                            continue

                        result = json.loads(pl.decode("utf-8"))
                        text = _extract_asr_text(result)
                        if text:
                            transcript_parts.append(text)
                    except json.JSONDecodeError:
                        logger.debug("Volcengine ASR: non-JSON binary payload, len=%d", len(pl))
                    except Exception as exc:
                        logger.warning("Volcengine ASR: parse error: %s", exc)

                elif msg_type == MSG_ERROR:
                    logger.warning("Volcengine ASR: server error in response")

        return "".join(transcript_parts)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Running in async context — create new loop in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _do_transcribe())
                return future.result(timeout=120)
        return asyncio.run(_do_transcribe())
    except RuntimeError:
        return asyncio.run(_do_transcribe())


def _build_header(
    msg_type: int,
    flags: int,
    serialization: int,
    compression: int,
) -> bytes:
    """Build the 4-byte WebSocket binary protocol header."""
    byte0 = (PROTOCOL_VERSION << 4) | HEADER_SIZE_CODE
    byte1 = (msg_type << 4) | flags
    byte2 = (serialization << 4) | compression
    byte3 = 0  # reserved
    return struct.pack("BBBB", byte0, byte1, byte2, byte3)
