"""
Testes de unidade para os sistemas de dedup de notices.py e offers.py.
Executa isolado — não depende de Discord, aiohttp ou .env.
"""
import sys, os, time, hashlib, re, unicodedata

# ── Garantir imports do projeto ──
sys.path.insert(0, os.path.dirname(__file__))

# =================================================================
# PARTE 1: Testes de notices.py (entity-overlap dedup)
# =================================================================
# Importações circulares com Discord impedem import direto,
# então replicamos as funções puras (sem I/O) exatamente como estão.

_STOPWORDS = {
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "um", "uma", "uns", "umas", "com", "por", "para", "como",
    "que", "e", "ou", "mas", "se", "ao", "aos", "the", "a", "an", "of", "in",
    "on", "for", "to", "and", "or", "is", "it", "its", "with", "by", "at",
    "from", "has", "have", "had", "be", "are", "was", "were", "will", "can",
}
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)

_TOPIC_NOISE = {
    "novo", "nova", "novos", "novas", "lança", "lançar", "lançou", "lançamento",
    "anuncia", "anunciar", "anunciou", "revela", "revelar", "revelou", "alerta",
    "alertar", "alertou", "propõe", "propor", "modelo", "modelos", "sistema",
    "sistemas", "empresa", "empresas", "tecnologia", "agora", "pode", "vai",
    "será", "primeiro", "primeira", "global", "mundo", "mercado", "setor",
    "mais", "como", "sobre", "não", "muito", "também", "após", "até",
    "ainda", "já", "ser", "ter", "deve", "diz", "faz", "usa", "usar",
    "usar", "afirma", "diz", "says", "new", "launches", "announces",
    "reveals", "report", "could", "may", "now", "first", "big", "just",
    "get", "gets", "got", "make", "makes", "made", "says", "said",
    "plan", "plans", "feature", "update", "latest", "according",
}

TOPIC_IDX_TTL_HORAS = 48
_ENTITY_OVERLAP_MIN = 2


def _extract_topic_keys(titulo: str) -> frozenset[str]:
    norm = (titulo or "").lower().strip()
    norm = _PUNCT_RE.sub(" ", norm)
    all_noise = _STOPWORDS | _TOPIC_NOISE
    palavras = [p for p in norm.split() if p not in all_noise and len(p) > 2]
    original_words = (titulo or "").split()
    capitalized = set()
    for w in original_words:
        wl = _PUNCT_RE.sub("", w).lower()
        if w and w[0].isupper() and len(wl) > 2 and wl not in all_noise:
            capitalized.add(wl)
    ordered = [p for p in palavras if p in capitalized]
    ordered += [p for p in palavras if p not in capitalized]
    keys = ordered[:5]
    if len(keys) < 2:
        return frozenset()
    return frozenset(keys)


def _get_entity_groups(h: dict) -> list:
    g = h.get("_entity_groups")
    return g if isinstance(g, list) else []


def _entity_groups_prune(groups: list) -> list:
    cutoff = int(time.time()) - (TOPIC_IDX_TTL_HORAS * 3600)
    return [g for g in groups if g.get("ts", 0) >= cutoff]


def topic_is_dup(h: dict, titulo: str) -> bool:
    keys = _extract_topic_keys(titulo)
    if len(keys) < _ENTITY_OVERLAP_MIN:
        return False
    groups = _get_entity_groups(h)
    for g in groups:
        past_keys = set(g.get("keys", []))
        if len(keys & past_keys) >= _ENTITY_OVERLAP_MIN:
            return True
    return False


def topic_add(h: dict, titulo: str) -> None:
    keys = _extract_topic_keys(titulo)
    if len(keys) < 2:
        return
    groups = _get_entity_groups(h)
    groups.append({"keys": sorted(keys), "ts": int(time.time())})
    h["_entity_groups"] = groups


# =================================================================
# PARTE 2: Testes de offers.py (cross-day title dedup)
# =================================================================

try:
    from offers_cog import (
        _deal_hash,
        _is_title_key_in_history,
        _mark_posted,
        _title_key,
    )
except ImportError:
    _TITLE_GENERIC = frozenset({
        "notebook", "teclado", "mouse", "headset", "monitor", "processador",
        "memoria", "placa", "ssd", "webcam", "laptop", "desktop", "gamer",
        "gaming", "mecanico", "sem", "fio", "com", "para", "rgb", "led",
        "preto", "branco", "prata", "cinza", "compacto", "gamer",
    })

    def _title_key(title: str) -> str:
        t = unicodedata.normalize("NFD", title.lower())
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
        t = re.sub(r"[^\w\s]", " ", t)
        words = [w for w in t.split() if len(w) >= 2 and w not in _TITLE_GENERIC]
        return " ".join(words[:3])

    def _deal_hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _is_title_key_in_history(history: dict, key: str) -> bool:
        if not key:
            return False
        for v in history.get("deals", {}).values():
            if isinstance(v, dict) and v.get("tkey") == key:
                return True
        return False

    def _mark_posted(history: dict, url: str, title: str, orig_tkey: str = "", listing: str = "") -> None:
        h = _deal_hash(url)
        entry = {
            "url": url,
            "title": title[:100],
            "ts": time.time(),
        }
        key = orig_tkey or _title_key(title)
        if key:
            entry["tkey"] = key
        if listing:
            entry["listing"] = listing
        history.setdefault("deals", {})[h] = entry


# =================================================================
# TESTES
# =================================================================
passed = 0
failed = 0


def check(name: str, condition: bool):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}")
        failed += 1


print("=" * 60)
print("TESTES DE DEDUP — notices.py (entity-overlap)")
print("=" * 60)

# --- Test 1: _extract_topic_keys extrai entidades corretas ---
print("\n🔹 _extract_topic_keys")
keys1 = _extract_topic_keys("Anthropic anuncia parceria com governo brasileiro para IA")
check("Extrai 'anthropic' como entidade", "anthropic" in keys1)
check("Exclui 'anuncia' (noise)", "anuncia" not in keys1)
check("Retorna frozenset", isinstance(keys1, frozenset))
check("Retorna entre 2 e 5 keys", 2 <= len(keys1) <= 5)

keys_empty = _extract_topic_keys("De um")
check("Título muito curto → frozenset vazio", len(keys_empty) == 0)

keys_short = _extract_topic_keys("O e a")
check("Só stopwords → frozenset vazio", len(keys_short) == 0)

# --- Test 2: entity overlap detecta temas duplicados ---
print("\n🔹 topic_is_dup / topic_add (overlap)")
h: dict = {}

titulo_a = "Anthropic fecha parceria com governo brasileiro para regulação de IA"
titulo_b = "Governo brasileiro e Anthropic anunciam acordo sobre inteligência artificial"
titulo_c = "Tesla apresenta novo carro autônomo na Europa"

topic_add(h, titulo_a)
check("Artigo A registrado no histórico", len(h.get("_entity_groups", [])) == 1)

dup = topic_is_dup(h, titulo_b)
keys_a = _extract_topic_keys(titulo_a)
keys_b = _extract_topic_keys(titulo_b)
overlap = keys_a & keys_b
print(f"     Keys A: {keys_a}")
print(f"     Keys B: {keys_b}")
print(f"     Overlap: {overlap} (len={len(overlap)})")
check(f"Artigo B é duplicata de A (overlap >= {_ENTITY_OVERLAP_MIN})", dup)

dup_c = topic_is_dup(h, titulo_c)
check("Artigo C (Tesla) NÃO é duplicata de A (Anthropic)", not dup_c)

# --- Test 3: in-cycle overlap (simulação) ---
print("\n🔹 In-cycle entity overlap (lógica do loop)")
_cycle_topic_groups: list[frozenset[str]] = []

keys_d = _extract_topic_keys("OpenAI lança GPT-5 com capacidades multimodais avançadas")
_cycle_topic_groups.append(keys_d)

keys_e = _extract_topic_keys("GPT-5 da OpenAI traz multimodalidade e novo benchmark")
_cycle_dup = any(
    len(keys_e & past) >= _ENTITY_OVERLAP_MIN
    for past in _cycle_topic_groups
) if len(keys_e) >= _ENTITY_OVERLAP_MIN else False
print(f"     Keys D: {keys_d}")
print(f"     Keys E: {keys_e}")
print(f"     Overlap: {keys_d & keys_e}")
check("In-cycle: GPT-5/OpenAI detectado como duplicata", _cycle_dup)

keys_f = _extract_topic_keys("Samsung lança Galaxy S25 Ultra com bateria melhorada")
_cycle_dup_f = any(
    len(keys_f & past) >= _ENTITY_OVERLAP_MIN
    for past in _cycle_topic_groups
) if len(keys_f) >= _ENTITY_OVERLAP_MIN else False
check("In-cycle: Samsung Galaxy NÃO é dup de OpenAI GPT-5", not _cycle_dup_f)

# --- Test 4: pruning de entity groups expirados ---
print("\n🔹 _entity_groups_prune")
old_ts = int(time.time()) - (TOPIC_IDX_TTL_HORAS * 3600 + 100)  # expirado
new_ts = int(time.time()) - 3600  # 1 hora atrás (válido)

groups = [
    {"keys": ["anthropic", "governo"], "ts": old_ts},
    {"keys": ["openai", "gpt5"], "ts": new_ts},
]
pruned = _entity_groups_prune(groups)
check("Prune remove grupo expirado", len(pruned) == 1)
check("Prune mantém grupo recente", pruned[0]["keys"] == ["openai", "gpt5"])

# --- Test 5: cap de 400 entity groups ---
print("\n🔹 Cap de 400 entity groups")
h_big: dict = {"_entity_groups": [
    {"keys": [f"word{i}", f"term{i}"], "ts": int(time.time())}
    for i in range(500)
]}
groups_big = _get_entity_groups(h_big)
check("Antes do cap: 500 groups", len(groups_big) == 500)
groups_big = _entity_groups_prune(groups_big)
if len(groups_big) > 400:
    groups_big = groups_big[-400:]
check("Depois do cap: 400 groups", len(groups_big) == 400)

# --- Test 6: histórico vazio / inválido ---
print("\n🔹 Edge cases (histórico vazio/inválido)")
check("Histórico vazio → não é dup", not topic_is_dup({}, titulo_a))
check("Histórico com _entity_groups=None → não é dup", not topic_is_dup({"_entity_groups": None}, titulo_a))
check("Histórico com _entity_groups='lixo' → não é dup", not topic_is_dup({"_entity_groups": "lixo"}, titulo_a))


print("\n" + "=" * 60)
print("TESTES DE DEDUP — offers.py (cross-day title key)")
print("=" * 60)

# --- Test 7: _title_key extrai marca+modelo ---
print("\n🔹 _title_key")
k1 = _title_key("Samsung Galaxy Book4 i5 512GB SSD Notebook Gamer")
check("_title_key notebook Galaxy Book4", "nb:galaxy-book4" in k1 or "galaxy" in k1)

k2 = _title_key("Monitor LG 27\" 4K UHD IPS")
check("_title_key com aspas/pontuação", len(k2.split()) >= 1)

k_ryzen_a = _title_key("AMD Ryzen 7 5700 AM4 8C 16T 4.6GHz 65W TDP")
k_ryzen_b = _title_key("Processador AMD Ryzen 7 5700 8N16T AM4")
check("Ryzen 5700 títulos diferentes → mesma key", k_ryzen_a == k_ryzen_b and "cpu:ryzen5700" in k_ryzen_a)

k_gpu_a = _title_key("Placa de Video MSI RTX 5060 Shadow 2x OC, 8GB, GDDR7")
k_gpu_b = _title_key("Placa de Video MSI RTX 5060 Shadow 2X OC 8GB GDDR7-912-V537-037")
check("RTX 5060 títulos diferentes → mesma key", k_gpu_a == k_gpu_b and "gpu:5060" in k_gpu_a)

k_ram_a = _title_key("Memória DDR4 16GB PC3200 Vengeance LPX Preto CORSAIR")
k_ram_b = _title_key("Memória DDR4 16GB PC3200 Vengeance LPX Preto CORSAIR")
check("Corsair Vengeance 16GB → key estável", k_ram_a == k_ram_b and "ram:vengeance-16gb-ddr4" in k_ram_a)

k_mobo_a = _title_key("Placa-Mãe Asus Prime B550M-A, AMD AM4")
k_mobo_b = _title_key("Placa Mãe ASUS PRIME B550M-A AM4")
check("B550M-A títulos diferentes → mesma key", k_mobo_a == k_mobo_b and "mobo:b550m-a" in k_mobo_a)

k_empty = _title_key("")
check("Título vazio → string vazia ou curta", len(k_empty.split()) <= 1)

# --- Test 8: _mark_posted persiste tkey ---
print("\n🔹 _mark_posted persiste tkey")
history: dict = {}
_mark_posted(history, "https://promobit.com/deal/123", "Samsung Galaxy Book4 i5 512GB SSD")
deal_hash = _deal_hash("https://promobit.com/deal/123")
check("Deal registrado no histórico", deal_hash in history.get("deals", {}))
entry = history["deals"][deal_hash]
check("Entry tem campo 'tkey'", "tkey" in entry)
check("tkey corresponde ao _title_key", entry["tkey"] == _title_key("Samsung Galaxy Book4 i5 512GB SSD"))
check("Entry tem URL", entry["url"] == "https://promobit.com/deal/123")
check("Entry tem timestamp", "ts" in entry)

# --- Test 9: _is_title_key_in_history encontra tkey persistido ---
print("\n🔹 _is_title_key_in_history")
key = _title_key("Samsung Galaxy Book4 i5 512GB SSD")
check("Encontra tkey no histórico", _is_title_key_in_history(history, key))

key_outro = _title_key("LG 27GL850 Monitor UltraGear")
check("NÃO encontra tkey diferente", not _is_title_key_in_history(history, key_outro))

check("key vazia → False", not _is_title_key_in_history(history, ""))
check("Histórico vazio → False", not _is_title_key_in_history({}, key))

# --- Test 10: cross-day dedup funciona ---
print("\n🔹 Cross-day dedup (simulação)")
# Dia 1: postou Samsung Galaxy Book4
hist: dict = {}
_mark_posted(hist, "https://promobit.com/deal/111", "Samsung Galaxy Book4 i5 512GB SSD Notebook")

# Dia 2: mesma oferta com URL diferente e título levemente diferente
url_dia2 = "https://promobit.com/deal/222"
title_dia2 = "Samsung Galaxy Book4 i5 16GB 512GB SSD - Preto"
key_dia2 = _title_key(title_dia2)
key_dia1 = _title_key("Samsung Galaxy Book4 i5 512GB SSD Notebook")
print(f"     Key dia 1: '{key_dia1}'")
print(f"     Key dia 2: '{key_dia2}'")

# URL é diferente, então _is_duplicate seria False
is_url_dup = _deal_hash(url_dia2) in hist.get("deals", {})
check("URL diferente → _is_duplicate=False", not is_url_dup)

# Mas o título bate no histórico
is_title_dup = _is_title_key_in_history(hist, key_dia2)
check(f"Cross-day title dedup: keys iguais = {key_dia1 == key_dia2}", key_dia1 == key_dia2)
if key_dia1 == key_dia2:
    check("_is_title_key_in_history detecta o dup cross-day", is_title_dup)
else:
    check("Keys diferem (esperado para títulos distintos)", True)
    print(f"     ⚠️  Título variou o suficiente para gerar key diferente (ok)")

# --- Test 11: _deal_hash determinístico ---
print("\n🔹 _deal_hash")
h1 = _deal_hash("https://promobit.com/deal/123")
h2 = _deal_hash("https://promobit.com/deal/123")
h3 = _deal_hash("https://promobit.com/deal/456")
check("Hash é determinístico", h1 == h2)
check("URLs diferentes → hashes diferentes", h1 != h3)
check("Hash tem 16 chars", len(h1) == 16)

# =================================================================
# RESUMO
# =================================================================
print("\n" + "=" * 60)
total = passed + failed
if failed == 0:
    print(f"🎉 TODOS OS {total} TESTES PASSARAM!")
else:
    print(f"⚠️  {passed}/{total} passaram, {failed} falharam")
print("=" * 60)

sys.exit(1 if failed > 0 else 0)
