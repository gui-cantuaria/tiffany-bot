import subprocess
import time
import sys
import os
import signal
import urllib.request

# Force UTF-8 output to prevent crashes on Windows console when printing emojis
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# --- LOCKFILE: ensure only one instance runs ---
_lock_fd = None
if sys.platform != "win32":
    import fcntl
    _LOCKFILE = "/tmp/tiffany_launcher.lock"
    _lock_fd = open(_LOCKFILE, "w")
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        _lock_fd.close()
        _lock_fd = None
        print("[LOCK] Another launcher instance is already running. Exiting duplicate.")
        sys.exit(1)

# --- SIGTERM: systemctl stop sends SIGTERM, treat like Ctrl+C ---
def _sigterm_handler(signum, frame):
    raise KeyboardInterrupt


if sys.platform != "win32":
    signal.signal(signal.SIGTERM, _sigterm_handler)


# --- BOT LIST ---
bots = [
    {"file": "notices.py", "name": "📰 Bot Notícias"},
    # offers.py now runs as a Cog inside notices.py (offers_cog.py)
]

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

processes = {}
_restart_times = {}  # name -> list of recent restart timestamps
_total_restarts = {}  # name -> total restarts since startup
MAX_RAPID_RESTARTS = 3  # max restarts within the window
RESTART_WINDOW = 60  # window in seconds
RESTART_COOLDOWN = 300  # cooldown after restart storm (5 min)
MAX_TOTAL_RESTARTS = 15  # circuit breaker: give up after N total restarts
_backoff_level = {}  # name -> current backoff multiplier
BACKOFF_BASE = 30  # initial backoff in seconds
BACKOFF_MAX = 300  # max backoff in seconds


def log(message: str) -> None:
    """Print a message with a timestamp."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"[{now}] {message}")


def webhook_notify(message: str) -> None:
    """Send a healthcheck notification via Discord webhook (PT-BR for admins)."""
    url = os.environ.get("DISCORD_WEBHOOK_HEALTHCHECK")
    if not url:
        return
    try:
        data = json.dumps({"content": f"🤖 **Tiffany Healthcheck**\n{message}"}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"Healthcheck webhook failed: {e}")


MAX_LOG_SIZE = 5 * 1024 * 1024  # 5MB per log file


def _truncate_log_if_large(log_path: str) -> None:
    """Truncate log file if it exceeds MAX_LOG_SIZE, keeping the tail."""
    try:
        if os.path.exists(log_path) and os.path.getsize(log_path) > MAX_LOG_SIZE:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(max(0, os.path.getsize(log_path) - MAX_LOG_SIZE // 2))
                f.readline()  # discard partial line
                content = f.read()
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"--- Log truncated at {datetime.now().isoformat()} ---\n")
                f.write(content)
    except Exception as e:
        log.warning(f"Log file operation failed: {e}")


def _read_crash_tail(bot_config: dict, lines: int = 15) -> str:
    """Read the last N lines of a bot's log to include crash context."""
    try:
        base_name = os.path.splitext(bot_config["file"])[0]
        log_path = os.path.join(LOG_DIR, f"{base_name}.log")
        if not os.path.exists(log_path):
            return "(no log file)"
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            tail = all_lines[-lines:] if len(all_lines) >= lines else all_lines
            return "".join(tail).strip()[-500:]  # cap at 500 chars for webhook
    except Exception as e:
        log.warning(f"Log file operation failed: {e}")
        return "(failed to read log)"


def start_bot(bot_config: dict):
    """Start a bot subprocess and capture stdout/stderr to a log file."""
    log(f"👉 Starting {bot_config['name']}...")
    base_name = os.path.splitext(bot_config["file"])[0]
    log_path = os.path.join(LOG_DIR, f"{base_name}.log")
    _truncate_log_if_large(log_path)
    log_file = open(log_path, "a", encoding="utf-8")
    log_file.write(f"\n--- Started at {datetime.now().isoformat()} ---\n")
    log_file.flush()
    try:
        popen_kw: dict = {
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
            "env": {**os.environ, "PYTHONIOENCODING": "utf-8"},
        }
        if sys.platform != "win32":
            popen_kw["start_new_session"] = True
        proc = subprocess.Popen(
            [sys.executable, "-u", bot_config["file"]],
            **popen_kw,
        )
    except Exception as e:
        log_file.close()
        raise RuntimeError(f"Failed to start {bot_config['name']}: {e}") from e
    return proc, log_file


def main() -> None:
    log("🚀 Starting Tiffany system...")

    # Start all bots for the first time
    for bot in bots:
        proc, log_file = start_bot(bot)
        processes[bot["name"]] = {"process": proc, "log_file": log_file, "config": bot}

    log("✅ Bots active! Monitoring crashes (watchdog enabled)...")
    webhook_notify(f"✅ Sistema iniciado com {len(bots)} bot(s)")

    try:
        while True:
            # Health check every 10 seconds
            time.sleep(10)

            for name, data in list(processes.items()):
                p = data["process"]
                bot_config = data["config"]

                # poll() != None means the process exited
                if p.poll() is not None:
                    crash_tail = _read_crash_tail(bot_config)
                    log(f"⚠️ ALERT: {name} crashed (exit code: {p.returncode})!")
                    log(f"📋 Last log lines:\n{crash_tail}")
                    webhook_notify(
                        f"⚠️ {name} caiu (exit code: {p.returncode})!\n"
                        f"```\n{crash_tail[:400]}\n```"
                    )
                    # Circuit breaker: give up if too many total crashes
                    _total_restarts[name] = _total_restarts.get(name, 0) + 1
                    if _total_restarts[name] >= MAX_TOTAL_RESTARTS:
                        log(f"💀 {name} crashed {MAX_TOTAL_RESTARTS}x total! Giving up permanently.")
                        webhook_notify(f"💀 {name} desativado — crashou {MAX_TOTAL_RESTARTS}x. Requer restart manual.")
                        continue
                    # Anti restart-storm with exponential backoff
                    now = time.time()
                    if name not in _restart_times:
                        _restart_times[name] = []
                    _restart_times[name].append(now)
                    _restart_times[name] = [t for t in _restart_times[name] if now - t < RESTART_WINDOW]
                    if len(_restart_times[name]) >= MAX_RAPID_RESTARTS:
                        level = _backoff_level.get(name, 0)
                        wait = min(BACKOFF_BASE * (2 ** level), BACKOFF_MAX)
                        _backoff_level[name] = level + 1
                        log(f"🚨 {name} crashed {MAX_RAPID_RESTARTS}x in {RESTART_WINDOW}s! Backoff: {wait}s (level {level + 1})...")
                        webhook_notify(f"🚨 {name} em restart storm! Backoff de {wait}s.")
                        time.sleep(wait)
                        _restart_times[name].clear()
                    else:
                        # Reset backoff on stable restart
                        _backoff_level[name] = 0
                    if data.get("log_file"):
                        data["log_file"].close()
                    log(f"🔄 Restarting {name}...")
                    try:
                        proc, log_file = start_bot(bot_config)
                        processes[name]["process"] = proc
                        processes[name]["log_file"] = log_file
                    except Exception as e:
                        log(f"💀 Failed to restart {name}: {e}")
                        webhook_notify(f"💀 Falha ao reiniciar {name}: {e}")

    except KeyboardInterrupt:
        log("🛑 Stop command received. Shutting down bots...")
        webhook_notify("🛑 Sistema encerrado manualmente.")
        for name, data in processes.items():
            # Graceful: SIGINT to process group first (allows discord.py + child ffmpeg cleanup)
            try:
                if sys.platform != "win32":
                    os.killpg(os.getpgid(data["process"].pid), signal.SIGINT)
                else:
                    data["process"].terminate()
            except OSError:
                pass
            try:
                data["process"].wait(timeout=10)
            except subprocess.TimeoutExpired:
                log(f"⚠️ {name} did not exit after SIGINT (10s), sending SIGTERM...")
                try:
                    if sys.platform != "win32":
                        os.killpg(os.getpgid(data["process"].pid), signal.SIGTERM)
                    else:
                        data["process"].terminate()
                except OSError:
                    pass
                try:
                    data["process"].wait(timeout=10)
                except subprocess.TimeoutExpired:
                    log(f"⚠️ {name} did not exit after SIGTERM (10s), forcing SIGKILL...")
                    try:
                        if sys.platform != "win32":
                            os.killpg(os.getpgid(data["process"].pid), signal.SIGKILL)
                        else:
                            data["process"].kill()
                    except OSError:
                        pass
                    data["process"].wait(timeout=5)
            if data.get("log_file"):
                data["log_file"].close()
            log(f"💤 {name} shut down successfully.")

        log("👋 Tiffany system shut down safely.")
    finally:
        if _lock_fd:
            try:
                if sys.platform != "win32":
                    import fcntl
                    fcntl.flock(_lock_fd, fcntl.LOCK_UN)
                _lock_fd.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
