"""
Comandos de voz estilo assistente: /tiffany entra na call, ouve o áudio e
interpreta frases como «Tiffany, toca ...». Reprodução via yt-dlp (YouTube
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
from discord import FFmpegPCMAudio, PCMVolumeTransformer, app_commands
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

    # Busca padrão no PATH (Linux/macOS/Windows).
    for candidate in ("ffmpeg", "ffmpeg.exe"):
        found = shutil.which(candidate)
        if found:
            return found

    # Alguns caminhos comuns no Windows quando o binário foi extraído manualmente.
    if os.name == "nt":
        roots = [os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)"), os.getenv("LOCALAPPDATA")]
        for root in roots:
            if not root:
                continue
            candidate = os.path.join(root, "ffmpeg", "bin", "ffmpeg.exe")
            if os.path.isfile(candidate):
                return candidate

    # Fallback opcional se imageio-ffmpeg estiver instalado no ambiente.
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

# Discord voice pode ficar pendente indefinidamente se UDP estiver bloqueado (comum em alguns PaaS).
def _voice_connect_timeout_sec() -> float:
    try:
        return max(5.0, min(float(os.getenv("VOICE_CONNECT_TIMEOUT_SEC", "25")), 120.0))
    except ValueError:
        return 25.0


# ~1.5s de PCM estéreo 48kHz s16le antes de tentar STT
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
    """
    Retorna (ação, argumento).
    ação: 'play' | 'stop' | 'none'
    """
    t = _normalize_transcript(text)
    if "tiffany" not in t and "tifani" not in t:
        return "none", None

    if re.search(
        r"tiffany\s*,?\s*(para|parar|stop|pause|pausa)\b|"
        r"tifani\s*,?\s*(para|parar|stop|pause|pausa)\b",
        t,
    ):
        return "stop", None

    m = re.search(
        r"(?:tiffany|tifani)\s*,?\s*(?:toca|reproduz|play|coloca)\s+(.+)",
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
    title = info.get("title") or info.get("id") or "áudio"
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
                            f"❌ Não consegui achar áudio para: `{query[:80]}`",
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
    # Avisa no texto que estou ouvindo
    await _notify(bot, session.text_channel_id, "🎙️ **Tiffany está ouvindo o canal de voz...** (diga «Tiffany, toca ...»)")
    _last_heard_notify = 0.0
    _last_audio_time = asyncio.get_event_loop().time()
    _warned_no_audio = False
    try:
        while vc.is_connected():
            await asyncio.sleep(5.0)
            if not vc.is_connected():
                break
            # Diagnóstico: se passou 60s sem receber nenhum áudio, avisa
            if not _warned_no_audio and (asyncio.get_event_loop().time() - _last_audio_time) > 60:
                await _notify(
                    bot,
                    session.text_channel_id,
                    "⚠️ Não recebi nenhum áudio após 60s. Seu host pode estar bloqueando UDP (comum na Discloud). "
                    "Comandos por fala podem não funcionar — use comandos de texto ou um VPS.",
                )
                _warned_no_audio = True
            if vc.is_playing():
                continue
            pcm = _drain_loudest_user_pcm(session)
            if len(pcm) < MIN_PCM_BYTES:
                continue
            _last_audio_time = asyncio.get_event_loop().time()
            wav = await asyncio.to_thread(_pcm_stereo_to_wav, pcm)
            text = await asyncio.to_thread(_transcribe_wav_bytes, wav)
            if not text:
                # Feedback ocasional de que ouviu mas não entendeu fala
                agora = asyncio.get_event_loop().time()
                if agora - _last_heard_notify > 60:
                    await _notify(bot, session.text_channel_id, "🎙️ Ouvido, mas não entendi. Tente: **«Tiffany, toca <música>»**")
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
    """Conecta ou move o cliente VoiceRecv para o canal."""
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
    @bot.tree.command(
        name="tiffany",
        description="Adiciona a Tiffany ao seu canal de voz (call). Depois você pode pedir música por voz.",
    )
    @app_commands.guild_only()
    async def cmd_tiffany(interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use este comando dentro de um servidor.", ephemeral=True)
            return
        guild = interaction.guild
        member = interaction.user
        if not member.voice or not member.voice.channel:
            await interaction.response.send_message(
                "Entre em um **canal de voz** antes de usar `/tiffany`.",
                ephemeral=True,
            )
            return
        channel = member.voice.channel
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Canal de palco não suportado para este modo.", ephemeral=True)
            return

        bot_member = guild.me or (guild.get_member(bot.user.id) if bot.user else None)
        if bot_member is None:
            await interaction.response.send_message(
                "Não consegui validar as permissões do bot neste servidor. Tente novamente em alguns segundos.",
                ephemeral=True,
            )
            return
        perms = channel.permissions_for(bot_member)
        missing: list[str] = []
        if not perms.view_channel:
            missing.append("Ver Canal")
        if not perms.connect:
            missing.append("Conectar")
        if not perms.speak:
            missing.append("Falar")
        if missing:
            await interaction.response.send_message(
                "Não tenho permissão suficiente para entrar na call.\n"
                f"Faltando em **{channel.name}**: `{', '.join(missing)}`.",
                ephemeral=True,
            )
            return

        if not _ffmpeg_available():
            await interaction.response.send_message(
                "FFmpeg não foi encontrado no host.\n"
                f"Defina `FFMPEG_PATH` corretamente ou adicione `ffmpeg` ao PATH. Valor atual: `{FFMPEG_PATH}`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await _ensure_opus()
        except Exception as e:
            log.warning("Opus: %s", e)

        gid = guild.id

        prev = _sessions.get(gid)
        if prev:
            if prev.listen_task:
                prev.listen_task.cancel()
            if prev.music_task:
                prev.music_task.cancel()

        timeout = _voice_connect_timeout_sec()
        try:
            log.info(
                "Conectando voice: guild=%s channel=%s timeout=%ss",
                guild.id,
                channel.id,
                timeout,
            )
            vc = await asyncio.wait_for(
                _join_voice_recv_client(guild, channel),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            log.warning(
                "Timeout voice connect guild=%s channel=%s após %ss",
                guild.id,
                channel.id,
                timeout,
            )
            vc_left = guild.voice_client
            if vc_left and vc_left.is_connected():
                try:
                    await vc_left.disconnect(force=True)
                except Exception:
                    pass
            await interaction.followup.send(
                "⏱️ **Tempo esgotado** ao conectar no canal de voz.\n\n"
                "O Discord fica em *“Tiffany is thinking…”* enquanto a conexão de **voz** não termina. "
                "Se isso demora e falha, muitas vezes o host **bloqueia UDP** usado pelo voice.\n\n"
                "**Na Discloud:** confirme no suporte se o seu plano permite **Discord Voice** (saída UDP). "
                "Se não permitir, a feature de call só roda de forma confiável em **PC local** ou **VPS**.\n\n"
                f"Você pode ajustar o limite com `VOICE_CONNECT_TIMEOUT_SEC` (atual: **{timeout:g}s**).",
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(
                f"Não consegui entrar no canal de voz: `{e}`\n"
                "Verifique conectividade com o Discord Voice Gateway e permissões do canal.",
                ephemeral=True,
            )
            return

        session = _GuildVoiceSession(text_channel_id=interaction.channel_id)
        sink = _PCMBufferSink(session)
        captura_ok = True
        try:
            vc.listen(sink)
            session.listen_task = asyncio.create_task(
                _voice_listen_loop(gid, vc, bot),
                name=f"tiffany-voice-{gid}",
            )
        except Exception as e:
            captura_ok = False
            # Em alguns hosts, conectar funciona mas a recepção de voz (UDP/Opus) falha.
            log.exception("Falha ao iniciar captura de voz guild=%s: %s", gid, e)
            session.listen_task = None

        session.music_task = asyncio.create_task(
            _play_worker(gid, vc, bot),
            name=f"tiffany-music-{gid}",
        )
        _sessions[gid] = session

        aviso_captura = ""
        if not captura_ok:
            aviso_captura = (
                "\n\n⚠️ Consegui entrar na call, mas a **captura de voz** falhou neste host. "
                "A reprodução por fila/comandos ainda funciona, porém comandos por fala podem não funcionar."
            )

        await interaction.followup.send(
            f"✅ **Tiffany adicionada** ao canal de voz **{channel.name}**.\n\n"
            "Enquanto estiver na call, você pode falar, por exemplo: "
            "**«Tiffany, toca …»** (nome da música ou link do YouTube/Spotify).\n"
            "Use **`/tiffany_sair`** para eu sair do canal."
            f"{aviso_captura}",
            ephemeral=True,
        )

    @bot.tree.command(name="tiffany_sair", description="Desconecta a Tiffany do canal de voz.")
    @app_commands.guild_only()
    async def cmd_tiffany_sair(interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Use em um servidor.", ephemeral=True)
            return
        gid = interaction.guild.id
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            await interaction.response.send_message("Não estou em nenhum canal de voz.", ephemeral=True)
            return
        sess = _sessions.pop(gid, None)
        if sess:
            if sess.listen_task:
                sess.listen_task.cancel()
            if sess.music_task:
                sess.music_task.cancel()
        await vc.disconnect(force=True)
        await interaction.response.send_message("Saí do canal de voz.", ephemeral=True)

    @bot.tree.command(name="next", description="Pula a faixa atual e toca a próxima da fila.")
    @app_commands.guild_only()
    async def cmd_next(interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Use em um servidor.", ephemeral=True)
            return

        guild = interaction.guild
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            await interaction.response.send_message("Não estou em nenhum canal de voz.", ephemeral=True)
            return

        session = _sessions.get(guild.id)
        if not session:
            await interaction.response.send_message("A sessão de voz não está ativa no momento.", ephemeral=True)
            return

        if not vc.is_playing():
            await interaction.response.send_message("Não tem faixa tocando agora.", ephemeral=True)
            return

        prox_na_fila = session.music_queue.qsize()
        vc.stop_playing()
        if prox_na_fila > 0:
            await interaction.response.send_message(
                f"⏭️ Faixa pulada. Tocando a próxima (restantes na fila: {prox_na_fila}).",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "⏭️ Faixa pulada. Não há próximas músicas na fila.",
                ephemeral=True,
            )

    # =========================
    # COMANDOS DE CHAT (música)
    # =========================
    _RANDOM_SONGS = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Astley - Never Gonna Give You Up
        "https://www.youtube.com/watch?v=9bZkp7q19f0",  # PSY - GANGNAM STYLE
        "https://www.youtube.com/watch?v=kJQP7kiw5Fk",  # Luis Fonsi - Despacito
        "https://www.youtube.com/watch?v=RgKAFK5djSk",  # Wiz Khalifa - See You Again
        "https://www.youtube.com/watch?v=JGwWNGJdvx8",  # Ed Sheeran - Shape of You
        "https://www.youtube.com/watch?v=YR3nmjxJY74",  # Mark Ronson - Uptown Funk
        "https://www.youtube.com/watch?v=YQHsXMglC9A",  # Adele - Hello
        "https://www.youtube.com/watch?v=ru0K8uYEZWw",  # Taylor Swift - Shake It Off
    ]

    async def _get_session_for_chat(guild: discord.Guild, bot: commands.Bot) -> tuple:
        """Retorna (session, vc) se houver sessão ativa; senão cria uma nova."""
        gid = guild.id
        sess = _sessions.get(gid)
        vc = guild.voice_client
        if sess and vc and vc.is_connected():
            return sess, vc
        # Tenta recuperar de algum canal de voz onde o bot esteja
        if vc and vc.is_connected() and isinstance(vc, voice_recv.VoiceRecvClient):
            sess = _GuildVoiceSession(text_channel_id=0)
            sink = _PCMBufferSink(sess)
            try:
                vc.listen(sink)
                sess.listen_task = asyncio.create_task(
                    _voice_listen_loop(gid, vc, bot),
                    name=f"tiffany-voice-{gid}",
                )
            except Exception:
                sess.listen_task = None
            sess.music_task = asyncio.create_task(
                _play_worker(gid, vc, bot),
                name=f"tiffany-music-{gid}",
            )
            _sessions[gid] = sess
            return sess, vc
        return None, None

    @bot.command(name="p", help="Toca música do link: @p <url> ou @p <nome>")
    async def cmd_p(ctx: commands.Context, *, query: str = ""):
        if not ctx.guild:
            return
        if not query:
            await ctx.send("🎵 Use: `@p <link do YouTube/Spotify>` ou `@p <nome da música>`")
            return
        sess, vc = await _get_session_for_chat(ctx.guild, bot)
        if not sess:
            await ctx.send("⚠️ Entre em um canal de voz primeiro ou use `/tiffany`.")
            return
        q = query.strip()
        if "open.spotify.com" in q or q.startswith("spotify:"):
            pass
        elif not re.match(r"^https?://", q):
            q = f"ytsearch1:{q}"
        await sess.music_queue.put(q)
        await ctx.send(f"🎵 Adicionado à fila: **{query[:100]}**")

    @bot.command(name="rm", help="Toca uma música aleatória: @rm")
    async def cmd_rm(ctx: commands.Context):
        if not ctx.guild:
            return
        sess, vc = await _get_session_for_chat(ctx.guild, bot)
        if not sess:
            await ctx.send("⚠️ Entre em um canal de voz primeiro ou use `/tiffany`.")
            return
        import random
        url = random.choice(_RANDOM_SONGS)
        await sess.music_queue.put(url)
        await ctx.send(f"🎲 Música aleatória adicionada à fila!")

    log.info("Comandos de voz (/tiffany, /tiffany_sair, /next) e chat (@p, @rm) registrados.")
