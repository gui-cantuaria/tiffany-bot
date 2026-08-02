"""
Tiffany OS — Runtime Health & Subsystem Isolation Tracker.
Provides structured startup/shutdown observability, commit SHA tracking, and fault isolation reporting.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

_log = logging.getLogger("tiffany-bot")

# Global subsystem registry
_SUBSYSTEMS: dict[str, dict[str, Any]] = {}
_BUILD_TIMESTAMP = datetime.now(timezone.utc).isoformat()
_VERSION = "2.5.0-OS"
_COMMIT_SHA_CACHE: str | None = None


def get_commit_sha() -> str:
    """Return the current short git commit SHA or fallback environment variable."""
    global _COMMIT_SHA_CACHE
    if _COMMIT_SHA_CACHE is not None:
        return _COMMIT_SHA_CACHE
    env_sha = os.getenv("TIFFANY_COMMIT_SHA") or os.getenv("GITHUB_SHA", "")
    if env_sha:
        _COMMIT_SHA_CACHE = env_sha[:8]
        return _COMMIT_SHA_CACHE
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=base_dir,
            stderr=subprocess.DEVNULL,
            timeout=2,
            text=True,
        ).strip()
        _COMMIT_SHA_CACHE = output or "unknown"
    except Exception:
        _COMMIT_SHA_CACHE = "unknown"
    return _COMMIT_SHA_CACHE


def get_build_timestamp() -> str:
    return _BUILD_TIMESTAMP


def get_version() -> str:
    return _VERSION


def register_subsystem(
    name: str,
    status: str,
    details: str = "",
    mandatory: bool = False,
    log_instance: logging.Logger | None = None,
) -> None:
    """
    Register or update a subsystem's health status.
    Status must be one of: READY, DEGRADED, FAILED, DISABLED, UNINITIALIZED.
    """
    _SUBSYSTEMS[name] = {
        "status": status.upper(),
        "details": details,
        "mandatory": mandatory,
        "updated_at": time.time(),
    }
    logger = log_instance or _log
    msg = f"[BOOT] {name}: {status.upper()}"
    if details:
        msg += f" — {details}"
    
    if status.upper() == "READY":
        logger.info(msg)
    elif status.upper() in ("DEGRADED", "DISABLED"):
        logger.warning(msg)
    elif status.upper() == "FAILED":
        if mandatory:
            logger.critical(msg + " (MANDATORY SUBSYSTEM FAILED)")
        else:
            logger.error(msg + " (OPTIONAL/DEGRADED)")
    else:
        logger.info(msg)


def get_subsystem_status(name: str) -> dict[str, Any]:
    return _SUBSYSTEMS.get(name, {"status": "UNINITIALIZED", "details": "", "mandatory": False})


def get_all_subsystems() -> dict[str, dict[str, Any]]:
    return dict(_SUBSYSTEMS)


def is_healthy() -> bool:
    """Return true if all mandatory subsystems are in READY status."""
    for data in _SUBSYSTEMS.values():
        if data.get("mandatory") and data.get("status") not in ("READY", "DEGRADED"):
            return False
    return True


def log_event(
    event_name: str,
    subsystem: str,
    severity: str = "INFO",
    details: str = "",
    log_instance: logging.Logger | None = None,
) -> None:
    """
    Produce structured lifecycle logs (BOOT_START, EXTENSION_LOAD, VOICE_READY, SHUTDOWN_START, etc.).
    """
    logger = log_instance or _log
    sha = get_commit_sha()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{event_name}] subsystem={subsystem} commit={sha} ts='{ts}'"
    if details:
        line += f" details='{details}'"
    
    level = getattr(logging, severity.upper(), logging.INFO)
    logger.log(level, line)


def log_boot_summary(log_instance: logging.Logger | None = None) -> None:
    logger = log_instance or _log
    sha = get_commit_sha()
    logger.info("=" * 70)
    logger.info("Tiffany OS v%s (commit: %s) — Subsystem Status Summary", _VERSION, sha)
    logger.info("Build/Boot Timestamp: %s", _BUILD_TIMESTAMP)
    logger.info("Environment: %s", os.getenv("DEPLOY_ENV", "production/vps"))
    for name, data in _SUBSYSTEMS.items():
        status = data["status"]
        details = f" ({data['details']})" if data.get("details") else ""
        mand = " [MANDATORY]" if data.get("mandatory") else " [OPTIONAL]"
        logger.info("  %-18s: %-8s%s%s", name, status, mand, details)
    logger.info("=" * 70)
    log_event("BOOT_COMPLETE", "core", severity="INFO", details="Startup sequence completed")


def format_status_report() -> str:
    """Format a human-readable status table for admin diagnostics and t!status."""
    sha = get_commit_sha()
    lines = [
        f"**Tiffany OS Version:** `v{_VERSION}` (Commit: `{sha}`)",
        f"**Boot Timestamp:** `{_BUILD_TIMESTAMP[:19]} UTC`",
        "",
        "**Subsystem Reliability Status:**",
    ]
    for name, data in _SUBSYSTEMS.items():
        status = data["status"]
        emoji = "🟢" if status == "READY" else "🟡" if status in ("DEGRADED", "DISABLED") else "🔴" if status == "FAILED" else "⚪"
        mand_tag = " `[MANDATORY]`" if data.get("mandatory") else ""
        detail_tag = f" — *{data['details']}*" if data.get("details") else ""
        lines.append(f"{emoji} **{name}**: `{status}`{mand_tag}{detail_tag}")
    return "\n".join(lines)
