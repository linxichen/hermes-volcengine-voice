# Changelog

## [v0.1.0] - 2026-08-13

Initial release of the Volcengine Doubao voice plugin for Hermes Agent.

### Added

- **TTS** — Doubao TTS 2.0 (seed-tts-2.0) via HTTP chunked streaming API, with 5 built-in Chinese voice presets (爽快思思 / Vivi / 甜美小源 / 儒雅逸辰 / 对话男声)
- **STT** — WebSocket streaming ASR with dialect support and speaker diarization
- **🎭 Emotion control** — `[情绪] 文本` prefix syntax (`[开心]`, `[伤心]`, `[生气]`, `[严肃]`, `[温柔]`, `[快速]`…), markers sent via non-billed `context_texts` field
  - *Feature contributed by [@BartmossW](https://github.com/BartmossW) in [PR #1](https://github.com/linxichen/hermes-volcengine-voice/pull/1)*
- **pre_llm_call hook** — injects voice-mode context (incl. emotion syntax) when volcengine is the active provider
- **Short-name aliases** — friendly config names resolved to full voice types
- **Demo audio clips** — `docs/demo/` with 10 emotion × voice samples + regeneration script
