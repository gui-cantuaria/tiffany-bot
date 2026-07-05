# Voice/Music Technical Reference

Detailed reference for tiffany_voice.py internals. Only needed when modifying voice, music, or STT code.

## Platform Resolution
| Platform | Method |
|---|---|
| YouTube / YouTube Music | Direct yt-dlp download |
| Spotify | oEmbed API -> `__NEXT_DATA__` JSON / legacy regex fallback |
| Deezer | oEmbed + /track/{id} API fallback |
| Apple Music | oEmbed + URL parsing fallback |
| Amazon Music | URL path parsing |

## Playback Architecture
- Download audio to temp file via yt-dlp (through WARP SOCKS5 proxy on VPS)
- Play local file with FFmpeg (no proxy needed)
- Seek (`t!ff`): reuse downloaded file with FFmpeg `-ss` parameter, safety timeout on worker wait loop
- Session persistence: save current_query + queue to `voice_state.json`
- Queue limit: 50 songs max
- Playlist extraction: `extract_flat="in_playlist"`, `ignoreerrors: True`
- Shuffle: zip display+query together before shuffling (keeps them synchronized)

## Voice Recognition Pipeline
```
Discord voice packets -> discord-ext-voice-recv -> Opus decode
-> PCM buffer (per user, silence-gated, min 1s / max 10s rolling)
-> normalize_audio() -> vad_filter() (drops silence frames)
-> WAV 48kHz -> FFmpeg -> WAV 16kHz
-> _transcribe_wav_bytes() -> _pick_best_stt_transcript()
-> _parse_voice_command() -> speaker channel membership check -> action dispatch
```

**STT priority chain** (all run, best transcript selected):
1. **Whisper via OpenRouter** (`openai/whisper-large-v3`, env `STT_OPENROUTER_MODEL`) — primary
2. **Gemini chat STT** (`google/gemini-3.1-flash-lite`, env `STT_CHAT_MODEL`) — runs if Whisper fails or no wake word detected
3. **Google STT** (`speech_recognition.recognize_google`, free, pt-BR)
4. **Vosk** (offline, `vosk-model-small-pt-0.3/`)

`_pick_best_stt_transcript()`: prefers transcripts containing wake word "Tiffany" (fuzzy-normalized), then longest.
`_is_stt_bleed()`: filters YouTube/video "subscribe" phrases that leak via mic.
`STT_TAIL_SEC=6`: if audio > 6s, sends only last 6s to STT.

## AI Chat (`t!c`)
- AI semaphore: 3 concurrent calls max + global rate limit (15/min)
- Per-user sliding window: 5 turns in-memory, 3 turns persisted in `chat_memory.json`, 24h TTL
- Cooldown: 5s per user
- Supports image attachments (vision natively)

## Audio Clip (`t!clip`)
- Circular PCM buffer (last 30s, stereo 48kHz 16-bit, ~5.76MB max)
- All voice-recv audio stored in `session.clip_buffer`
- Exports as WAV file sent via `discord.File`
- Cooldown: 10s per user

## Idle & Cleanup
- Auto-disconnect after 5min idle (skips if 24/7 mode)
- Empty channel watchdog: checks every 60s, guard `_empty_channel_pending`
- `_after()` callback protected against `loop.is_closed()`
- Stale temp files (`tiffany_*`) cleaned on startup (>30min old)

## Random Music (`t!r`)
- ~5050 international songs in `random_songs.py`
- Avoids repeating last played random song

## Lavalink / wavelink
- Code integrated but **DISABLED** (`LAVALINK_ENABLED=0`) — VoiceRecvClient needed for voice listening
- Docker infra ready: `Dockerfile`, `docker-compose.yml`, `lavalink/application.yml`
- `VOICE_AUTO_REJOIN=0` (default) — bot does NOT auto-rejoin after restart

## WARP proxy (required for YouTube on the VPS)
YouTube blocks datacenter IPs, so yt-dlp routes through a Cloudflare WARP SOCKS5
proxy at `127.0.0.1:40000` (hardcoded in `YDL_OPTS["proxy"]`). Without it, ALL
music/playlist commands fail with "Não consegui extrair músicas".

- **Install/config:** `bash scripts/warp-setup.sh` (idempotent; forces proxy mode
  BEFORE connect so it never tunnels SSH and locks you out of the VPS).
- **Auto-recovery:** `scripts/warp-healthcheck.sh` + `tiffany-warp-healthcheck.timer`
  run every 3 min and reconnect WARP if the proxy drops.
- **systemd dependency:** `tiffany-bot.service` has `After/Wants=warp-svc.service`
  (soft dependency — news/offers still start if WARP is down).
- **Verify:** `curl -x socks5h://127.0.0.1:40000 https://cloudflare.com/cdn-cgi/trace`
  should print `warp=on`.

## Python version
- Ubuntu 22.04 ships Python 3.10; yt-dlp now warns 3.10 is deprecated.
- Migration plan lives in `docs/python-migration.md`. Not urgent, but plan it
  before yt-dlp drops 3.10 support.

## Known Issues
- Opus decoder may throw `OpusError: corrupted stream` — monkey-patched to return silence frames
- VPS YouTube blocking — resolved via Cloudflare WARP SOCKS5 proxy at 127.0.0.1:40000 (see WARP section)
