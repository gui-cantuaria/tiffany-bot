#!/usr/bin/env python3
"""List slash commands and flag interaction_check paths that may timeout Discord."""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Minimal env so imports succeed without a real bot token.
os.environ.setdefault("DISCORD_TOKEN", "audit-placeholder")
os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("CANAL_NOTICIAS_ID", "0")
os.environ.setdefault("ID_CARGO_PARA_MARCAR", "0")
os.environ.setdefault("GUILD_ID", "0")


def _collect_tree_commands() -> list[tuple[str, str]]:
    import notices  # noqa: WPS433

    try:
        import tiffany_voice

        tiffany_voice.register_voice(notices.discord_client)
    except Exception as exc:
        print(f"WARN: register_voice failed: {exc}")

    rows: list[tuple[str, str]] = []
    for cmd in notices.discord_client.tree.get_commands():
        rows.append((cmd.name, type(cmd).__name__))
    rows.sort(key=lambda r: r[0].lower())
    return rows


def _audit_slash_rate_limit_check() -> list[str]:
    path = ROOT / "tiffany_voice.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    issues: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "slash_rate_limit_check":
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.If):
                continue
            responds = any(
                isinstance(child, ast.Await)
                and isinstance(getattr(child, "value", None), ast.Call)
                and isinstance(getattr(getattr(child.value, "func", None), "attr", None), str)
                and child.value.func.attr in ("send_message", "send")
                for child in ast.walk(stmt)
            )
            returns_false = any(
                isinstance(child, ast.Return)
                and isinstance(child.value, ast.Constant)
                and child.value.value is False
                for child in ast.walk(stmt)
            )
            if returns_false and not responds:
                issues.append(
                    "slash_rate_limit_check branch returns False without responding "
                    "(causes Discord 'The application did not respond')."
                )
        break
    return issues


def main() -> int:
    print("=== Tiffany Bot — slash command audit ===\n")

    commands = _collect_tree_commands()
    names = [name for name, _ in commands]
    print(f"Registered slash commands ({len(commands)}):")
    for name, kind in commands:
        print(f"  /{name}  ({kind})")

    print()
    if "status" in names:
        print("FAIL: /status still registered globally — should be prefix-only (t!status).")
    else:
        print("OK: /status is not in the slash tree.")

    if "stats" in names:
        print("OK: /stats is registered (public health).")
    else:
        print("FAIL: /stats missing from slash tree.")

    print()
    static_issues = _audit_slash_rate_limit_check()
    if static_issues:
        print("Static check issues:")
        for item in static_issues:
            print(f"  - {item}")
    else:
        print("OK: slash_rate_limit_check has no bare `return False` without response path.")

    print()
    print("Notes:")
    print("  - interaction_check returning False without interaction.response causes Discord timeout.")
    print("  - notices._TiffanyCommandTree responds on blacklist before rate limit.")
    print("  - tree.error handler lives in notices.py (fallback if voice module fails).")

    failed = ("status" in names) or ("stats" not in names) or bool(static_issues)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
