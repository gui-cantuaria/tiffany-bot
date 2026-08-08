"""Parse LAVALINK_NODES JSON or fall back to LAVALINK_HOST/PORT for wavelink.Pool."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger("tiffany-bot")

try:
    import wavelink
except ImportError:
    wavelink = None  # type: ignore


def lavalink_enabled() -> bool:
    return os.getenv("LAVALINK_ENABLED", "0").strip() == "1"


def _default_password() -> str:
    pwd = os.getenv("LAVALINK_PASSWORD", "").strip()
    if not pwd and lavalink_enabled():
        log.warning("LAVALINK_PASSWORD is unset while LAVALINK_ENABLED=1. Secure configuration required.")
    return pwd


def build_wavelink_nodes() -> list[Any]:
    """Build wavelink.Node list for Pool.connect (supports cluster via LAVALINK_NODES)."""
    if wavelink is None:
        return []

    raw = os.getenv("LAVALINK_NODES", "").strip()
    if raw:
        try:
            configs = json.loads(raw)
            if not isinstance(configs, list) or not configs:
                raise ValueError("LAVALINK_NODES must be a non-empty JSON array")
            nodes: list[Any] = []
            for i, cfg in enumerate(configs):
                if not isinstance(cfg, dict):
                    continue
                uri = cfg.get("uri") or cfg.get("url")
                password = cfg.get("password") or _default_password()
                ident = cfg.get("identifier") or cfg.get("id") or f"node-{i}"
                if not uri:
                    log.warning("LAVALINK_NODES[%d] missing uri — skipped", i)
                    continue
                nodes.append(
                    wavelink.Node(
                        uri=str(uri),
                        password=str(password),
                        identifier=str(ident),
                    )
                )
            if nodes:
                log.info("Lavalink cluster: %d node(s) from LAVALINK_NODES", len(nodes))
                return nodes
        except Exception as e:
            log.warning("Invalid LAVALINK_NODES (%s) — using single-node fallback", e)

    host = os.getenv("LAVALINK_HOST", "127.0.0.1")
    port = int(os.getenv("LAVALINK_PORT", "2333"))
    ident = os.getenv("LAVALINK_NODE_ID", "primary")
    return [
        wavelink.Node(
            uri=f"http://{host}:{port}",
            password=_default_password(),
            identifier=ident,
        )
    ]
