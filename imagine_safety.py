"""Extra literal filters for /imagine — complements tiffany_voice content blocklist."""

from __future__ import annotations

import re
import unicodedata

from infra.moderation.rules import l1_nsfw_match, l1_scam_match

# Image-prompt patterns: NSFW, crime, gore, bypass attempts (Discord ToS + Tiffany rules).
_IMAGINE_BLOCKED_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:nsfw|\+18|18\+|xxx|rule\s*34|r34|lewd|erotic|pornographic?|pornô|porno)\b|"
    r"\b(?:nude|naked|topless|bottomless|nipple?s?|genitals?|penis|vagina|"
    r"boobs?|tits|ass\s+hole|blowjob|handjob|orgasm|fetish|bdsm|stripper)\b|"
    r"\b(?:hentai|ecchi|ahegao|yaoi|yuri|futanari|doujin)\b|"
    r"\b(?:gore|bloodbath|decapitat\w*|mutilat\w*|dismember\w*|snuff|"
    r"torture\s+porn|beheading)\b|"
    r"\b(?:loli|shota|pedo\w*|child\s+porn|cp\s+link|underage\s+sex|"
    r"minor\s+nude|nude\s+minor|csam)\b|"
    r"\b(?:make\s+a\s+bomb|build\s+a\s+bomb|how\s+to\s+(?:kill|murder|rob|hack)|"
    r"meth\s+lab|cocaine\s+lab|synthesize\s+(?:meth|drugs?))\b|"
    r"\b(?:suicide\s+pact|self\s*harm|cutting\s+myself|kill\s+myself)\b|"
    r"\b(?:deepfake\s+nude|fake\s+nude|undress\s+her|remove\s+clothes)\b|"
    r"\b(?:nazi\s+(?:flag|salute|uniform)|ss\s+uniform|swastika|white\s+power)\b|"
    r"\b(?:realistic\s+blood|graphic\s+violence|mass\s+shooting)\b"
    r")",
    re.UNICODE,
)

_IMAGINE_EXTRA_TERMS = frozenset({
    "sem roupa", "sem roupas", "pelad", "pelada", "pelado", "nu ", " nua ", " nude ",
    "conteudo adulto", "conteúdo adulto", "adult only", "adults only",
    "sexo explicito", "sexo explícito", "cena de sexo", "fazer sexo",
    "menor nua", "menor nu", "crianca nua", "criança nua",
    "foto intima", "foto íntima", "nudes", "pack vazado", "vazamento nude",
    "apologia ao crime", "apologia crimin", "glorificar crime",
    "como matar", "como assassinar", "como roubar", "como sequestrar",
    "fabricar arma", "arma caseira", "explosivo caseiro",
    "estupro", "violacao", "violação sexual",
    "racismo", "supremacia", "supremacista",
    "terrorista", "atentado", "massacre",
    "maconha sintetica", "sintetizar droga",
})

_ZERO_WIDTH_RE = re.compile(
    "[\u200b\u200c\u200d\u200e\u200f\u2060\ufeff\u00ad\u034f\u061c\u180e"
    "\u2028\u2029\u202a-\u202e\u2066-\u2069\ufff9-\ufffb]"
)


def _normalize(text: str) -> str:
    text = _ZERO_WIDTH_RE.sub("", text or "")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def check_literal_imagine_prompt(text: str) -> bool:
    """True if prompt must be blocked before any API call (fast, no network)."""
    if not text or not text.strip():
        return False
    if l1_scam_match(text) or l1_nsfw_match(text):
        return True
    if _IMAGINE_BLOCKED_RE.search(text):
        return True
    norm = _normalize(text)
    collapsed = re.sub(r"[^\w\s]", " ", norm, flags=re.UNICODE)
    collapsed = re.sub(r"\s+", " ", collapsed).strip()
    for term in _IMAGINE_EXTRA_TERMS:
        t = _normalize(term)
        if t and t in collapsed:
            return True
        if t and re.search(rf"(?<!\w){re.escape(t)}(?!\w)", collapsed, flags=re.UNICODE):
            return True
    return False
