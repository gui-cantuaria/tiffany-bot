"""Dice rolling and RPG macro system."""
import discord
from discord.ext import commands
import re
import os
import json
import logging
import asyncio
import time
from typing import Optional
import guild_config
import locale_utils
from locale_utils import tr, interaction_lang, resolve_lang
from utils import _embed

log = logging.getLogger('tiffany-bot')

_DICE_TERM_RE = re.compile(
    r"(?P<neg>-)?"
    r"(?P<count>\d*)d(?P<sides>\d+|f)"
    r"(?P<explode>!)?"
    r"(?P<keep>(?:kh|kl|k|dh|dl)\d*)?"
    r"(?P<pool>(?:>=|<=|>|<|==|=)\d+)?"
    r"(?P<nosort>ns)?",
    re.IGNORECASE,
)

# Legacy compat: old t20 notation -> d20 (silent, no error)
_T_TO_D_RE = re.compile(r"(\d*)t(\d+|f)", re.IGNORECASE)


def _normalize_dice_expr(expr: str) -> str:
    return _T_TO_D_RE.sub(r"\1d\2", expr.strip())


def _roll_fate_die() -> int:
    import random
    return random.choice([-1, 0, 1])


def _pool_count(rolls: list[int], op: str, target: int) -> int:
    if op in (">", "gt"):
        return sum(1 for r in rolls if r > target)
    if op in ("<", "lt"):
        return sum(1 for r in rolls if r < target)
    if op in (">=", "ge"):
        return sum(1 for r in rolls if r >= target)
    if op in ("<=", "le"):
        return sum(1 for r in rolls if r <= target)
    if op in ("=", "==", "eq"):
        return sum(1 for r in rolls if r == target)
    return 0


def _apply_keep_drop(rolls: list[int], keep_str: str, nosort: bool) -> list[int]:
    if not keep_str or not rolls:
        return list(rolls)
    kd = keep_str.lower()
    if kd.startswith("kh"):
        kd_type, num_s = "kh", kd[2:]
    elif kd.startswith("kl"):
        kd_type, num_s = "kl", kd[2:]
    elif kd.startswith("dh"):
        kd_type, num_s = "dh", kd[2:]
    elif kd.startswith("dl"):
        kd_type, num_s = "dl", kd[2:]
    elif kd.startswith("k") and not kd.startswith(("kh", "kl")):
        kd_type, num_s = "kh", kd[1:]
    else:
        return list(rolls)
    kd_num = min(max(int(num_s or "1"), 1), len(rolls))
    ordered = list(rolls) if nosort else sorted(rolls, reverse=True)
    if kd_type == "kh":
        return ordered[:kd_num]
    if kd_type == "kl":
        return sorted(rolls)[:kd_num]
    if kd_type == "dh":
        return ordered[kd_num:]
    if kd_type == "dl":
        return sorted(rolls)[kd_num:]
    return list(rolls)


def _roll_one_dice_term(term: str) -> tuple[float, str, int, int]:
    """Roll one dice term and return (value, formatted_text, crits, fumbles)."""
    import random
    m = _DICE_TERM_RE.fullmatch(term.strip().lower())
    if not m:
        raise ValueError("invalid term")
    count = min(max(int(m.group("count") or 1), 1), 100)
    is_fate = m.group("sides").lower() == "f"
    sides = 6 if is_fate else int(m.group("sides"))
    if not is_fate and (sides < 2 or sides > 1000):
        raise ValueError("invalid sides")
    explode = bool(m.group("explode"))
    keep_str = m.group("keep") or ""
    pool_m = m.group("pool")
    nosort = bool(m.group("nosort"))
    pool_op, pool_target = "", 0
    if pool_m:
        if pool_m.startswith(">="):
            pool_op, pool_target = ">=", int(pool_m[2:])
        elif pool_m.startswith("<="):
            pool_op, pool_target = "<=", int(pool_m[2:])
        elif pool_m.startswith(">"):
            pool_op, pool_target = ">", int(pool_m[1:])
        elif pool_m.startswith("<"):
            pool_op, pool_target = "<", int(pool_m[1:])
        elif pool_m.startswith("=="):
            pool_op, pool_target = "==", int(pool_m[2:])
        else:
            pool_op, pool_target = "=", int(pool_m[1:])

    rolls: list[int] = [
        _roll_fate_die() if is_fate else random.randint(1, sides) for _ in range(count)
    ]
    if explode and not is_fate:
        extra = 0
        for r in list(rolls):
            while r >= sides and extra < count * 12:
                rolls.append(random.randint(1, sides))
                extra += 1
                r = rolls[-1]
    kept = _apply_keep_drop(rolls, keep_str, nosort)

    # --- Rollem-style formatting: bold crits/fumbles, strikethrough dropped ---
    sorted_rolls = rolls if nosort else sorted(rolls, reverse=True)
    kept_remaining = list(kept)
    crits = 0
    fumbles = 0
    formatted: list[str] = []
    for r in sorted_rolls[:24]:
        is_kept = r in kept_remaining
        if is_kept:
            kept_remaining.remove(r)
        is_crit = not is_fate and r == sides
        is_fumble = not is_fate and r == 1
        if is_crit and is_kept:
            crits += 1
        if is_fumble and is_kept:
            fumbles += 1
        r_str = f"**{r}**" if is_crit else (f"**{r}**" if is_fumble else str(r))
        if not is_kept:
            r_str = f"~~{r_str}~~"
        formatted.append(r_str)
    rolls_show = ", ".join(formatted)
    if len(sorted_rolls) > 24:
        rolls_show += "…"

    if pool_op:
        succ = _pool_count(kept, pool_op, pool_target)
        return float(succ), f"{succ} sucesso(s) ← [{rolls_show}]", crits, fumbles
    total = sum(kept)
    return float(total), f"[{rolls_show}]", crits, fumbles


def _safe_math_eval(expr: str) -> float:
    safe = re.sub(r"[^0-9+\-*/().\s]", "", expr)
    if not safe.strip() or len(safe) > 200:
        raise ValueError("empty or too long")
    import ast, operator
    _OPS = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg, ast.UAdd: operator.pos,
    }
    def _eval_node(node):
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval_node(node.operand))
        raise ValueError("unsupported expression")
    tree = ast.parse(safe, mode="eval")
    return float(_eval_node(tree))


def _format_dice_with_math(
    work_lower: str,
    terms: list[re.Match[str]],
    rolls_parts: list[str],
    total: float,
) -> str:
    """Build clear display: [4] + 4 + 6 = **14** (die + modifiers = total)."""
    display = work_lower
    offset = 0
    for m, rolls_str in zip(terms, rolls_parts):
        start = m.start() + offset
        end = m.end() + offset
        display = display[:start] + rolls_str + display[end:]
        offset += len(rolls_str) - (end - start)
    display = re.sub(r"\s*([+\-*/()])\s*", r" \1 ", display).strip()
    total_s = str(int(total)) if total == int(total) else f"{total:g}"
    return f"{display} = **{total_s}**"


def _roll_single(expression: str, label: str = "") -> tuple[str, int, int]:
    """Roll a dice expression. Returns (text, total_crits, total_fumbles)."""
    raw = expression.strip()
    
    err_msg = (
        f"❌ **Não entendi:** `{raw}`\n\n"
        "💡 Exemplos: `d20`, `2d6+3`, `4d6dl1`, `5d10>=7` · calculadora: `c50+50`"
    )
    if not raw:
        return ("⚠️ Informe uma expressão. Ex: `d20`, `2d6+3`, `4d6dl1`, `5d10>=7`", 0, 0)
    work = raw
    # Label via [Label] prefixo inline
    label_m = re.match(r"^\[([^\]]+)\]\s*(.+)$", work)
    if label_m and not _DICE_TERM_RE.search(label_m.group(1)):
        label = label_m.group(1).strip()
        work = label_m.group(2).strip()
    work_lower = work.lower()
    prefix = f"**{label.upper()}:** " if label else ""
    try:
        terms = list(_DICE_TERM_RE.finditer(work_lower))
        if not terms:
            val = _safe_math_eval(work_lower)
            return (f"{prefix}{raw} = **{val:g}**", 0, 0)
        rolls_parts: list[str] = []
        vals: list[float] = []
        total_crits = 0
        total_fumbles = 0
        math_expr = work_lower
        offset = 0
        for m in terms:
            term = m.group(0)
            val, rolls_str, crits, fumbles = _roll_one_dice_term(term)
            total_crits += crits
            total_fumbles += fumbles
            rolls_parts.append(rolls_str)
            vals.append(val)
            repl = str(int(val) if val == int(val) else val)
            start = m.start() + offset
            math_expr = math_expr[:start] + repl + math_expr[m.end() + offset:]
            offset += len(repl) - (m.end() - m.start())
        if len(terms) == 1 and not re.search(r"[+*/()-]", _DICE_TERM_RE.sub("0", work_lower)):
            # Simple term without math: "**total** ← [rolls]"
            v = int(vals[0]) if vals[0] == int(vals[0]) else vals[0]
            if "," not in rolls_parts[0] and "sucesso" not in rolls_parts[0]:
                return (f"{prefix}**{v}**", total_crits, total_fumbles)
            return (f"{prefix}{rolls_parts[0]} = **{v}**", total_crits, total_fumbles)
        total = _safe_math_eval(math_expr)
        if len(terms) > 1:
            # Multiple terms: show each, then total
            lines = [f"{rolls_parts[i]} = {int(vals[i]) if vals[i] == int(vals[i]) else vals[i]}" for i in range(len(terms))]
            return (f"{prefix}\n" + "\n".join(lines) + f"\n**Total: {total:g}**", total_crits, total_fumbles)
        # Single term + math: "[dice] + mods = **total**"
        return (f"{prefix}{_format_dice_with_math(work_lower, terms, rolls_parts, total)}", total_crits, total_fumbles)
    except Exception:
        return (err_msg, 0, 0)


def _roll_dice(expression: str, label: str = "") -> tuple[str, int, int]:
    """Roll dice (standard d20 notation, 4d6…). Returns (text, crits, fumbles)."""
    import random
    expression = _normalize_dice_expr(expression)
    low = expression.lower()

    # If user types only a bare number (e.g. t!d 20), convert to d20.
    # But if it has math (50 + 25), leave as math!
    if re.match(r"^\d+$", low):
        expression = f"d{expression}"
        low = expression.lower()

    # RPG shortcuts (only work via t!d)
    if low in ("adv", "advantage", "vantagem"):
        text, crits, fumbles = _roll_single("2d20kh1")
        return (text + "\n*(Vantagem: maior de 2d20)*", crits, fumbles)
    if low in ("dis", "disadvantage", "desvantagem"):
        text, crits, fumbles = _roll_single("2d20kl1")
        return (text + "\n*(Desvantagem: menor de 2d20)*", crits, fumbles)
    adv_m = re.match(r"^(?:adv|advantage|vantagem)\s*([+-]\d+)$", low)
    if adv_m:
        mod = adv_m.group(1)
        text, crits, fumbles = _roll_single(f"2d20kh1{mod}")
        return (text + f"\n*(Vantagem {mod})*", crits, fumbles)
    dis_m = re.match(r"^(?:dis|disadvantage|desvantagem)\s*([+-]\d+)$", low)
    if dis_m:
        mod = dis_m.group(1)
        text, crits, fumbles = _roll_single(f"2d20kl1{mod}")
        return (text + f"\n*(Desvantagem {mod})*", crits, fumbles)

    if low in ("stats", "atributos", "stat", "atributo"):
        labels = ["FOR", "DES", "CON", "INT", "SAB", "CAR"]
        lines = []
        total_crits = 0
        total_fumbles = 0
        for lbl in labels:
            text, crits, fumbles = _roll_single("4d6dl1")
            total_crits += crits
            total_fumbles += fumbles
            lines.append(f"**{lbl}:** {text}")
        return ("**Rolagem de Atributos (4d6dl1)**\n" + "\n".join(lines), total_crits, total_fumbles)

    init_m = re.match(r"^(?:init|iniciativa|initiative)\s*([+-]?\d*)$", low)
    if init_m:
        mod_str = init_m.group(1)
        mod = int(mod_str) if mod_str and mod_str not in ("+", "-", "") else 0
        roll_val = random.randint(1, 20)
        total = roll_val + mod
        mod_display = f"+{mod}" if mod >= 0 else str(mod)
        is_crit = roll_val == 20
        is_fumble = roll_val == 1
        r_str = f"**[{roll_val}]**" if is_crit else (f"**({roll_val})**" if is_fumble else str(roll_val))
        return (f"{total} ← [{r_str}]d20{mod_display} *(Iniciativa)*", 1 if is_crit else 0, 1 if is_fumble else 0)

    if low in ("coin", "moeda", "coinflip", "cara", "coroa"):
        result = random.choice(["Cara", "Coroa"])
        return (f"**{result}!**", 0, 0)

    # Percentual (d100 / d%)
    if low in ("d%", "d100", "t%", "t100", "percentual"):
        roll_val = random.randint(1, 100)
        return (f"{roll_val} ← [{roll_val}]t100", 0, 0)

    rep_m = re.match(r"^(\d+)#(.+)$", expression, re.IGNORECASE)
    if rep_m:
        count = min(int(rep_m.group(1)), 20)
        sub = rep_m.group(2).strip()
        results = [_roll_single(sub, label) for _ in range(count)]
        total_crits = sum(c for _, c, _ in results)
        total_fumbles = sum(f for _, _, f in results)
        numbered = [f"`{i+1}.` {text}" for i, (text, _, _) in enumerate(results)]
        return ("\n".join(numbered), total_crits, total_fumbles)
    return _roll_single(expression, label)


def _parse_inline_specs(content: str) -> list[tuple[str, str]]:
    """Extract (expression, label) from each inline [roll] — used for reroll."""
    specs: list[tuple[str, str]] = []
    for m in re.finditer(r"\[([^\]]+)\]", content):
        inner = m.group(1).strip()
        if not inner:
            continue
        converted = _normalize_dice_expr(inner)
        if _DICE_TERM_RE.search(converted):
            parts = converted.split(None, 1)
            if len(parts) == 2 and _DICE_TERM_RE.search(parts[0]):
                if not _DICE_TERM_RE.search(parts[1]) and not re.match(r"^[+\-*/]", parts[1]):
                    specs.append((parts[0], parts[1]))
                    continue
            specs.append((converted, ""))
    return specs


def _parse_inline_rolls(content: str) -> tuple[list[tuple[str, int, int]], list[tuple[str, str]]]:
    """Roll [inline] and return (results, specs for reroll)."""
    results: list[tuple[str, int, int]] = []
    specs = _parse_inline_specs(content)
    rolls_info: list[tuple[str, str]] = []
    for expr, lbl in specs:
        text, crits, fumbles = _roll_dice(expr, lbl)
        if _dice_roll_ok(text):
            results.append((text, crits, fumbles))
            rolls_info.append((expr, lbl))
    return results, rolls_info


def _dice_roll_ok(text: str) -> bool:
    low = (text or "").lower()
    return "nao entendi" not in low and "não entendi" not in low and "⚠️" not in text and "❌" not in text


# Regex to detect dice expression messages (no prefix, d notation)
_DICE_MSG_EXPR_RE = re.compile(
    r"^(?:\d+#)?"  # optional repetitions (3#)
    r"(\d*d[f\d%]+)"  # first dice term (d20, 4d6, d%, df…)
    r"([!]?)"  # explode opcional
    r"((?:kh|kl|k|dh|dl)\d*)?"  # keep/drop opcional
    r"((?:>=|<=|>|<|==|=)\d+)?"  # pool opcional
    r"(ns)?"  # nosort opcional
    r"(\s*[+\-*/]\s*(?:\d+|\d*d[f\d%]+[!]?(?:(?:kh|kl|k|dh|dl)\d*)?(?:(?:>=|<=|>|<|==|=)\d+)?(?:ns)?))*"  # additional terms
    r"(?:\s+(.+))?$",  # label opcional
    re.IGNORECASE,
)

_DICE_MATH_RE = re.compile(r"^c\s*([\d(].*)$", re.IGNORECASE)


def _try_parse_dice_msg(content: str) -> tuple[str, str] | None:
    """Try to parse a message as dice (d20, 4d6…). Returns (expression, label) or None."""
    content = content.strip()
    if not content:
        return None
    # Calculator with c prefix (e.g. c20+5)
    math_m = _DICE_MATH_RE.match(content)
    if math_m:
        return math_m.group(1), ""

    m = _DICE_MSG_EXPR_RE.match(content)
    if not m:
        legacy = _normalize_dice_expr(content)
        if legacy != content.lower() and _DICE_MSG_EXPR_RE.match(legacy):
            m = _DICE_MSG_EXPR_RE.match(legacy)
            content = legacy
        else:
            return None
    label = (m.group(7) or "").strip()
    expr = content[: m.start(7)].strip() if label else content.strip()
    return _normalize_dice_expr(expr), label


_MACROS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dice_macros.json")
_DICE_MACROS_MAX = 20
_DICE_MACRO_NAME_MAX = 30
_DICE_REROLL_PREFIX = "reroll:"
_dice_macros: dict[str, dict[str, str]] = {}

# @rollem-next (Discord app id 840409146738475028)
_ROLLEM_NEXT_BOT_ID = 840409146738475028
# Classic @rollem — included when ROLLEM_DELETE_ALL=1
_ROLLEM_PRIME_BOT_ID = 240732567744151553
_ROLLEM_DEV_BOT_ID = 243615627581980672
_rollem_conflict_warned: set[int] = set()


def _rollem_known_bot_ids() -> frozenset[int]:
    return frozenset({_ROLLEM_NEXT_BOT_ID, _ROLLEM_PRIME_BOT_ID, _ROLLEM_DEV_BOT_ID})


async def _guild_has_rollem(guild: discord.Guild) -> bool:
    for bid in _rollem_known_bot_ids():
        try:
            await guild.fetch_member(bid)
            return True
        except discord.NotFound:
            continue
        except discord.HTTPException:
            continue
    return False


async def _maybe_warn_rollem_conflict(
    channel: discord.abc.Messageable,
    guild: discord.Guild,
) -> None:
    """Warn once per guild if Rollem is also present (same d20 syntax)."""
    gid = guild.id
    if gid in _rollem_conflict_warned:
        return
    if not await _guild_has_rollem(guild):
        return
    _rollem_conflict_warned.add(gid)
    try:
        await channel.send(
            embed=_embed(
                "⚠️ Detectei o **Rollem** neste servidor. Tiffany e Rollem usam a mesma sintaxe "
                "(`d20`, `4d6`…) — podem aparecer **duas respostas** no mesmo comando. "
                "Recomendo deixar só uma bot no canal de dados."
            ),
            delete_after=60,
        )
    except discord.HTTPException:
        pass


def _rollem_auto_delete_enabled() -> bool:
    return os.getenv("DICE_DELETE_ROLLEM", "1").strip().lower() not in ("0", "false", "no", "off")


def _rollem_delete_bot_ids() -> frozenset[int]:
    raw = os.getenv("ROLLEM_DELETE_BOT_IDS", "").strip()
    if raw:
        return frozenset(int(p.strip()) for p in raw.split(",") if p.strip().isdigit())
    ids = {_ROLLEM_NEXT_BOT_ID}
    if os.getenv("ROLLEM_DELETE_ALL", "0").strip().lower() in ("1", "true", "yes", "on"):
        ids.add(_ROLLEM_PRIME_BOT_ID)
    return frozenset(ids)


def _can_delete_in_channel(message: discord.Message) -> bool:
    if not message.guild or message.guild.me is None:
        return False
    channel = message.channel
    if not hasattr(channel, "permissions_for"):
        return False
    return channel.permissions_for(message.guild.me).manage_messages


def _dice_allowed_channels() -> Optional[set[int]]:
    """Allowed channels for prefixless rolls. None = all."""
    raw = os.getenv("DICE_CHANNELS", "").strip()
    if not raw:
        return None
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids or None


def _dice_channel_ok(channel_id: int) -> bool:
    allowed = _dice_allowed_channels()
    return allowed is None or channel_id in allowed


def _load_dice_macros():
    global _dice_macros
    if os.path.exists(_MACROS_FILE):
        try:
            with open(_MACROS_FILE, "r", encoding="utf-8") as f:
                _dice_macros = json.load(f)
        except Exception:
            _dice_macros = {}


def _save_dice_macros():
    tmp = _MACROS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_dice_macros, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _MACROS_FILE)


def _get_dice_macro(user_id: int, name: str) -> str:
    uid = str(user_id)
    return _dice_macros.get(uid, {}).get(name.lower(), "")


def _validate_dice_macro_name(name: str) -> Optional[str]:
    name = (name or "").strip().lower()
    if not name or len(name) > _DICE_MACRO_NAME_MAX:
        return f"Nome inválido (1–{_DICE_MACRO_NAME_MAX} caracteres)."
    if not re.match(r"^[\w\-]+$", name, re.UNICODE):
        return "Nome só pode ter letras, números, `_` e `-`."
    return None


def _validate_dice_expression(expr: str) -> Optional[str]:
    expr = (expr or "").strip()
    if not expr:
        return "Fórmula vazia."
    if len(expr) > 200:
        return "Fórmula longa demais (máx. 200 caracteres)."
    text, _, _ = _roll_dice(expr)
    if not _dice_roll_ok(text):
        return "Fórmula inválida. Ex: `1d20+5`, `4d6dl1`, `2d20kh1`."
    return None


def _set_dice_macro(user_id: int, name: str, expr: str) -> tuple[bool, str]:
    err = _validate_dice_macro_name(name)
    if err:
        return False, err
    err = _validate_dice_expression(expr)
    if err:
        return False, err
    uid = str(user_id)
    key = name.strip().lower()
    user_macros = _dice_macros.setdefault(uid, {})
    if key not in user_macros and len(user_macros) >= _DICE_MACROS_MAX:
        return False, (
            f"Limite de **{_DICE_MACROS_MAX}** macros por usuário. "
            f"Remova uma com `t!d macro remove <nome>`."
        )
    user_macros[key] = expr.strip()
    _save_dice_macros()
    return True, ""


def _remove_dice_macro(user_id: int, name: str) -> bool:
    uid = str(user_id)
    key = name.lower()
    if uid in _dice_macros and key in _dice_macros[uid]:
        del _dice_macros[uid][key]
        if not _dice_macros[uid]:
            del _dice_macros[uid]
        _save_dice_macros()
        return True
    return False


def _decode_rolls_info(token: str) -> list[tuple[str, str]]:
    import base64
    if not token:
        return []
    pad = "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(token + pad)
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, list):
            return [(str(a), str(b)) for a, b in data]
    except Exception:
        pass
    return []


def _rolls_info_from_footer(footer_text: str) -> list[tuple[str, str]]:
    if not footer_text or _DICE_REROLL_PREFIX not in footer_text:
        return []
    token = footer_text.split(_DICE_REROLL_PREFIX, 1)[1].strip()
    return _decode_rolls_info(token)


def _format_dice_description(roll_results: list[tuple[str, int, int]]) -> tuple[str, int, int]:
    total_crits = sum(c for _, c, _ in roll_results)
    total_fumbles = sum(f for _, _, f in roll_results)
    body = "\n".join(t for t, _, _ in roll_results)
    desc = body
    if total_crits > 0:
        desc = f"🟩 **Críticos: {total_crits}**\n\n{desc}"
    elif total_fumbles > 0:
        desc = f"🟥 **Falhas Críticas: {total_fumbles}**\n\n{desc}"
    return desc, total_crits, total_fumbles


def _build_dice_embed(desc: str, crits: int, fumbles: int) -> discord.Embed:
    return _embed(desc)


_DICE_HELP_TEXT = (
    "**Dados** — digite no chat, sem prefixo.\n\n"
    "**Básico:**\n"
    "`d20` — um dado de 20 lados\n"
    "`4d6` · `2d10+5` — vários dados, com bônus\n"
    "`4d6 ataque` — nomeia a rolagem\n"
    "`[d20+5]` — rola no meio da frase\n"
    "`c50+50` — calculadora\n\n"
    "**Avançado:**\n"
    "`3#d20` — repete 3 vezes\n"
    "`2d20kh1` — fica com o maior · `kl1` com o menor\n"
    "`4d6dl1` — descarta o menor · `dh1` descarta o maior\n"
    "`4d6!` — explosivo (máximo rola de novo)\n"
    "`5d10>=7` — conta quantos deram 7+\n"
    "`df` — dado Fate (−, 0, +)\n\n"
    "**Atalhos RPG** (`t!d`):\n"
    "`t!d adv` / `t!d dis` — vantagem / desvantagem\n"
    "`t!d stats` — atributos · `t!d init +3` — iniciativa · `t!d coin` — moeda · `t!d d%` — 1–100\n\n"
    "**Macros** (máx. 20):\n"
    "`t!d macro add ataque 1d20+7` → depois `t!d ataque`\n"
    "`t!d macro list` · `t!d macro remove <nome>`\n\n"
    "Críticos em **negrito**, descartados ~~riscados~~ · 🔄 Reroll"
)


class DiceRerollView(discord.ui.View):
    """Reroll button — formulas live on the view instance (legacy messages: footer)."""

    def __init__(self, rolls_info: Optional[list[tuple[str, str]]] = None):
        super().__init__(timeout=None)
        self.rolls_info = rolls_info or []

    @discord.ui.button(
        label="🔄 Reroll",
        style=discord.ButtonStyle.secondary,
        custom_id="tiffany:dice_reroll",
    )
    async def btn_reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        rolls_info = list(self.rolls_info)
        if not rolls_info and interaction.message and interaction.message.embeds:
            ft = interaction.message.embeds[0].footer
            if ft and ft.text:
                rolls_info = _rolls_info_from_footer(ft.text)
        if not rolls_info:
            await interaction.response.send_message(
                embed=_embed(tr(interaction_lang(interaction), "cmd.dice.reroll_no_formula")),
                ephemeral=True,
            )
            return

        roll_results: list[tuple[str, int, int]] = []
        for expr, lbl in rolls_info:
            text, crits, fumbles = _roll_dice(expr, lbl)
            if _dice_roll_ok(text):
                roll_results.append((text, crits, fumbles))

        if not roll_results:
            await interaction.response.send_message(
                embed=_embed(tr(interaction_lang(interaction), "cmd.dice.reroll_failed")),
                ephemeral=True,
            )
            return

        desc, total_crits, total_fumbles = _format_dice_description(roll_results)
        em = _build_dice_embed(desc, total_crits, total_fumbles)
        await interaction.response.send_message(
            content=f"<@{interaction.user.id}> rolou novamente:",
            embed=em,
            view=DiceRerollView(rolls_info),
        )


_voice_registered = False


def register_voice(bot: commands.Bot) -> None:
    global _voice_registered
    if _voice_registered:
        log.warning("register_voice called more than once — ignoring duplicate.")
        return
    _voice_registered = True
    _load_dice_macros()
    bot.add_view(DiceRerollView())

    from infra.i18n_middleware import register_i18n_middleware
    register_i18n_middleware(bot)

    @bot.check
    async def _global_cmd_rate_limit(ctx: commands.Context) -> bool:
        if ctx.author.bot or not ctx.command:
            return True
        # Hybrid slash: blacklist + rate limit run in CommandTree.interaction_check.
        if ctx.interaction is not None:
            return True
        if not await _require_feature(ctx):
            return False
        uid = ctx.author.id
        if ctx.guild and guild_config.is_blacklisted(ctx.guild.id, uid):
            lang = _ctx_lang(ctx)
            await ctx.send(embed=_embed(tr(lang, "blocked.1")), delete_after=8)
            return False
        if not ctx.guild and guild_config.is_user_blacklisted_anywhere(uid):
            lang = _ctx_lang(ctx)
            await ctx.send(embed=_embed(tr(lang, "blocked.1")), delete_after=8)
            return False
        ok, wait = _check_cmd_rate_limit(ctx.author.id, ctx.command.name)
        if not ok:
            raise TiffanyRateLimited(wait, ctx.command.name, slash=False)
        return True

    _dm_slash = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    _guild_slash = app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)

    from random_songs import RANDOM_SONGS as _RANDOM_SONGS
    try:
        from random_songs import RANDOM_DISCOVERY as _RANDOM_DISCOVERY
    except ImportError:
        _RANDOM_DISCOVERY: list[str] = []

    # --- Prefixless dice listener (d20, 4d6, c50+50…) ---
    @bot.listen("on_message")
    async def _on_message_dice(message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not guild_config.is_feature_enabled(message.guild.id, "dice"):
            return
        if not _dice_channel_ok(message.channel.id):
            return
        content = message.content.strip()
        if not content:
            return
        # Cap length before regex parsing to avoid ReDoS/CPU abuse on long input.
        if len(content) > 200:
            return
        lower = content.lower()
        if lower.startswith(("t!", "!", "/", "-", ".", ";", ">", "?", "%")):
            return
        if message.content.startswith("<@"):
            return

        roll_results: list[tuple[str, int, int]] = []
        rolls_info: list[tuple[str, str]] = []

        if "[" in content and "]" in content:
            inline_results, inline_specs = _parse_inline_rolls(content)
            if inline_results:
                roll_results = inline_results
                rolls_info = inline_specs

        if not roll_results:
            parsed = _try_parse_dice_msg(content)
            if parsed:
                expr, lbl = parsed
                text, crits, fumbles = _roll_dice(expr, lbl)
                if _dice_roll_ok(text):
                    roll_results = [(text, crits, fumbles)]
                    rolls_info = [(expr, lbl)]

        if not roll_results:
            return

        allowed, wait = _check_cmd_rate_limit(message.author.id, "d")
        if not allowed:
            try:
                await message.channel.send(
                    embed=_embed(tr(resolve_lang(message.guild, message.author.id), "cmd.dice.cooldown", secs=f"{wait:.0f}")),
                    delete_after=5,
                )
            except discord.HTTPException:
                pass
            return

        _touch_activity(message.guild.id)
        desc, total_crits, total_fumbles = _format_dice_description(roll_results)
        em = _build_dice_embed(desc, total_crits, total_fumbles)
        try:
            await message.channel.send(
                embed=em,
                view=DiceRerollView(rolls_info),
            )
            if message.guild:
                await _maybe_warn_rollem_conflict(message.channel, message.guild)
        except discord.HTTPException as e:
            log.warning("Failed to send dice roll: %s", e)

    @bot.listen("on_message")
    async def _delete_rollem_replies(message: discord.Message) -> None:
        """Delete Rollem Next replies (and optionally @rollem) to avoid channel clutter."""
        if not message.guild or not message.author.bot:
            return
        if not _rollem_auto_delete_enabled():
            return
        if message.author.id not in _rollem_delete_bot_ids():
            return
        if not _dice_channel_ok(message.channel.id):
            return
        if not _can_delete_in_channel(message):
            return
        try:
            await message.delete()
        except discord.HTTPException as e:
            log.debug("Could not delete Rollem message (%s): %s", message.author.id, e)

