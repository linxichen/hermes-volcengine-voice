# Hermes Volcengine Voice Plugin

> 🌋 火山引擎豆包语音合成 & 识别插件 for [Hermes Agent](https://github.com/NousResearch/hermes-agent)

Adds **Volcengine (火山引擎) Doubao (豆包)** TTS and STT as voice providers to Hermes Agent via monkey-patch plugin.

## ✨ Features

- **TTS** — HTTP Chunked streaming via V3 API (`/api/v3/tts/unidirectional`)
- **STT** — WebSocket streaming ASR via V3 API (`/api/v3/sauc/bigmodel`)
- **2.0 voices** — Uses Doubao TTS 2.0 model with 5+ Chinese voice presets
- **Short-name aliases** — Config uses friendly names like `zh_female_conversation`, auto-resolved to voice types
- **Seamless integration** — Set `tts.provider: volcengine` and it just works

## 📦 Installation

```bash
# Clone into Hermes plugins directory
git clone https://github.com/linxichen/hermes-volcengine-voice.git ~/.hermes/plugins/volcengine-voice

# Enable in config.yaml
hermes config set plugins.enabled --append volcengine-voice
```

## 🔑 Setup

### 1. Get API Key

Go to [火山引擎语音控制台](https://console.volcengine.com/speech) → API Key 管理 → create a key.

⚠️ **Important:** You need a **Speech** API key, NOT an Ark (LLM) key. Ark keys (prefix `ark-`) will return `45000010: "Invalid X-Api-Key"`.

### 2. Configure

```bash
# Add to ~/.hermes/.env
echo 'VOLCENGINE_VOICE_API_KEY=your-api-key-here' >> ~/.hermes/.env

# Set provider
hermes config set tts.provider volcengine
hermes config set stt.provider volcengine
```

### 3. Choose a voice (optional)

```bash
# Available presets:
#   zh_female_conversation  — 爽快思思 2.0 (default)
#   zh_female_gentle        — Vivi 2.0 温柔女声
#   zh_female_sweet         — 甜美小源 2.0
#   zh_male_ruya            — 儒雅逸辰 2.0
#   zh_male_conversation    — 对话男声

hermes config set tts.volcengine.speaker zh_female_gentle
```

### 4. Restart

```bash
hermes gateway restart
```

## 🎤 Usage

Once configured, Hermes uses Volcengine for all TTS and STT automatically:

- **Discord voice messages** — auto-transcribed via Volcengine STT
- **Voice responses** — spoken via Volcengine TTS when `/voice tts` is enabled
- **Discord voice channels** — join with `/voice channel`, bot speaks through VC

## 🎵 Voice List

| Short Name | Voice Type | Description |
|-----------|-----------|-------------|
| `zh_female_conversation` | `zh_female_shuangkuaisisi_uranus_bigtts` | 爽快思思 2.0 |
| `zh_female_gentle` | `zh_female_vv_uranus_bigtts` | Vivi 2.0 温柔女声 |
| `zh_female_sweet` | `zh_female_tianmeixiaoyuan_uranus_bigtts` | 甜美小源 2.0 |
| `zh_male_ruya` | `zh_male_ruyayichen_uranus_bigtts` | 儒雅逸辰 2.0 |
| `zh_male_conversation` | `zh_male_M392_conversation_wvae_bigtts` | 对话男声 (1.0) |

Full list: [火山引擎音色列表](https://www.volcengine.com/docs/6561/1257544)

## 🏗️ Architecture

```
volcengine-voice/
├── plugin.yaml          # Plugin metadata
├── __init__.py          # Monkey-patch dispatch for TTS + STT
├── tts.py               # HTTP Chunked TTS (V3 API)
└── stt.py               # WebSocket binary STT (V3 API)
```

The plugin intercepts Hermes' TTS/STT dispatch and routes `provider: volcengine` calls to the Doubao API:

```python
# From __init__.py — register()
import tools.tts_tool as tts_module
original_tts = tts_module.text_to_speech_tool

def patched_tts(text, output_path=None):
    config = tts_module._load_tts_config()
    if tts_module._get_provider(config) == "volcengine":
        from hermes_plugins.volcengine_voice.tts import _volcengine_tts
        return _volcengine_tts(text, output_path, config)
    return original_tts(text, output_path)

tts_module.text_to_speech_tool = patched_tts
```

## 📄 License

MIT — feel free to use, modify, and share.

## 🔗 Links

- [Hermes Agent](https://github.com/NousResearch/hermes-agent)
- [火山引擎语音文档](https://www.volcengine.com/docs/6561)
- [Blog: How to Set Up](https://linxic.com/tutorial/hermes-volcengine-voice/)
