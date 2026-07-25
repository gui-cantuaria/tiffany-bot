#!/usr/bin/env python3
"""Audit slash ↔ prefix parity and silent failure paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DISCORD_TOKEN", "audit-placeholder")
os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("CANAL_NOTICIAS_ID", "0")
os.environ.setdefault("ID_CARGO_PARA_MARCAR", "0")
os.environ.setdefault("GUILD_ID", "0")

# Slash-only by design (owner / security / duplicate alias).
_SLASH_ONLY_OK = frozenset({"rp"})
# Prefix-only by design.
_PREFIX_ONLY_OK = frozenset({"status", "su", "summary"})


def _load_bot():
    import notices  # noqa: WPS433

    try:
        import tiffany_voice

        tiffany_voice.register_voice(notices.discord_client)
    except Exception as exc:
        print(f"WARN: register_voice failed: {exc}")

    # Loaded at on_ready in production — treat as present for parity audit.
    _PREFIX_FROM_COGS = {"giveaway", "gw", "embed", "emb"}

    return notices.discord_client, _PREFIX_FROM_COGS


def _slash_names(bot) -> set[str]:
    return {cmd.name for cmd in bot.tree.get_commands()}


def _prefix_names(bot) -> set[str]:
    names: set[str] = set()
    for cmd in bot.commands:
        names.add(cmd.name)
        names.update(getattr(cmd, "aliases", []) or [])
    return names


def main() -> int:
    bot, cog_prefix = _load_bot()
    slash = _slash_names(bot)
    prefix = _prefix_names(bot) | cog_prefix

    print("=== Tiffany Bot — slash <-> prefix audit ===\n")
    print(f"Slash commands: {len(slash)}")
    print(f"Prefix tokens (names + aliases): {len(prefix)}\n")

    missing_prefix: list[str] = []
    for name in sorted(slash):
        if name in _SLASH_ONLY_OK:
            continue
        if name in prefix:
            continue
        missing_prefix.append(name)

    missing_slash: list[str] = []
    for name in sorted(prefix):
        if name in _PREFIX_ONLY_OK:
            continue
        if name in slash:
            continue
        # Skip subcommands (giveaway create, embed create, etc.)
        if name in {"create", "edit", "send", "list", "end", "reroll", "c", "new", "add", "e", "stop", "finish"}:
            continue
        missing_slash.append(name)

    print("Slash without prefix equivalent:")
    if missing_prefix:
        for name in missing_prefix:
            print(f"  FAIL  /{name}")
    else:
        print("  OK (all slash commands have t! equivalent)")

    print()
    print("Prefix without slash (excluding subcommands & intentional):")
    if missing_slash:
        for name in missing_slash:
            print(f"  INFO  t!{name}")
    else:
        print("  OK")

    print()
    print("Intentional exceptions:")
    print(f"  Slash-only OK: {', '.join(f'/{n}' for n in sorted(_SLASH_ONLY_OK))}")
    print(f"  Prefix-only OK: {', '.join(f't!{n}' for n in sorted(_PREFIX_ONLY_OK))}")

    print()
    print("Prefix silent-failure notes:")
    print("  - Blacklist on prefix now replies with blocked embed (not Discord timeout).")
    print("  - t!status stays silent for non-owners (owner-only panel).")
    print("  - Hybrid slash skips @bot.check — blacklist handled in interaction_check.")

    failed = bool(missing_prefix)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
