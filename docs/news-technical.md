# News Bot Technical Reference

Detailed reference for notices.py internals. Only needed when modifying news collection, AI analysis, or embed formatting.

## Score Thresholds
- General: >= 80 (NOTA_MIN_APROVACAO)
- Games: >= 85 (NOTA_MIN_GAMES)
- Urgent (role ping): >= 90 (NOTA_URGENTE) — max 3 pings per day (resets at midnight BR)

## Schedule
- Hours: 8h-18h Sao Paulo time (UTC-3)
- Interval: every 45 minutes (elapsed-time based)
- Pre-heating: entire 7h hour — RSS collected before 8h window opens

## AI Budget per Cycle
- Text analysis: max 3 calls (MAX_IA_CALLS_POR_CICLO)
- Vision validation: max 2 calls (MAX_VISION_CALLS_POR_CICLO)
- After vision budget exhausted, images accepted without AI validation
- Cooldown between AI calls: 15s
- Max 1 post per cycle, surplus queued
- Max 2 candidates per RSS source
- News older than 12h discarded

## Embed Layout (DO NOT CHANGE without authorization)
1. **Author:** `Via {Site} . {Category} {Emoji}`
2. **Title:** Journalistic, non-clickbait. 6-11 words, max 3 lines on screen. Alert emoji if nota >= 90. Max 256 chars.
3. **Description:** Single dense paragraph (4-6 sentences), formal Portuguese. Max 4096 chars.
4. **CTA Field:** `Click here to read full article` link
5. **Image:** Downloaded and attached as `discord.File` (not URL embed)
6. **Footer:** `Noticia resumida por IA` (+ `Fonte em ingles` for EN sources)
7. **Thread:** Auto-created: `Chat {Category}: {Title}` (max 100 chars)

## Image Pipeline
- Extract from RSS `<media:content>`, `<enclosure>`, og:image meta tags
- Validate: min 400x200px, no 403 responses, AI vision relevance check (budget-limited)
- Integrity: Content-Length vs bytes received, JPEG EOF (FFD9), PNG IEND chunk
- Timeout: 30s, 3 retries
- Attach as `discord.File` (never post without image)

## Dedup System
- URL hash + SimHash (Hamming distance <= 6) + title fingerprint
- In-cycle: `_cycle_titles` and `_cycle_simhashes` sets (in-memory only, do NOT pollute persistent history)
- Persistent: `_simhash_idx` and `_title_idx` in `notices_history.json`
- Title/simhash only added to persistent history AFTER IA approval (Fase 2)

## AI Model
- Unified model: google/gemini-3.1-flash-lite (via OpenRouter)
- No fallback chain — same model for all attempts (3 retries with backoff)
- Cost: ~$0.25/M input, $1.50/M output tokens
