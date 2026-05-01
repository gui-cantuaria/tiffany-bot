"""
Comandos de voz estilo assistente: $tiffany entra na call, ouve o audio e
interpreta frases como «Tiffany, toca ...». Reproducao via yt-dlp (YouTube
busca ou URL Spotify/YouTube). Requer FFmpeg no PATH e PyNaCl.
"""

from __future__ import annotations

import asyncio
import audioop
import importlib
import io
import logging
import os
import re
import shutil
import threading
import wave
from dataclasses import dataclass, field
from typing import Any, Optional

import discord
import yt_dlp
from discord import FFmpegPCMAudio, PCMVolumeTransformer
from discord.ext import commands, voice_recv

log = logging.getLogger("tiffany-bot.voice")

def _resolve_ffmpeg_executable() -> Optional[str]:
    env_path = (os.getenv("FFMPEG_PATH") or "").strip()
    if env_path:
        if os.path.isabs(env_path) and os.path.isfile(env_path):
            return env_path
        by_name = shutil.which(env_path)
        if by_name:
            return by_name

    for candidate in ("ffmpeg", "ffmpeg.exe"):
        found = shutil.which(candidate)
        if found:
            return found

    if os.name == "nt":
        roots = [os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)"), os.getenv("LOCALAPPDATA")]
        for root in roots:
            if not root:
                continue
            candidate = os.path.join(root, "ffmpeg", "bin", "ffmpeg.exe")
            if os.path.isfile(candidate):
                return candidate

    try:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        candidate = imageio_ffmpeg.get_ffmpeg_exe()
        if candidate and os.path.isfile(candidate):
            return candidate
    except Exception:
        pass

    return None


FFMPEG_EXECUTABLE = _resolve_ffmpeg_executable()
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")

def _voice_connect_timeout_sec() -> float:
    try:
        return max(5.0, min(float(os.getenv("VOICE_CONNECT_TIMEOUT_SEC", "25")), 120.0))
    except ValueError:
        return 25.0


MIN_PCM_BYTES = int(48000 * 2 * 2 * 1.5)

YDL_OPTS: dict[str, Any] = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "ignoreerrors": False,
}

FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


def _ffmpeg_available() -> bool:
    return FFMPEG_EXECUTABLE is not None


@dataclass
class _GuildVoiceSession:
    text_channel_id: int
    pcm_buffers: dict[int, bytearray] = field(default_factory=dict)
    buf_lock: threading.Lock = field(default_factory=threading.Lock)
    listen_task: Optional[asyncio.Task] = None
    music_task: Optional[asyncio.Task] = None
    music_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    play_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_sessions: dict[int, _GuildVoiceSession] = {}
_ytdl = yt_dlp.YoutubeDL(YDL_OPTS)


def _normalize_transcript(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower().strip())


def _parse_voice_command(text: str) -> tuple[str, Optional[str]]:
    t = _normalize_transcript(text)
    if "tiffany" not in t and "tifani" not in t:
        return "none", None

    if re.search(
        r"tiffany\s*,\s*(para|parar|stop|pause|pausa)\b|"
        r"tifani\s*,\s*(para|parar|stop|pause|pausa)\b",
        t,
    ):
        return "stop", None

    m = re.search(
        r"(?:tiffany|tifani)\s*,\s*(?:toca|reproduz|play|coloca)\s+(.+)",
        t,
        re.IGNORECASE,
    )
    if m:
        q = m.group(1).strip()
        q = re.sub(r"^(a música|a musica|música|musica)\s+", "", q, flags=re.IGNORECASE)
        if q:
            return "play", q[:200]

    return "none", None


def _pcm_stereo_to_wav(pcm_stereo: bytes) -> bytes:
    mono = audioop.tomono(pcm_stereo, 2, 0.5, 0.5)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        wf.writeframes(mono)
    return buf.getvalue()


def _transcribe_wav_bytes(wav: bytes) -> Optional[str]:
    try:
        sr = importlib.import_module("speech_recognition")
    except ModuleNotFoundError:
        log.warning("Pacote SpeechRecognition não instalado; STT desativado.")
        return None

    r = sr.Recognizer()
    r.dynamic_energy_threshold = True
    with sr.AudioFile(io.BytesIO(wav)) as source:
        audio = r.record(source)
    try:
        return r.recognize_google(audio, language="pt-BR")
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        log.warning("SpeechRecognition indisponível: %s", e)
        return None


def _extract_audio(info: dict[str, Any]) -> tuple[Optional[str], str]:
    if info is None:
        return None, "?"
    if "entries" in info and info["entries"]:
        info = info["entries"][0]
    title = info.get("title") or info.get("id") or "audio"
    url = info.get("url")
    if url:
        return url, title
    for f in info.get("formats") or ():
        if f.get("acodec") != "none" and f.get("url"):
            return f["url"], title
    return None, title


def _blocking_ytdl_extract(query: str) -> tuple[Optional[str], str]:
    try:
        info = _ytdl.extract_info(query, download=False)
    except Exception as e:
        log.exception("yt-dlp falhou: %s", e)
        return None, str(e)
    return _extract_audio(info)


class _PCMBufferSink(voice_recv.AudioSink):
    def __init__(self, session: _GuildVoiceSession):
        super().__init__()
        self._session = session

    def wants_opus(self) -> bool:
        return False

    def write(self, user: discord.Member | discord.User | None, data: Any) -> None:
        if user is None or getattr(user, "bot", False):
            return
        pcm = data.pcm
        if not pcm:
            return
        uid = user.id
        with self._session.buf_lock:
            self._session.pcm_buffers.setdefault(uid, bytearray()).extend(pcm)

    def cleanup(self) -> None:
        pass


def _drain_loudest_user_pcm(session: _GuildVoiceSession) -> bytes:
    with session.buf_lock:
        if not session.pcm_buffers:
            return b""
        uid, buf = max(session.pcm_buffers.items(), key=lambda kv: len(kv[1]))
        raw = bytes(buf)
        session.pcm_buffers.clear()
    return raw


async def _notify(bot: discord.Client, channel_id: int, content: str) -> None:
    ch = bot.get_channel(channel_id)
    if ch and hasattr(ch, "send"):
        try:
            await ch.send(content)
        except discord.HTTPException:
            log.warning("Falha ao enviar mensagem no canal %s", channel_id)


async def _ensure_opus() -> None:
    if discord.opus.is_loaded():
        return
    p = os.getenv("OPUS_LIB_PATH")
    if p:
        discord.opus.load_opus(p)
        return
    try:
        discord.opus._load_default()
    except Exception:
        log.warning("Opus não carregado explicitamente; discord pode falhar em voice.")


class _YTSource(PCMVolumeTransformer):
    @classmethod
    async def from_query(cls, query: str, *, volume: float = 0.35) -> Optional[_YTSource]:
        loop = asyncio.get_running_loop()
        url, _title = await loop.run_in_executor(None, lambda: _blocking_ytdl_extract(query))
        if not url:
            return None
        src = FFmpegPCMAudio(url, executable=FFMPEG_EXECUTABLE or FFMPEG_PATH, **FFMPEG_OPTS)
        return cls(src, volume=volume)


async def _play_worker(guild_id: int, vc: voice_recv.VoiceRecvClient, bot: discord.Client) -> None:
    try:
        while vc.is_connected():
            session = _sessions.get(guild_id)
            if not session:
                await asyncio.sleep(0.25)
                continue
            try:
                query = await asyncio.wait_for(session.music_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            try:
                async with session.play_lock:
                    if not vc.is_connected():
                        break
                    source = await _YTSource.from_query(query)
                    if source is None:
                        await _notify(
                            bot,
                            session.text_channel_id,
                            f"❌ Não consegui achar audio para: `{query[:80]}`",
                        )
                        session.music_queue.task_done()
                        continue

                    loop = asyncio.get_running_loop()
                    fut: asyncio.Future = loop.create_future()

                    def _after(err: Optional[Exception]) -> None:
                        if err:
                            log.error("Erro no player: %s", err)
                        if not fut.done():
                            loop.call_soon_threadsafe(fut.set_result, None)

                    vc.play(source, after=_after)
                    await fut
            except Exception:
                log.exception("Erro no worker de música")
            finally:
                try:
                    session.music_queue.task_done()
                except ValueError:
                    pass
    except asyncio.CancelledError:
        raise


async def _voice_listen_loop(
    guild_id: int,
    vc: voice_recv.VoiceRecvClient,
    bot: discord.Client,
) -> None:
    session = _sessions.get(guild_id)
    if not session:
        return
    await _notify(bot, session.text_channel_id, "🎙️ **Tiffany está ouvindo o canal de voz...** (diga «Tiffany, toca ...»)")
    _last_heard_notify = 0.0
    _last_audio_time = asyncio.get_event_loop().time()
    _warned_no_audio = False
    try:
        while vc.is_connected():
            await asyncio.sleep(5.0)
            if not vc.is_connected():
                break
            if vc.is_playing():
                continue

            # Diagnóstico: se passou 60s sem receber nenhum audio, avisa
            if not _warned_no_audio and (asyncio.get_event_loop().time() - _last_audio_time) > 60:
                await _notify(
                    bot,
                    session.text_channel_id,
                    "⚠️ Não recebi nenhum audio após 60s. Seu host pode estar bloqueando UDP (comum na Discloud). "
                    "Comandos por fala podem não funcionar — use comandos de texto ou um VPS.",
                )
                _warned_no_audio = True

            pcm = _drain_loudest_user_pcm(session)
            if len(pcm) < MIN_PCM_BYTES:
                continue
            _last_audio_time = asyncio.get_event_loop().time()
            wav = await asyncio.to_thread(_pcm_stereo_to_wav, pcm)
            text = await asyncio.to_thread(_transcribe_wav_bytes, wav)
            if not text:
                agora = asyncio.get_event_loop().time()
                if agora - _last_heard_notify > 60:
                    await _notify(bot, session.text_channel_id, "🎙️ Ouvido, mas não entendi. Tente: **«Tiffany, toca <musica>»**")
                    _last_heard_notify = agora
                continue
            action, arg = _parse_voice_command(text)
            log.info("STT guild=%s: %r -> %s %r", guild_id, text, action, arg)
            if action == "none":
                agora = asyncio.get_event_loop().time()
                if agora - _last_heard_notify > 30:
                    await _notify(bot, session.text_channel_id, f"🎙️ Entendi: «{text[:60]}», mas não é um comando. Diga: **«Tiffany, toca ...»**")
                    _last_heard_notify = agora
                continue
            if action == "stop":
                vc.stop_playing()
                await _notify(bot, session.text_channel_id, "⏹️ Reprodução interrompida (comando de voz).")
                continue
            if action == "play" and arg:
                q = arg.strip()
                if "open.spotify.com" in q or q.startswith("spotify:"):
                    q = q
                elif not re.match(r"^https?://", q):
                    q = f"ytsearch1:{q}"
                await session.music_queue.put(q)
                await _notify(
                    bot,
                    session.text_channel_id,
                    f"🎵 Entendido: **{arg[:100]}** — adicionando à fila.",
                )
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("Loop de escuta encerrou com erro")
    finally:
        try:
            vc.stop_listening()
        except Exception:
            pass
        cur = _sessions.get(guild_id)
        if cur is session:
            removed = _sessions.pop(guild_id, None)
            if removed and removed.music_task:
                removed.music_task.cancel()


async def _join_voice_recv_client(
    guild: discord.Guild,
    channel: discord.VoiceChannel,
) -> voice_recv.VoiceRecvClient:
    vc_existing = guild.voice_client
    if (
        vc_existing
        and vc_existing.is_connected()
        and isinstance(vc_existing, voice_recv.VoiceRecvClient)
    ):
        try:
            vc_existing.stop_listening()
        except Exception:
            pass
        await vc_existing.move_to(channel)
        return vc_existing
    if vc_existing and vc_existing.is_connected():
        await vc_existing.disconnect(force=True)
    return await channel.connect(
        cls=voice_recv.VoiceRecvClient,
        self_deaf=False,
    )


def register_voice(bot: commands.Bot) -> None:
    _RANDOM_SONGS = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=9bZkp7q19f0",
        "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
        "https://www.youtube.com/watch?v=RgKAFK5djSk",
        "https://www.youtube.com/watch?v=JGwWNGJdvx8",
        "https://www.youtube.com/watch?v=YR3nmjxJY74",
        "https://www.youtube.com/watch?v=YQHsXMglC9A",
        "https://www.youtube.com/watch?v=ru0K8uYEZWw",
    ]

    async def _ensure_connected(ctx: commands.Context) -> tuple:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            await ctx.send("⚠️ Use este comando em um servidor.")
            return None, None

        user_vc = ctx.author.voice
        if not user_vc or not user_vc.channel:
            await ctx.send("⚠️ Você precisa estar em um **canal de voz** primeiro.")
            return None, None

        guild = ctx.guild
        gid = guild.id
        channel = user_vc.channel

        # Já está conectado?
        sess = _sessions.get(gid)
        vc = guild.voice_client
        if sess and vc and vc.is_connected() and isinstance(vc, voice_recv.VoiceRecvClient):
            if vc.channel.id == channel.id:
                return sess, vc
            # Se está em outro canal, move
            try:
                await vc.move_to(channel)
                return sess, vc
            except Exception as e:
                await ctx.send(f"⚠️ Erro ao mover para o canal: {e}")
                return None, None

        # Verificar permissoes
        bot_member = guild.me
        if bot_member:
            perms = channel.permissions_for(bot_member)
            if not perms.connect or not perms.speak:
                await ctx.send("⚠️ Não tenho permissão para entrar ou falar neste canal de voz.")
                return None, None

        # Conectar
        try:
            await _ensure_opus()
        except Exception:
            pass

        try:
            timeout = _voice_connect_timeout_sec()
            vc = await asyncio.wait_for(
                _join_voice_recv_client(guild, channel),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Tempo esgotado ao conectar no canal de voz. Verifique se o host permite UDP.")
            return None, None
        except Exception as e:
            await ctx.send(f"⚠️ Erro ao entrar no canal de voz: {e}")
            return None, None

        # Criar sessão
        session = _GuildVoiceSession(text_channel_id=ctx.channel.id)
        sink = _PCMBufferSink(session)
        try:
            vc.listen(sink)
            session.listen_task = asyncio.create_task(
                _voice_listen_loop(gid, vc, bot),
                name=f"tiffany-voice-{gid}",
            )
        except Exception as e:
            log.warning("Falha ao iniciar escuta: %s", e)
            session.listen_task = None

        session.music_task = asyncio.create_task(
            _play_worker(gid, vc, bot),
            name=f"tiffany-music-{gid}",
        )
        _sessions[gid] = session

        log.info("Sessão criada guild=%s voice=%s music=%s", gid, session.listen_task is not None, session.music_task is not None)
        await ctx.send(f"✅ **Tiffany adicionada** ao canal de voz **{channel.name}**.")
        return session, vc

    @bot.command(name="tiffany", help="Adiciona a Tiffany ao seu canal de voz. Depois você pode pedir musica por voz.")
    async def cmd_tiffany(ctx: commands.Context):
        sess, vc = await _ensure_connected(ctx)
        if not sess:
            return
        await ctx.send("🎙️ **Tiffany está ouvindo o canal de voz...** (diga «Tiffany, toca ...»)")

    @bot.command(name="play", help="Toca música: $play <url> ou $play <nome>")
    async def cmd_play(ctx: commands.Context, *, query: str = ""):
        if not ctx.guild:
            return
        if not query:
            await ctx.send("🎵 Use: `$play <link do YouTube/Spotify>` ou `$play <nome da música>`")
            return
        sess, vc = await _ensure_connected(ctx)
        if not sess:
            return
        q = query.strip()
        if "open.spotify.com" in q or q.startswith("spotify:"):
            pass
        elif not re.match(r"^https?://", q):
            q = f"ytsearch1:{q}"
        
        # Debug: log queue state
        log.info("Play cmd: putting query '%s' into queue (size before: %d)", q, sess.music_queue.qsize())
        await sess.music_queue.put(q)
        await ctx.send(f"🎵 Adicionado à fila: **{query[:100]}** (fila: {sess.music_queue.qsize()})")
        
        # Ensure worker is running
        gid = ctx.guild.id
        if sess.music_task is None or sess.music_task.done():
            log.warning("Music worker not running, restarting...")
            sess.music_task = asyncio.create_task(
                _play_worker(gid, vc, bot),
                name=f"tiffany-music-{gid}",
            )

    @bot.command(name="rm", help="Toca uma musica aleatoria: $rm")
    async def cmd_rm(ctx: commands.Context):
        if not ctx.guild:
            return
        sess, vc = await _ensure_connected(ctx)
        if not sess:
            return
        import random
        url = random.choice(_RANDOM_SONGS)
        await sess.music_queue.put(url)
        await ctx.send("🎲 Musica aleatoria adicionada à fila!")

    @bot.command(name="leave", help="Desconecta a Tiffany do canal de voz.")
    async def cmd_leave(ctx: commands.Context):
        if not ctx.guild:
            return
        gid = ctx.guild.id
        sess = _sessions.pop(gid, None)
        if sess:
            if sess.listen_task:
                sess.listen_task.cancel()
            if sess.music_task:
                sess.music_task.cancel()
        vc = ctx.guild.voice_client
        if vc and vc.is_connected():
            await vc.disconnect(force=True)
            await ctx.send("👋 **Tiffany saiu** do canal de voz.")
        else:
            await ctx.send("⚠️ Não estou em nenhum canal de voz.")

    @bot.command(name="next", help="Pula a faixa atual e toca a proxima da fila.")
    async def cmd_next(ctx: commands.Context):
        if not ctx.guild:
            return
        guild = ctx.guild
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            await ctx.send("⚠️ Não estou em nenhum canal de voz.")
            return
        session = _sessions.get(guild.id)
        if not session:
            await ctx.send("⚠️ A sessão de voz não está ativa no momento.")
            return
        if not vc.is_playing():
            await ctx.send("⚠️ Não tem faixa tocando agora.")
            return
        prox_na_fila = session.music_queue.qsize()
        vc.stop_playing()
        if prox_na_fila > 0:
            await ctx.send(f"⏭️ Faixa pulada. Tocando a proxima (restantes na fila: {prox_na_fila}).")
        else:
            await ctx.send("⏭️ Faixa pulada. Não há proximas musicas na fila.")

    log.info("Comandos de voz registrados: $tiffany, $play/$p, $rm, $leave, $next")
