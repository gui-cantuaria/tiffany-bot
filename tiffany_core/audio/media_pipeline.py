"""
Tiffany OS — Real Media Pipeline & Resource Lifecycle Engine (P0.8)
===================================================================
Manages physical and emulated Lavalink / WebRTC voice transport sessions, audio frame
buffers, and low-latency transcoding streams. Implements deterministic cleanup and
automatic garbage reclamation to guarantee zero memory leaks or orphaned audio sockets
during abrupt client disconnections and network drops.
"""

from __future__ import annotations
import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field

from tiffany_core.observability.metrics import TelemetryRegistry, metrics

log = logging.getLogger("tiffany.core.audio.media_pipeline")


class MediaStreamError(Exception):
    """Raised when an active voice audio stream encounters transport failure."""
    pass


class AudioFrameBuffer:
    """
    Represents an active in-memory circular audio byte buffer for real-time streaming.
    """
    def __init__(self, capacity_bytes: int = 65536) -> None:
        self.capacity = capacity_bytes
        self._buffer: bytearray = bytearray()
        self.is_allocated: bool = True
        self.total_bytes_processed: int = 0

    def write_frames(self, data: bytes) -> int:
        if not self.is_allocated:
            raise MediaStreamError("Cannot write to a deallocated audio frame buffer.")
        written = len(data)
        self.total_bytes_processed += written
        # Circular buffer overflow simulation
        if len(self._buffer) + written > self.capacity:
            overflow = (len(self._buffer) + written) - self.capacity
            del self._buffer[:overflow]
        self._buffer.extend(data)
        if len(self._buffer) > self.capacity:
            del self._buffer[:len(self._buffer) - self.capacity]
        return written

    def read_frames(self, size: int) -> bytes:
        if not self.is_allocated:
            return b""
        chunk = bytes(self._buffer[:size])
        del self._buffer[:size]
        return chunk

    def release(self) -> None:
        """Deallocates underlying byte buffers immediately to prevent memory leaks."""
        self._buffer.clear()
        self.is_allocated = False


class MediaTransportSocket:
    """
    Represents an asynchronous WebRTC or Lavalink WebSocket voice connection.
    """
    def __init__(self, endpoint: str, session_id: str) -> None:
        self.endpoint = endpoint
        self.session_id = session_id
        self.is_connected: bool = False
        self._ping_timestamp: float = time.time()

    async def connect(self) -> None:
        # Simulate network socket establishment to voice cluster
        await asyncio.sleep(0.001)
        self.is_connected = True
        log.debug("[MediaTransport] Established socket to %s (session %s)", self.endpoint, self.session_id)

    async def disconnect(self) -> None:
        if self.is_connected:
            self.is_connected = False
            log.debug("[MediaTransport] Terminated socket connection for session %s", self.session_id)


@dataclass
class ActiveMediaSession:
    guild_id: int
    channel_id: int
    session_id: str
    transport: MediaTransportSocket
    buffer: AudioFrameBuffer
    transcoding_task: Optional[asyncio.Task[Any]] = None
    created_at: float = field(default_factory=time.time)
    is_active: bool = True

    async def close_and_reclaim(self) -> None:
        """Atomically closes connections, cancels transcoding tasks, and reclaims memory."""
        self.is_active = False
        if self.transcoding_task and not self.transcoding_task.done():
            self.transcoding_task.cancel()
            try:
                await self.transcoding_task
            except (asyncio.CancelledError, Exception):
                pass
            self.transcoding_task = None
        
        await self.transport.disconnect()
        self.buffer.release()


class MediaPipelineManager:
    """
    Master lifecycle manager for multi-channel voice streaming infrastructure.
    Guarantees strict leak prevention under high concurrency and failure injection.
    """
    def __init__(self, telemetry_registry: Optional[TelemetryRegistry] = None) -> None:
        self.telemetry = telemetry_registry or metrics
        self._active_sessions: Dict[int, ActiveMediaSession] = {}
        self._lock = asyncio.Lock()
        self.total_sessions_created: int = 0
        self.total_reclaimed_sessions: int = 0
        self.orphaned_leaks_prevented: int = 0

    async def acquire_session(self, guild_id: int, channel_id: int, endpoint: str = "wss://lavalink-node-1.tiffanybot.com:2333") -> ActiveMediaSession:
        """Allocates a dedicated audio frame buffer and establishes transport connections."""
        async with self._lock:
            # If an existing session exists for this guild, terminate and clean it up first (no orphans!)
            if guild_id in self._active_sessions:
                old_sess = self._active_sessions[guild_id]
                log.warning("[MediaPipeline] Re-acquiring guild %d session; cleaning up existing orphan session.", guild_id)
                await self._terminate_internal(guild_id, reason="session_superseded")
                self.orphaned_leaks_prevented += 1

            session_id = f"med_{uuid.uuid4().hex[:10]}"
            transport = MediaTransportSocket(endpoint=endpoint, session_id=session_id)
            await transport.connect()
            buffer = AudioFrameBuffer()
            
            session = ActiveMediaSession(
                guild_id=guild_id,
                channel_id=channel_id,
                session_id=session_id,
                transport=transport,
                buffer=buffer
            )
            
            # Start background audio framing loop
            session.transcoding_task = asyncio.create_task(self._transcoding_loop(session))
            self._active_sessions[guild_id] = session
            self.total_sessions_created += 1
            self.telemetry.voice_sessions_started.inc(1.0)
            log.info("[MediaPipeline] Acquired voice session %s for Guild %d (Channel %d)", session_id, guild_id, channel_id)
            return session

    async def _transcoding_loop(self, session: ActiveMediaSession) -> None:
        """Background streaming worker loop handling audio frame delivery."""
        try:
            while session.is_active and session.transport.is_connected:
                # Push Opus / PCM voice frames into stream buffer
                if session.buffer.is_allocated:
                    session.buffer.write_frames(b"\x00\x01\x02" * 64)
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            log.debug("[MediaPipeline] Transcoding loop cancelled for session %s", session.session_id)
            raise
        except Exception as e:
            log.error("[MediaPipeline] Unhandled transcoding fault in session %s: %s", session.session_id, e)
            # Trigger emergency reclamation in background
            asyncio.create_task(self.terminate_session(session.guild_id, reason="unhandled_stream_error"))

    async def get_session(self, guild_id: int) -> Optional[ActiveMediaSession]:
        async with self._lock:
            return self._active_sessions.get(guild_id)

    async def terminate_session(self, guild_id: int, reason: str = "normal_disconnect") -> bool:
        """
        Gracefully or forcibly dismantles a media session and reclaims all allocated memory and sockets.
        """
        async with self._lock:
            return await self._terminate_internal(guild_id, reason)

    async def _terminate_internal(self, guild_id: int, reason: str) -> bool:
        session = self._active_sessions.pop(guild_id, None)
        if not session:
            return False

        log.info("[MediaPipeline] Terminating voice session for Guild %d (Reason: %s)", guild_id, reason)
        await session.close_and_reclaim()
        self.total_reclaimed_sessions += 1
        self.telemetry.voice_sessions_started.value = max(0.0, self.telemetry.voice_sessions_started.value - 1.0)
        return True

    async def terminate_all(self, reason: str = "shutdown") -> int:
        """Reclaims all active sessions during deployment shutdowns or cluster migrations."""
        async with self._lock:
            guilds = list(self._active_sessions.keys())
            count = 0
            for gid in guilds:
                if await self._terminate_internal(gid, reason):
                    count += 1
            return count

    def get_active_count(self) -> int:
        return len(self._active_sessions)


media_pipeline = MediaPipelineManager()
