#!/usr/bin/env python3
"""Print slash commands used in Playing status rotation (local check, no token needed)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DISCORD_TOKEN", "verify-placeholder")
os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("CANAL_NOTICIAS_ID", "0")
os.environ.setdefault("ID_CARGO_PARA_MARCAR", "0")
os.environ.setdefault("GUILD_ID", "0")


def main() -> int:
    import notices  # noqa: WPS433
    import tiffany_voice as tv

    tv.register_voice(notices.discord_client)
    # giveaway/embed load at on_ready on VPS — include in count like production.
    _COG_SLASH = ("giveaway", "embed")
    lines = tv.presence_lines_for(notices.discord_client)
    existing = {line.lstrip("/") for line in lines}
    extra = tuple(f"/{n}" for n in _COG_SLASH if n not in existing)
    lines = lines + extra
    sec = tv.PRESENCE_ROTATE_SEC
    total = len(lines) * sec

    print("=== Tiffany — verificação do status Playing ===\n")
    print(f"Intervalo: {sec}s por comando")
    print(f"Comandos na rotação: {len(lines)}")
    print(f"Ciclo completo: ~{total // 60}m {total % 60}s\n")
    print("Sequência (ordem alfabética):\n")
    for i, line in enumerate(lines, 1):
        print(f"  {i:2}. Jogando {line}")
    print("\nComo verificar no Discord:")
    print("  1. Abra o perfil da Tiffany no servidor (clique no nome/avatar).")
    print("  2. Veja «Jogando …» — deve mostrar /about, /play, etc.")
    print(f"  3. Aguarde {sec}s — o comando muda para o próximo da lista.")
    print("  4. Confira GitHub Actions se o deploy mais recente passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
