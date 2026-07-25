"""Single source of truth for supported languages and global display order."""

from __future__ import annotations

# English first, then approximate worldwide speakers / international reach.
ALL_LANGS: tuple[str, ...] = (
    "en", "hi", "es", "ar", "fr", "pt", "ru", "de",
    "ja", "ko", "vi", "tr", "it", "uk", "nl", "sv",
)

CORE_LANGS: tuple[str, ...] = ("en", "es", "fr", "pt", "de")

DEFAULT_LANG = "en"

LANG_CODES_DISPLAY = " · ".join(code.upper() for code in ALL_LANGS)

ALL_LANGS_SET = frozenset(ALL_LANGS)
