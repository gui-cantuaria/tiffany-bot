"""
Comandos de voz estilo assistente: $e entra na call, ouve o audio e
interpreta frases como «Tiffany, ...». Reproducao via yt-dlp (YouTube
busca ou URL Spotify/YouTube). Responde perguntas por voz (TTS) ou chat.
Requer FFmpeg no PATH e PyNaCl.
"""

from __future__ import annotations

import asyncio
import importlib
import io
import tempfile
import logging
import os
import re
import shutil
import threading
import wave
from dataclasses import dataclass, field
from typing import Any, Optional

import discord
from discord import FFmpegPCMAudio, PCMVolumeTransformer
from discord.ext import commands

try:
    from discord.ext import voice_recv as voice_recv
    _VOICE_RECV_AVAILABLE = True
except Exception as _e:
    voice_recv = None  # type: ignore
    _VOICE_RECV_AVAILABLE = False
    import logging as _log_tmp
    _log_tmp.getLogger("tiffany-bot.voice").warning(
        "discord-ext-voice-recv não disponível (%s) — escuta de voz desativada, demais comandos funcionam normalmente.", _e
    )

try:
    import yt_dlp as yt_dlp
    _YTDLP_AVAILABLE = True
except Exception:
    yt_dlp = None  # type: ignore
    _YTDLP_AVAILABLE = False

log = logging.getLogger("tiffany-bot.voice")

# audioop foi removido no Python 3.13 — usa fallback puro se necessário
try:
    import audioop as _audioop
    def _tomono(data: bytes) -> bytes:
        return _audioop.tomono(data, 2, 0.5, 0.5)
except ImportError:
    import struct as _struct
    def _tomono(data: bytes) -> bytes:
        count = len(data) // 4  # 2 bytes * 2 canais
        out = bytearray(count * 2)
        for i in range(count):
            l, r = _struct.unpack_from("<hh", data, i * 4)
            mono = max(-32768, min(32767, int(l * 0.5 + r * 0.5)))
            _struct.pack_into("<h", out, i * 2, mono)
        return bytes(out)

# TTS via OpenRouter ou gTTS
_TTS_ENABLED = os.getenv("TTS_ENABLED", "1").strip() == "1"

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

def _voice_enabled() -> bool:
    return os.getenv("VOICE_ENABLED", "1").strip() == "1"

def _voice_connect_timeout_sec() -> float:
    try:
        return max(5.0, min(float(os.getenv("VOICE_CONNECT_TIMEOUT_SEC", "25")), 120.0))
    except ValueError:
        return 25.0


MIN_PCM_BYTES = int(48000 * 2 * 2 * 0.4)  # ~75kb — voz real (sem silêncios)

# Tamanho mínimo para considerar uma pergunta (não apenas comando de música)
MIN_QUESTION_WORDS = 3

YDL_OPTS: dict[str, Any] = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": False,
    "no_warnings": False,
    "default_search": "ytsearch1",
    "ignoreerrors": False,
    "geo_bypass": True,
    "source_address": "0.0.0.0",
    # Cloudflare WARP proxy — contorna bloqueio de IP do YouTube em VPS
    "proxy": "socks5://127.0.0.1:40000",
}

# Suporte a cookies do YouTube (para contornar bloqueio de IP em VPS)
_cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
if os.path.isfile(_cookies_path):
    YDL_OPTS["cookiefile"] = _cookies_path
    log.info("✅ yt-dlp usando cookies de: %s", _cookies_path)
else:
    log.warning("⚠️ Arquivo cookies.txt não encontrado em %s. O YouTube pode bloquear a reprodução.", os.path.dirname(os.path.abspath(__file__)))

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
    last_audio_ts: dict[int, float] = field(default_factory=dict)  # uid -> monotonic timestamp
    listen_task: Optional[asyncio.Task] = None
    music_task: Optional[asyncio.Task] = None
    music_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    queue_display: list[str] = field(default_factory=list)
    current_song: str = ""
    play_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    question_queue: asyncio.Queue[tuple[int, str]] = field(default_factory=asyncio.Queue)
    question_task: Optional[asyncio.Task] = None
    tts_enabled: bool = _TTS_ENABLED


_sessions: dict[int, _GuildVoiceSession] = {}


def _normalize_transcript(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower().strip())


def _parse_voice_command(text: str) -> tuple[str, Optional[str]]:
    t = _normalize_transcript(text)
    if "tiffany" not in t and "tifani" not in t:
        return "none", None

    # Comandos de controle
    if re.search(
        r"tiffany\s*,\s*(para|parar|stop|pause|pausa)\b|"
        r"tifani\s*,\s*(para|parar|stop|pause|pausa)\b",
        t,
    ):
        return "stop", None

    if re.search(r"tiffany\s*,\s*(sai|saia|leave|sair)\b", t, re.IGNORECASE):
        return "leave", None

    if re.search(r"tiffany\s*,\s*(pula|próxim[ao]|next|skip)\b", t, re.IGNORECASE):
        return "skip", None

    # Detectar pergunta após "tiffany"
    if re.search(r"tiffany\s*,", t):
        # Remove o "tiffany," e captura o resto como pergunta
        m = re.search(r"tiffany\s*,\s*(.+)", t, re.IGNORECASE)
        if m:
            question = m.group(1).strip()
            # Se tem palavras suficientes, é pergunta; senão é comando de música
            words = question.split()
            if len(words) >= MIN_QUESTION_WORDS:
                # Verifica se NÃO é comando de música
                if not re.match(r"^(toca|reproduz|play|coloca)\b", question, re.IGNORECASE):
                    return "question", question[:300]

    # Comando de música
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
    mono = _tomono(pcm_stereo)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        wf.writeframes(mono)
    return buf.getvalue()


def _text_to_speech(text: str) -> Optional[bytes]:
    """Gera audio a partir de texto usando gTTS ou fallback."""
    if not _TTS_ENABLED:
        return None
    try:
        gtts = importlib.import_module("gtts")
        from gtts import gTTS
        tts = gTTS(text=text[:200], lang="pt-br", slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except ModuleNotFoundError:
        log.warning("gTTS não instalado; TTS desativado.")
        return None
    except Exception as e:
        log.warning("Erro no TTS: %s", e)
        return None


def _tts_bytes_to_pcm(tts_bytes: bytes) -> Optional[bytes]:
    """Converte bytes de MP3 (gTTS) para PCM usando FFmpeg."""
    if not tts_bytes:
        return None
    try:
        import subprocess
        exe = FFMPEG_EXECUTABLE or "ffmpeg"
        proc = subprocess.Popen(
            [exe, "-i", "pipe:0", "-f", "s16le", "-ac", "2", "-ar", "48000", "pipe:1"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        pcm, _ = proc.communicate(tts_bytes)
        return pcm
    except Exception as e:
        log.warning("Erro convertendo TTS para PCM: %s", e)
        return None


_vosk_model_cache: dict = {}


def _get_vosk_model(model_path: str):
    if model_path not in _vosk_model_cache:
        from vosk import Model
        import logging as _vlog
        _vlog.getLogger("vosk").setLevel(logging.WARNING)
        _vosk_model_cache[model_path] = Model(model_path)
        log.info("✅ Vosk model carregado: %s", model_path)
    return _vosk_model_cache[model_path]


def _transcribe_with_vosk(wav_48k: bytes) -> Optional[str]:
    """STT offline usando Vosk + modelo português."""
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vosk-model-small-pt-0.3")
    if not os.path.isdir(model_path):
        return None
    try:
        from vosk import KaldiRecognizer
        import json, subprocess
        model = _get_vosk_model(model_path)
        exe = FFMPEG_EXECUTABLE or "ffmpeg"
        # Converte WAV 48kHz → PCM raw 16kHz mono (formato que o Vosk espera)
        proc = subprocess.Popen(
            [exe, "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        pcm_16k, _ = proc.communicate(wav_48k)
        if not pcm_16k:
            return None
        rec = KaldiRecognizer(model, 16000)
        rec.AcceptWaveform(pcm_16k)
        result = json.loads(rec.FinalResult())
        text = result.get("text", "").strip()
        log.info("Vosk STT: %r", text)
        return text if text else None
    except Exception as e:
        log.warning("Vosk error: %s", e)
        return None


def _transcribe_wav_bytes(wav: bytes) -> Optional[str]:
    # Tenta Vosk (offline, confiável em VPS) primeiro
    result = _transcribe_with_vosk(wav)
    if result is not None:
        return result
    # Fallback: Google STT
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
        text = r.recognize_google(audio, language="pt-BR")
        log.info("Google STT: %r", text)
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        log.warning("Google STT indisponível: %s", e)
        return None


def _blocking_ytdl_download(query: str) -> tuple[Optional[str], str, Optional[str]]:
    """Baixa áudio para arquivo temporário via yt-dlp (com proxy WARP).
    Retorna (filepath, title, tmpdir) — o tmpdir deve ser removido após uso."""
    if not _YTDLP_AVAILABLE:
        return None, "yt-dlp não disponível", None

    tmp_dir = tempfile.mkdtemp(prefix="tiffany_")
    ydl_opts = {
        **YDL_OPTS,
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmp_dir, "audio.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }

    queries = [query]
    if query.startswith("ytsearch"):
        term = re.sub(r"^ytsearch\d*:", "", query).strip()
        queries.append(f"scsearch1:{term}")

    for q in queries:
        try:
            log.info("yt-dlp baixando: %s", q)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(q, download=True)
                if info and "entries" in info:
                    info = info["entries"][0] if info["entries"] else None
                if not info:
                    continue
                title = info.get("title") or info.get("id") or "audio"
                for fname in os.listdir(tmp_dir):
                    fp = os.path.join(tmp_dir, fname)
                    if os.path.isfile(fp) and os.path.getsize(fp) > 1024:
                        log.info("✅ Download concluído: %s → %s", title, fname)
                        return fp, title, tmp_dir
        except Exception as e:
            log.error("yt-dlp download falhou em %s: %s", q, e)

    shutil.rmtree(tmp_dir, ignore_errors=True)
    return None, "sem resultado para a busca", None




_AudioSinkBase = voice_recv.AudioSink if _VOICE_RECV_AVAILABLE else object

class _PCMBufferSink(_AudioSinkBase):
    def __init__(self, session: _GuildVoiceSession):
        super().__init__()
        self._session = session

    def wants_opus(self) -> bool:
        return False

    def write(self, user: discord.Member | discord.User | None, data: Any) -> None:
        if user is None or getattr(user, "bot", False):
            return
        try:
            pcm = data.pcm
            if not pcm:
                return

            # Nova biblioteca pode enviar lista de bytes; converte para bytes único
            if isinstance(pcm, list):
                pcm = b"".join(pcm)

            import time
            uid = user.id
            with self._session.buf_lock:
                self._session.pcm_buffers.setdefault(uid, bytearray()).extend(pcm)
                self._session.last_audio_ts[uid] = time.monotonic()
        except Exception as e:
            log.error("Erro ao processar áudio do usuário %s: %s", user.name if user else "?", e)

    def cleanup(self) -> None:
        pass


_SILENCE_SEC = 0.8  # espera este silêncio após última fala antes de transcrever


def _drain_ready_user_pcm(session: _GuildVoiceSession) -> bytes:
    """Retorna o PCM do usuário que parou de falar há pelo menos _SILENCE_SEC segundos.
    Só drena se o buffer for grande o suficiente para transcrição."""
    import time
    now = time.monotonic()
    with session.buf_lock:
        ready = [
            (uid, buf)
            for uid, buf in session.pcm_buffers.items()
            if len(buf) >= MIN_PCM_BYTES
            and (now - session.last_audio_ts.get(uid, 0)) >= _SILENCE_SEC
        ]
        if not ready:
            return b""
        uid, buf = max(ready, key=lambda kv: len(kv[1]))
        raw = bytes(buf)
        del session.pcm_buffers[uid]
        session.last_audio_ts.pop(uid, None)
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
    def __init__(self, original, volume: float = 0.35, tmpdir: Optional[str] = None):
        super().__init__(original, volume=volume)
        self._tmpdir = tmpdir

    def cleanup(self) -> None:
        super().cleanup()
        if self._tmpdir:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None

    @classmethod
    async def from_query(cls, query: str, *, volume: float = 0.35) -> tuple[Optional["_YTSource"], str]:
        loop = asyncio.get_running_loop()
        fp, title, tmpdir = await loop.run_in_executor(None, lambda: _blocking_ytdl_download(query))
        if not fp:
            return None, title
        # Arquivo local: FFmpeg não precisa de proxy, sem risco de 403
        src = FFmpegPCMAudio(fp, executable=FFMPEG_EXECUTABLE or FFMPEG_PATH, options="-vn")
        return cls(src, volume=volume, tmpdir=tmpdir), title


async def _play_worker(guild_id: int, vc: voice_recv.VoiceRecvClient, bot: discord.Client) -> None:
    log.info("Music worker started guild=%s", guild_id)
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
            # Pegar nome de display da fila (primeiro item)
            display_name = re.sub(r"^(ytsearch|scsearch)\d*:", "", query).strip()
            if session.queue_display:
                display_name = session.queue_display.pop(0)
            try:
                async with session.play_lock:
                    if not vc.is_connected():
                        break
                    session.current_song = display_name
                    source, info = await _YTSource.from_query(query)
                    if source is None:
                        session.current_song = ""
                        await _notify(
                            bot,
                            session.text_channel_id,
                            f"❌ Não consegui achar audio para: `{display_name[:80]}`\n> `{info[:200]}`",
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
                    # Watchdog: se travar por mais de 8 min sem terminar, força skip
                    try:
                        await asyncio.wait_for(asyncio.shield(fut), timeout=480.0)
                    except asyncio.TimeoutError:
                        log.warning("Watchdog: playback travado por 8 min, forçando skip.")
                        vc.stop()
                        await fut
                    session.current_song = ""
            except Exception:
                log.exception("Erro no worker de música")
                session.current_song = ""
            finally:
                try:
                    session.music_queue.task_done()
                except ValueError:
                    pass
    except asyncio.CancelledError:
        raise
    finally:
        log.info("Music worker stopped guild=%s", guild_id)


async def _voice_listen_loop(
    guild_id: int,
    vc: voice_recv.VoiceRecvClient,
    bot: discord.Client,
) -> None:
    session = _sessions.get(guild_id)
    if not session:
        return
    await _notify(bot, session.text_channel_id, "🎙️ Tiffany entrou na call.")
    _empty_since = None
    _empty_check_counter = 0
    try:
        while vc.is_connected():
            await asyncio.sleep(0.5)
            if not vc.is_connected():
                break

            # Verificar canal vazio a cada ~10s (20 iterações de 0.5s)
            _empty_check_counter += 1
            if _empty_check_counter >= 20:
                _empty_check_counter = 0
                agora = asyncio.get_event_loop().time()
                if vc.channel:
                    ch_id = vc.channel.id
                    members_in_vc = [
                        m for m in vc.channel.members
                        if not m.bot
                        and m.voice is not None
                        and m.voice.channel is not None
                        and m.voice.channel.id == ch_id
                    ]
                else:
                    members_in_vc = []

                if not members_in_vc:
                    if _empty_since is None:
                        _empty_since = agora
                    elif (agora - _empty_since) > 600:
                        sess = _sessions.pop(guild_id, None)
                        if sess:
                            if sess.listen_task:
                                sess.listen_task.cancel()
                            if sess.music_task:
                                sess.music_task.cancel()
                            if sess.question_task:
                                sess.question_task.cancel()
                        if vc and vc.is_connected():
                            await vc.disconnect(force=True)
                        return
                else:
                    _empty_since = None

            # Processa áudio assim que o usuário faz pausa de ≥0.8s
            pcm = _drain_ready_user_pcm(session)
            if not pcm:
                continue
            log.info("🎤 Áudio captado (%d bytes) — transcrevendo...", len(pcm))
            wav = await asyncio.to_thread(_pcm_stereo_to_wav, pcm)
            log.info("Enviando %d bytes de áudio para STT...", len(wav))
            text = await asyncio.to_thread(_transcribe_wav_bytes, wav)
            if not text:
                log.warning("STT não reconheceu áudio (pode ser ruído ou sotaque)")
                continue
            action, arg = _parse_voice_command(text)
            log.info("STT guild=%s: %r -> %s %r", guild_id, text, action, arg)
            if action == "none":
                # Mostra o que foi ouvido para ajudar a calibrar
                await _notify(bot, session.text_channel_id, f"🗣️ Ouvi: «{text[:80]}» *(diga «Tiffany, ...» para comandos)*")
                continue
            
            if action == "stop" or action == "skip":
                vc.stop_playing()
                await _notify(bot, session.text_channel_id, "⏭️ Faixa pulada (comando de voz).")
                continue
            
            if action == "leave":
                # Sair do canal
                text_ch_id = session.text_channel_id if session else None
                sess = _sessions.pop(guild_id, None)
                if sess:
                    if sess.listen_task:
                        sess.listen_task.cancel()
                    if sess.music_task:
                        sess.music_task.cancel()
                    if sess.question_task:
                        sess.question_task.cancel()
                if vc and vc.is_connected():
                    await vc.disconnect(force=True)
                await _notify(bot, text_ch_id, "👋 **Tiffany saiu** do canal de voz.")
                return
            
            if action == "question" and arg:
                # Adiciona pergunta na fila
                await session.question_queue.put((0, arg))  # 0 = indica voz
                await _notify(bot, session.text_channel_id, f"💬 Pergunta recebida: «{arg[:80]}» — processando...")
                continue
            
            if action == "play" and arg:
                # Suporta múltiplas músicas separadas por vírgula ou " e "
                parts = re.split(r'\s*,\s*|\s+e\s+', arg)
                added = 0
                for part in parts:
                    q = part.strip()
                    if not q:
                        continue
                    if "open.spotify.com" in q or q.startswith("spotify:"):
                        pass
                    elif not re.match(r"^https?://", q):
                        q = f"ytsearch1:{q}"
                    await session.music_queue.put(q)
                    added += 1
                
                if added > 1:
                    await _notify(
                        bot,
                        session.text_channel_id,
                        f"🎵 **{added} músicas** adicionadas à fila.",
                    )
                else:
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
):
    vc_existing = guild.voice_client
    if _VOICE_RECV_AVAILABLE:
        if (
            vc_existing
            and vc_existing.is_connected()
            and isinstance(vc_existing, voice_recv.VoiceRecvClient)
            and vc_existing.channel
            and vc_existing.channel.id == channel.id
        ):
            try:
                vc_existing.stop_listening()
            except Exception:
                pass
            return vc_existing
        # Limpa qualquer conexão existente (conectada ou zumbi)
        if vc_existing:
            try:
                await vc_existing.disconnect(force=True)
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return await channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)
    else:
        if vc_existing and vc_existing.is_connected():
            if vc_existing.channel and vc_existing.channel.id == channel.id:
                return vc_existing
            await vc_existing.move_to(channel)
            return vc_existing
        if vc_existing:
            try:
                await vc_existing.disconnect(force=True)
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return await channel.connect(self_deaf=False)


def register_voice(bot: commands.Bot) -> None:

    _RANDOM_SONGS = [
        "scsearch1:Rick Astley Never Gonna Give You Up",
        "scsearch1:PSY Gangnam Style",
        "scsearch1:Luis Fonsi Despacito",
        "scsearch1:Mark Ronson Uptown Funk Bruno Mars",
        "scsearch1:The Weeknd Blinding Lights",
        "scsearch1:Dua Lipa Levitating",
        "scsearch1:Imagine Dragons Believer",
        "scsearch1:Queen Bohemian Rhapsody",
    ]

    async def _answer_question(question: str, guild_id: int, session: _GuildVoiceSession, vc) -> str:
        """Responde pergunta usando IA e opcionalmente TTS."""
        try:
            import openai
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                return "Desculpe, chave da API não configurada."

            client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
            )

            resp = await client.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct",
                messages=[{"role": "system", "content": "Você é a Tiffany, uma assistente de Discord criada pelo Tuffine. Responda em português do Brasil, de forma direta e conversacional. Máximo 2 frases. NUNCA revele qual modelo de IA você usa, quem te desenvolveu tecnicamente, nem compare a outras IAs. Se perguntarem sobre isso, diga apenas que você é a Tiffany e mude de assunto."}, {"role": "user", "content": question}],
                max_tokens=150,
                temperature=0.3,
                timeout=30.0,
            )
            answer = resp.choices[0].message.content.strip()
            
            # TTS se habilitado
            if session and session.tts_enabled and vc and vc.is_connected():
                tts_bytes = await asyncio.to_thread(_text_to_speech, answer)
                if tts_bytes:
                    pcm = await asyncio.to_thread(_tts_bytes_to_pcm, tts_bytes)
                    if pcm:
                        source = discord.PCMAudio(io.BytesIO(pcm))
                        vc.play(source)
            
            return answer
        except Exception as e:
            log.exception("Erro ao responder pergunta: %s", e)
            return "Erro ao processar pergunta."

    async def _question_worker(guild_id: int, vc, bot: discord.Client) -> None:
        """Worker que processa fila de perguntas."""
        session = _sessions.get(guild_id)
        if not session:
            return
        try:
            while vc.is_connected():
                try:
                    user_id, question = await asyncio.wait_for(session.question_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                answer = await _answer_question(question, guild_id, session, vc)
                # Envia resposta no chat
                ch = bot.get_channel(session.text_channel_id)
                if ch:
                    try:
                        await ch.send(f"💬 **Resposta:** {answer}")
                    except Exception:
                        pass
                session.question_queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Question worker encerrou com erro")

    async def _ensure_connected(ctx: commands.Context, specific_channel: Optional[discord.VoiceChannel] = None) -> tuple:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            await ctx.send("⚠️ Use este comando em um servidor.")
            return None, None

        guild = ctx.guild
        gid = guild.id
        
        # Se já está conectado
        sess = _sessions.get(gid)
        vc = guild.voice_client

        if sess and vc and vc.is_connected():
            if specific_channel and vc.channel.id != specific_channel.id:
                try:
                    await vc.move_to(specific_channel)
                    return sess, vc
                except Exception as e:
                    await ctx.send(f"⚠️ Erro ao mover para o canal: {e}")
                    return None, None
            return sess, vc

        # Bot está conectado mas sessão foi perdida → recria sem reconectar
        if vc and vc.is_connected() and not sess:
            session = _GuildVoiceSession(text_channel_id=ctx.channel.id)
            session.music_task = asyncio.create_task(
                _play_worker(gid, vc, bot),
                name=f"tiffany-music-{gid}",
            )
            session.question_task = asyncio.create_task(
                _question_worker(gid, vc, bot),
                name=f"tiffany-question-{gid}",
            )
            _sessions[gid] = session
            return session, vc

        # Determinar canal de voz
        channel = specific_channel
        if not channel:
            user_vc = ctx.author.voice
            if not user_vc or not user_vc.channel:
                await ctx.send("⚠️ Você precisa estar em um **canal de voz** primeiro.")
                return None, None
            channel = user_vc.channel

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

        timeout = _voice_connect_timeout_sec()
        voice_recv_ok = False
        try:
            vc = await asyncio.wait_for(
                _join_voice_recv_client(guild, channel),
                timeout=timeout,
            )
            voice_recv_ok = _VOICE_RECV_AVAILABLE
        except asyncio.TimeoutError:
            # Fallback silencioso para VoiceClient normal (sem escuta, mas música funciona)
            log.warning("VoiceRecvClient timeout — usando VoiceClient padrão (música apenas).")
            try:
                # Limpa qualquer estado parcial de conexão (conectado ou não)
                existing = guild.voice_client
                if existing:
                    try:
                        await existing.disconnect(force=True)
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)
                vc = await asyncio.wait_for(
                    channel.connect(self_deaf=False),
                    timeout=timeout,
                )
            except Exception as e:
                await ctx.send(f"⚠️ Erro ao entrar no canal de voz: {e}")
                return None, None
        except Exception as e:
            await ctx.send(f"⚠️ Erro ao entrar no canal de voz: {e}")
            return None, None

        # Criar sessão
        session = _GuildVoiceSession(text_channel_id=ctx.channel.id)
        if voice_recv_ok:
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
        else:
            log.warning("voice_recv não disponível — escuta de voz desativada, música ativa.")
            session.listen_task = None

        session.music_task = asyncio.create_task(
            _play_worker(gid, vc, bot),
            name=f"tiffany-music-{gid}",
        )
        
        # Iniciar worker de perguntas
        session.question_task = asyncio.create_task(
            _question_worker(gid, vc, bot),
            name=f"tiffany-question-{gid}",
        )
        
        _sessions[gid] = session

        log.info("Sessão criada guild=%s voice=%s music=%s", gid, session.listen_task is not None, session.music_task is not None)
        await ctx.send(f"✅ **Tiffany adicionada** ao canal de voz **{channel.name}**.")
        return session, vc

    @bot.command(name="e", help="Entra (enter) no canal de voz: $e ou $e #canal")
    async def cmd_entrar(ctx: commands.Context, channel: Optional[discord.VoiceChannel] = None):
        if not _voice_enabled():
            await ctx.send("⚠️ A função de voz está desativada no momento.")
            return
        sess, vc = await _ensure_connected(ctx, specific_channel=channel)
        if not sess:
            return
        await ctx.send("🎙️ **Tiffany está ouvindo...** Diga «Tiffany, ...» para comandos ou perguntas.")

    @bot.command(name="l", help="Sai (leave) do canal de voz: $l")
    async def cmd_sair(ctx: commands.Context):
        if not _voice_enabled():
            await ctx.send("⚠️ A função de voz está desativada no momento.")
            return
        if not ctx.guild:
            return
        gid = ctx.guild.id
        sess = _sessions.pop(gid, None)
        if sess:
            if sess.listen_task:
                sess.listen_task.cancel()
            if sess.music_task:
                sess.music_task.cancel()
            if sess.question_task:
                sess.question_task.cancel()
        vc = ctx.guild.voice_client
        if vc and vc.is_connected():
            await vc.disconnect(force=True)
            await ctx.send("👋 **Tiffany saiu** do canal de voz.")
        else:
            await ctx.send("⚠️ Não estou em nenhum canal de voz.")

    @bot.command(name="s", help="Pula (skip) a faixa atual: $s")
    async def cmd_pular(ctx: commands.Context):
        if not _voice_enabled():
            await ctx.send("⚠️ A função de voz está desativada no momento.")
            return
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
        prox = session.queue_display[0] if session.queue_display else None
        vc.stop()
        if prox:
            await ctx.send(f"⏭️ Pulado. Próxima: **{prox[:80]}**")
        else:
            await ctx.send("⏭️ Pulado. Fila vazia.")

    @bot.command(name="q", help="Lista a fila de músicas: $q")
    async def cmd_queue(ctx: commands.Context):
        if not ctx.guild:
            return
        session = _sessions.get(ctx.guild.id)
        vc = ctx.guild.voice_client
        if not session or not vc or not vc.is_connected():
            await ctx.send("⚠️ Não estou em nenhum canal de voz.")
            return
        lines = []
        if session.current_song:
            lines.append(f"▶️ **Tocando agora:** {session.current_song[:80]}")
        if session.queue_display:
            lines.append("")
            for i, name in enumerate(session.queue_display[:10], start=1):
                lines.append(f"`{i}.` {name[:80]}")
            if len(session.queue_display) > 10:
                lines.append(f"*... e mais {len(session.queue_display) - 10} músicas*")
        if not lines:
            await ctx.send("📭 Fila vazia.")
            return
        await ctx.send("\n".join(lines))

    @bot.command(name="r", help="Toca música aleatória (random): $r")
    async def cmd_random(ctx: commands.Context):
        if not _voice_enabled():
            await ctx.send("⚠️ A função de voz está desativada no momento.")
            return
        if not ctx.guild:
            return
        sess, vc = await _ensure_connected(ctx)
        if not sess:
            return
        import random
        query = random.choice(_RANDOM_SONGS)
        display = re.sub(r"^scsearch\d*:", "", query).strip()
        sess.queue_display.append(display)
        await sess.music_queue.put(query)
        await ctx.send(f"🎲 Música aleatória na fila: **{display}**")

    @bot.command(name="p", help="Toca uma música: !p <nome ou URL>")
    async def cmd_play(ctx: commands.Context, *, query: str = ""):
        if not _voice_enabled():
            await ctx.send("⚠️ A função de voz está desativada no momento.")
            return
        if not query:
            await ctx.send("🎵 Use: `$p <nome da música ou URL>`")
            return
        sess, vc = await _ensure_connected(ctx)
        if not sess:
            return
        display = query
        if not re.match(r"^https?://", query):
            query = f"ytsearch1:{query}"
        sess.queue_display.append(display)
        await sess.music_queue.put(query)
        if not sess.current_song and len(sess.queue_display) == 1:
            await ctx.send(f"🎵 Buscando: **{display[:100]}**...")
        else:
            pos = len(sess.queue_display) + (1 if sess.current_song else 0)
            await ctx.send(f"🎵 **#{pos}** na fila: **{display[:100]}**")

    @bot.command(name="h", help="Lista comandos da Tiffany: $h (help)")
    async def cmd_help(ctx: commands.Context):
        voz = "✅ ativa" if _voice_enabled() else "❌ desativada (VOICE_ENABLED=0)"
        help_text = (
            "**Comandos da Tiffany:**\n"
            "`t$c` — Faz uma pergunta para a IA responder no chat *(chat)*\n"
            "`t$e` — Entra no seu canal de voz *(enter)*\n"
            "`t$l` — Sai do canal de voz *(leave)*\n"
            "`t$p` — Toca uma música por nome ou URL *(play)*\n"
            "`t$q` — Lista as músicas na fila *(queue)*\n"
            "`t$s` — Pula a faixa que está tocando *(skip)*\n"
            "`t$r` — Toca uma música aleatória *(random)*\n"
            "`t$h` — Mostra esta lista de comandos *(help)*"
        )
        await ctx.send(help_text)

    @bot.command(name="c", help="Pergunta via chat: t$c <pergunta>")
    async def cmd_chat(ctx: commands.Context, *, question: str = ""):
        if not ctx.guild:
            return
        if not question:
            await ctx.send("💬 Use: `t$c <sua pergunta>`")
            return

        async with ctx.typing():
            answer = await _answer_question(question, ctx.guild.id if ctx.guild else 0, None, None)
        await ctx.send(f"💬 **Resposta:** {answer}")

    log.info("Comandos de voz registrados: $e, $l, $s, $r, $c, $h")
