"""L1 regex rules — synchronous, zero network."""

from __future__ import annotations

import re

SCAM_RE = re.compile(
    r"(?i)"
    r"(discord(?:app)?\.(?:com|gift)|discord-nitro|free\s+nitro|steamcommun[il]ty|"
    r"steamcornmunity|st[e3]am\s*gift|airdrop\s+crypto|binance\s+giveaway|"
    r"claim\s+your\s+nitro|@everyone\s+free|nitro\s+for\s+free|"
    r"discord\.gg/[a-z0-9]{8,}.*nitro|"
    r"onlyfans\s+leak|onlyfans\s+free|"
    r"cp\s+link|child\s+porn|"
    r"send\s+nudes|pack\s+vip\s+gr[aá]tis)"
)

INVITE_SPAM_RE = re.compile(
    r"(?i)(discord(?:\.gg|app\.com/invite)/[a-z0-9-]{2,})"
)

NSFW_HEURISTIC_RE = re.compile(
    r"(?i)\b(porn|xxx|hentai|nude|nudes|onlyfans|nsfw|18\+|\+18|sexo\s+explicito)\b"
)

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


def extract_urls(content: str) -> list[str]:
    return URL_RE.findall(content or "")


def l1_scam_match(content: str) -> bool:
    return bool(SCAM_RE.search(content or ""))


def l1_nsfw_match(content: str) -> bool:
    return bool(NSFW_HEURISTIC_RE.search(content or ""))


def l1_invite_spam(content: str) -> bool:
    return len(INVITE_SPAM_RE.findall(content or "")) >= 2


def l1_caps_spam(content: str) -> bool:
    if not content or len(content) < 20:
        return False
    caps = sum(1 for c in content if c.isupper())
    return caps / max(len(content), 1) > 0.7


def needs_ai_scan(content: str) -> bool:
    if not content or len(content.strip()) < 8:
        return False
    if l1_scam_match(content) or l1_invite_spam(content) or l1_nsfw_match(content):
        return True
    return l1_caps_spam(content)
