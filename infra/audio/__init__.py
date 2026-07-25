"""Lavalink cluster configuration — bot orchestrates, nodes stream."""

from infra.audio.lavalink_nodes import build_wavelink_nodes, lavalink_enabled

__all__ = ["build_wavelink_nodes", "lavalink_enabled"]
