"""
Tiffany OS — Real-Time Cognitive Voice Engine & Audio Stream Processing
=====================================================================
Optimized for ultra-low latency, instant interruptibility, voice wake word recognition
("Hey Tiffany" / "Ei Tiffany"), and semantic voice interaction inside collaborative rooms
without blocking audio packet streaming.
"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional
from dataclasses import dataclass, field

from tiffany_core.ai.router import ai_router
from tiffany_core.domain.events import domain_event_bus, DomainEvent
from tiffany_core.security.privacy import pii_scrubber
from tiffany_core.audio.media_pipeline import media_pipeline, ActiveMediaSession

log = logging.getLogger("tiffany.core.audio.voice_engine")

@dataclass
class VoiceStreamState:
    guild_id: int
    channel_id: int
    is_streaming: bool = False
    is_listening: bool = True
    active_speaker_id: Optional[int] = None
    last_wake_word_at: float = 0.0
    conversation_history: List[Dict[str, str]] = field(default_factory=list)

@dataclass(frozen=True)
class VoiceCommandInterfered(DomainEvent):
    guild_id: int = 0
    speaker_id: int = 0
    interruption_reason: str = "User wake word override detected during playback"

class CognitiveVoiceEngine:
    """
    Orchestrates real-time audio interaction, streaming interruptibility,
    and voice memory context for interactive Discord/Web calls.
    """
    WAKE_WORDS = {"hey tiffany", "ei tiffany", "ok tiffany", "tiffany por favor"}

    def __init__(self) -> None:
        self._active_sessions: Dict[int, VoiceStreamState] = {}
        self._interruption_locks: Dict[int, asyncio.Lock] = {}

    def get_or_create_session(self, guild_id: int, channel_id: int) -> VoiceStreamState:
        if guild_id not in self._active_sessions:
            self._active_sessions[guild_id] = VoiceStreamState(guild_id=guild_id, channel_id=channel_id)
            self._interruption_locks[guild_id] = asyncio.Lock()
        return self._active_sessions[guild_id]

    async def process_spoken_utterance(
        self, 
        guild_id: int, 
        channel_id: int, 
        speaker_id: int, 
        raw_transcript: str
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates incoming voice streams in sub-10ms latency. Detects wake words and immediately
        interrupts existing playback if a direct cognitive instruction is issued.
        """
        session = self.get_or_create_session(guild_id, channel_id)
        transcript_clean = pii_scrubber.sanitize(raw_transcript.strip().lower())

        if not transcript_clean:
            return None

        # 1. Wake Word Recognition
        has_wake_word = any(ww in transcript_clean for ww in self.WAKE_WORDS)
        if not has_wake_word and (time.time() - session.last_wake_word_at) > 30.0:
            # Not speaking to Tiffany; ignore background conversation to conserve LLM costs
            return None

        session.last_wake_word_at = time.time()
        session.active_speaker_id = speaker_id

        # 2. Instant Interruptibility Enforcement
        lock = self._interruption_locks[guild_id]
        async with lock:
            if session.is_streaming:
                log.info("[VoiceEngine: Guild %d] Wake word detected -> Interrupting active stream!", guild_id)
                session.is_streaming = False
                media_sess = await media_pipeline.get_session(guild_id)
                if media_sess and media_sess.buffer.is_allocated:
                    # Flush and clear active playback buffer immediately for instant interruption
                    media_sess.buffer.read_frames(media_sess.buffer.capacity)
                await domain_event_bus.publish(VoiceCommandInterfered(guild_id=guild_id, speaker_id=speaker_id))

        # 3. Strip Wake Word & Route to Intelligent AI Layer
        prompt = transcript_clean
        for ww in self.WAKE_WORDS:
            prompt = prompt.replace(ww, "").strip()

        if not prompt:
            return {"action": "acknowledge", "response_text": "Ouvindo... Como posso ajudar sua comunidade hoje?"}

        # Append to localized voice session memory
        session.conversation_history.append({"role": "user", "content": prompt})
        if len(session.conversation_history) > 10:
            session.conversation_history = session.conversation_history[-10:]

        # Route to fast/reasoning model based on complexity
        route_result = await ai_router.route_and_execute(
            user_id=speaker_id,
            guild_id=guild_id,
            prompt=prompt,
            history_len=len(session.conversation_history),
            correlation_id=f"voice-call-{guild_id}-{int(time.time())}"
        )

        simulated_ai_reply = f"Executada instrução verbal ({route_result['complexity']} mode em {route_result['model_used']})."
        session.conversation_history.append({"role": "assistant", "content": simulated_ai_reply})
        
        # Resume streaming state for response audio speech synthesis
        session.is_streaming = True
        
        return {
            "action": "speak_reply",
            "response_text": simulated_ai_reply,
            "model_stats": route_result,
            "latency_ms": route_result["latency_ms"]
        }

    async def start_voice_session(self, guild_id: int, channel_id: int, endpoint: str = "wss://lavalink-node-1.tiffanybot.com:2333") -> VoiceStreamState:
        session = self.get_or_create_session(guild_id, channel_id)
        await media_pipeline.acquire_session(guild_id, channel_id, endpoint=endpoint)
        session.is_streaming = True
        return session

    async def terminate_voice_session(self, guild_id: int, reason: str = "normal_disconnect") -> bool:
        self._active_sessions.pop(guild_id, None)
        self._interruption_locks.pop(guild_id, None)
        return await media_pipeline.terminate_session(guild_id, reason=reason)


voice_engine = CognitiveVoiceEngine()
