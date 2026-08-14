#!/usr/bin/env python3
"""Regenerate the demo clips in this folder.

Usage: VOLCENGINE_VOICE_API_KEY=xxx python3 generate_demo.py
(You need a Volcengine Speech API key — see repo README.)

Each clip speaks the same neutral sentence with a different [emotion]
marker + voice, so you can hear what the emotion feature does.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tts import _volcengine_tts  # noqa: E402

SENTENCE = "今天天气真不错，我们一起去公园走走吧。"

GRID = [
    # (output_file, voice_key, emotion_marker)
    ("sisi-happy.mp3",    "zh_female_conversation", "开心"),
    ("sisi-sad.mp3",      "zh_female_conversation", "伤心"),
    ("sisi-angry.mp3",    "zh_female_conversation", "生气"),
    ("sisi-fast.mp3",     "zh_female_conversation", "快速"),
    ("vivi-happy.mp3",    "zh_female_gentle",       "开心"),
    ("vivi-gentle.mp3",   "zh_female_gentle",       "温柔"),
    ("xiaoyuan-happy.mp3","zh_female_sweet",        "开心"),
    ("xiaoyuan-angry.mp3","zh_female_sweet",        "生气"),
    ("yichen-serious.mp3","zh_male_ruya",           "严肃"),
    ("yichen-happy.mp3",  "zh_male_ruya",           "开心"),
]

HERE = os.path.dirname(os.path.abspath(__file__))

for fname, voice, emotion in GRID:
    out = os.path.join(HERE, fname)
    _volcengine_tts(f"[{emotion}] {SENTENCE}", out, {"volcengine": {"speaker": voice}})
    print("OK", fname)
print("All clips regenerated.")
