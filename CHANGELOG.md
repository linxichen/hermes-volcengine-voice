# Changelog

## [v2.0.0] - 2026-11-16

Migrated the plugin to Hermes's public provider APIs and hardened the optional
LLM transcript cleanup.

### Upgrade note

v1.2.0 enabled LLM cleanup automatically whenever an Ark key was present. v2.0.0
requires `stt.volcengine.enable_llm_postprocess: true`; an existing install with
an Ark key but no explicit flag stops cleaning until it opts in.

### Changed

- **Public provider registration** — `tts.provider: volcengine` now resolves
  through `ctx.register_tts_provider()` (`TTSProvider`), and
  `stt.provider: volcengine` through `ctx.register_transcription_provider()`
  (`TranscriptionProvider`). The plugin no longer monkey-patches
  `tools.tts_tool.text_to_speech_tool` or
  `tools.transcription_tools.transcribe_audio`, and no longer imports private
  `tools.*` modules.
- **`pre_llm_call` stays public** — the hook now reads `tts.provider` through
  `hermes_cli.config.load_config_readonly()` instead of `tools.tts_tool`
  internals.
- **Config keys unchanged** — `tts.provider: volcengine`,
  `stt.provider: volcengine`, `tts.volcengine.*` and `stt.volcengine.*` keep
  working.
- **Chat-context feature removed** — no `state.db` read, no `enable_context`
  setting, no cross-session history injection.
- Requires Hermes >= 0.21.6 (minimum tested on 0.22.2 / `6e9b3e3b88` and
  `1c0cd66`; the provider APIs actually date from `v2026.5.28` / 0.15.0).

### Added

- **Opt-in LLM post-processing** — off by default; runs only when
  `stt.volcengine.enable_llm_postprocess` is explicitly `true`. A present Ark
  key alone never enables it. The transcript is sent to Volcengine Ark; hotwords
  and `domain_prompt` remain available.
- **Fail-open and integrity guards** — configuration/request/response errors
  return the raw transcript; incomplete `finish_reason` and Arabic digit
  sequences (compared in order) are rejected; inputs over 4000 characters skip
  the stage and `max_tokens` is sized from the input.
- **Optional Ark secrets declared, not required** — `VOLCENGINE_ARK_API_KEY`,
  `VOLCENGINE_CODING_API_KEY` and `ARK_API_KEY` are declared as optional
  `config_schema` secrets and read through `agent.secret_scope.get_secret()`.
  No Ark key is read from `config.yaml`.
- **Data framing** — the transcript is delimited as data and the model is told
  never to answer or act on it.
- Tests for provider registration, the opt-in matrix, fail-open behavior,
  truncation, digit changes, framing and the never-raising STT envelope.

### Credits

- [@peetteerr](https://github.com/peetteerr) for [PR #3](https://github.com/linxichen/hermes-volcengine-voice/pull/3),
  which added the `*args`/`**kwargs` STT compatibility fix and the original
  smart LLM post-processing work that this release hardens.

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
