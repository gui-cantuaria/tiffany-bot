"""
Tiffany OS — Intelligent Deal Validation Engine (P0.8)
======================================================
Intelligent promotion validator and "Metade do Dobro" (Fake Discount) detection engine.

Prevents Tiffany Bot from posting fake store promotions where prices are inflated 
or where store claims huge discounts (e.g. "70% OFF") on products priced at or above 
normal market average (e.g., RTX 4060 Ti / RTX 5060 Ti at R$ 3.700 claiming "70% OFF" 
when real deal price is R$ 2.200 - 2.300).

Features:
- Regex-based hardware model & reference price extractor (GPUs, CPUs, SSDs, RAM, Consoles).
- Real discount percentage calculation against estimated market baseline.
- Fake original price ("De R$ ...") inflation detector.
- OpenRouter AI async fallback for unindexed hardware/products.
- Detailed verdict codes & Discord embed badges.
"""

from __future__ import annotations
import re
import json
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Tuple, List

log = logging.getLogger("tiffany.core.deal_validator")

# =========================
# DATACLASS & VERDICTS
# =========================

class DealVerdictCode:
    ULTRA_DEAL = "ULTRA_DEAL"                 # Real discount >= 20% below market baseline
    REAL_DEAL = "REAL_DEAL"                   # Real discount 10-19% below market baseline
    FAIR_PRICE = "FAIR_PRICE"                 # Real discount 0-9% below market baseline
    OVERPRICED = "OVERPRICED"                 # Price is > 5% above market baseline
    FAKE_DISCOUNT = "FAKE_DISCOUNT"           # Store claimed huge % OFF, but price is market or overpriced
    METADE_DO_DOBRO = "METADE_DO_DOBRO"       # Store inflated original price by > 35% above market baseline

@dataclass
class DealValidationResult:
    is_valid_deal: bool
    verdict_code: str
    verdict_badge: str
    real_discount_pct: float
    claimed_discount_pct: float
    expected_market_price: Optional[float]
    great_deal_price: Optional[float]
    price_inflation_detected: bool
    rejection_reason: str = ""
    confidence_score: float = 1.0
    matched_model: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid_deal": self.is_valid_deal,
            "verdict_code": self.verdict_code,
            "verdict_badge": self.verdict_badge,
            "real_discount_pct": round(self.real_discount_pct, 1),
            "claimed_discount_pct": round(self.claimed_discount_pct, 1),
            "expected_market_price": self.expected_market_price,
            "great_deal_price": self.great_deal_price,
            "price_inflation_detected": self.price_inflation_detected,
            "rejection_reason": self.rejection_reason,
            "confidence_score": self.confidence_score,
            "matched_model": self.matched_model,
        }


# =========================
# HARDWARE PRICE BASELINES (BRL / R$)
# =========================

@dataclass
class HardwareReference:
    pattern: re.Pattern
    model_name: str
    baseline_price: float
    great_deal_price: float
    max_normal_price: float

_HARDWARE_REFERENCES: List[HardwareReference] = [
    # --- GPUs (NVIDIA) ---
    HardwareReference(
        pattern=re.compile(r"\b(rtx\s*5090)\b", re.IGNORECASE),
        model_name="NVIDIA RTX 5090",
        baseline_price=17000.0,
        great_deal_price=14500.0,
        max_normal_price=18500.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rtx\s*5080)\b", re.IGNORECASE),
        model_name="NVIDIA RTX 5080",
        baseline_price=9500.0,
        great_deal_price=8200.0,
        max_normal_price=10500.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rtx\s*5070\s*ti)\b", re.IGNORECASE),
        model_name="NVIDIA RTX 5070 Ti",
        baseline_price=6200.0,
        great_deal_price=5200.0,
        max_normal_price=6900.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rtx\s*5070)\b", re.IGNORECASE),
        model_name="NVIDIA RTX 5070",
        baseline_price=4500.0,
        great_deal_price=3800.0,
        max_normal_price=5000.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rtx\s*(?:5060\s*ti|4060\s*ti))\b", re.IGNORECASE),
        model_name="NVIDIA RTX 4060 Ti / 5060 Ti",
        baseline_price=2700.0,
        great_deal_price=2300.0,
        max_normal_price=2990.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rtx\s*(?:5060|4060))\b", re.IGNORECASE),
        model_name="NVIDIA RTX 4060 / 5060",
        baseline_price=2100.0,
        great_deal_price=1750.0,
        max_normal_price=2350.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rtx\s*4090)\b", re.IGNORECASE),
        model_name="NVIDIA RTX 4090",
        baseline_price=13500.0,
        great_deal_price=11500.0,
        max_normal_price=15000.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rtx\s*4080(?:\s*super)?)\b", re.IGNORECASE),
        model_name="NVIDIA RTX 4080 / 4080 Super",
        baseline_price=7500.0,
        great_deal_price=6400.0,
        max_normal_price=8200.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rtx\s*4070\s*ti(?:\s*super)?)\b", re.IGNORECASE),
        model_name="NVIDIA RTX 4070 Ti / 4070 Ti Super",
        baseline_price=5400.0,
        great_deal_price=4500.0,
        max_normal_price=5900.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rtx\s*4070(?:\s*super)?)\b", re.IGNORECASE),
        model_name="NVIDIA RTX 4070 / 4070 Super",
        baseline_price=4100.0,
        great_deal_price=3400.0,
        max_normal_price=4500.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rtx\s*3060(?:\s*ti)?)\b", re.IGNORECASE),
        model_name="NVIDIA RTX 3060 / 3060 Ti",
        baseline_price=1700.0,
        great_deal_price=1350.0,
        max_normal_price=1900.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(gtx\s*1650)\b", re.IGNORECASE),
        model_name="NVIDIA GTX 1650",
        baseline_price=850.0,
        great_deal_price=680.0,
        max_normal_price=980.0,
    ),

    # --- GPUs (AMD) ---
    HardwareReference(
        pattern=re.compile(r"\b(rx\s*7900\s*xtx)\b", re.IGNORECASE),
        model_name="AMD RX 7900 XTX",
        baseline_price=7200.0,
        great_deal_price=6100.0,
        max_normal_price=7900.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rx\s*7800\s*xt)\b", re.IGNORECASE),
        model_name="AMD RX 7800 XT",
        baseline_price=3800.0,
        great_deal_price=3100.0,
        max_normal_price=4200.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rx\s*7700\s*xt)\b", re.IGNORECASE),
        model_name="AMD RX 7700 XT",
        baseline_price=3100.0,
        great_deal_price=2500.0,
        max_normal_price=3400.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rx\s*7600(?:\s*xt)?)\b", re.IGNORECASE),
        model_name="AMD RX 7600 / 7600 XT",
        baseline_price=1750.0,
        great_deal_price=1390.0,
        max_normal_price=1950.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(rx\s*6600(?:\s*xt)?)\b", re.IGNORECASE),
        model_name="AMD RX 6600 / 6600 XT",
        baseline_price=1300.0,
        great_deal_price=1050.0,
        max_normal_price=1450.0,
    ),

    # --- CPUs (AMD) ---
    HardwareReference(
        pattern=re.compile(r"\b(ryzen\s*7\s*7800x3d)\b", re.IGNORECASE),
        model_name="AMD Ryzen 7 7800X3D",
        baseline_price=2700.0,
        great_deal_price=2150.0,
        max_normal_price=2950.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(ryzen\s*7\s*5700x3d)\b", re.IGNORECASE),
        model_name="AMD Ryzen 7 5700X3D",
        baseline_price=1450.0,
        great_deal_price=1150.0,
        max_normal_price=1600.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(ryzen\s*5\s*7600[x]?)\b", re.IGNORECASE),
        model_name="AMD Ryzen 5 7600 / 7600X",
        baseline_price=1300.0,
        great_deal_price=1050.0,
        max_normal_price=1450.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(ryzen\s*5\s*5600[xgt]?)\b", re.IGNORECASE),
        model_name="AMD Ryzen 5 5600",
        baseline_price=850.0,
        great_deal_price=620.0,
        max_normal_price=950.0,
    ),

    # --- CPUs (Intel) ---
    HardwareReference(
        pattern=re.compile(r"\b(i9\s*14900k[f]?|i9\s*13900k[f]?)\b", re.IGNORECASE),
        model_name="Intel Core i9 14900K / 13900K",
        baseline_price=4200.0,
        great_deal_price=3400.0,
        max_normal_price=4600.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(i7\s*14700k[f]?|i7\s*13700k[f]?)\b", re.IGNORECASE),
        model_name="Intel Core i7 14700K / 13700K",
        baseline_price=2800.0,
        great_deal_price=2250.0,
        max_normal_price=3100.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(i5\s*14600k[f]?|i5\s*13600k[f]?)\b", re.IGNORECASE),
        model_name="Intel Core i5 14600K / 13600K",
        baseline_price=1900.0,
        great_deal_price=1500.0,
        max_normal_price=2100.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(i5\s*12400f|i5\s*13400f|i5\s*14400f)\b", re.IGNORECASE),
        model_name="Intel Core i5 12400F / 13400F",
        baseline_price=750.0,
        great_deal_price=560.0,
        max_normal_price=850.0,
    ),

    # --- Storage (SSDs) ---
    HardwareReference(
        pattern=re.compile(r"\b(ssd\b.*\b4\s*tb|4\s*tb\b.*\bssd)\b", re.IGNORECASE),
        model_name="SSD NVMe 4TB",
        baseline_price=1800.0,
        great_deal_price=1380.0,
        max_normal_price=2100.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(ssd\b.*\b2\s*tb|2\s*tb\b.*\bssd)\b", re.IGNORECASE),
        model_name="SSD NVMe 2TB",
        baseline_price=850.0,
        great_deal_price=640.0,
        max_normal_price=980.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(ssd\b.*\b1\s*tb|1\s*tb\b.*\bssd|1000\s*gb\b.*\bssd)\b", re.IGNORECASE),
        model_name="SSD NVMe 1TB",
        baseline_price=450.0,
        great_deal_price=320.0,
        max_normal_price=520.0,
    ),

    # --- Consoles ---
    HardwareReference(
        pattern=re.compile(r"\b(playstation\s*5\s*pro|ps5\s*pro)\b", re.IGNORECASE),
        model_name="PlayStation 5 Pro",
        baseline_price=6500.0,
        great_deal_price=5600.0,
        max_normal_price=6990.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(playstation\s*5|ps5)\b", re.IGNORECASE),
        model_name="PlayStation 5",
        baseline_price=3700.0,
        great_deal_price=3100.0,
        max_normal_price=4000.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(xbox\s*series\s*x)\b", re.IGNORECASE),
        model_name="Xbox Series X",
        baseline_price=4200.0,
        great_deal_price=3450.0,
        max_normal_price=4600.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(xbox\s*series\s*s)\b", re.IGNORECASE),
        model_name="Xbox Series S",
        baseline_price=2500.0,
        great_deal_price=1950.0,
        max_normal_price=2750.0,
    ),
    HardwareReference(
        pattern=re.compile(r"\b(nintendo\s*switch\s*oled)\b", re.IGNORECASE),
        model_name="Nintendo Switch OLED",
        baseline_price=2100.0,
        great_deal_price=1650.0,
        max_normal_price=2300.0,
    ),
]


# =========================
# CORE VALIDATION LOGIC
# =========================

def match_hardware_reference(title: str) -> Optional[HardwareReference]:
    """Extract matching hardware reference pattern from product title."""
    for ref in _HARDWARE_REFERENCES:
        if ref.pattern.search(title):
            return ref
    return None


def validate_deal(deal: dict) -> DealValidationResult:
    """
    Intelligent deal validator. Checks for:
    1. Inflation of 'was/original' price ('Metade do dobro').
    2. Overpriced products advertised with fake store discounts.
    3. Calculates REAL discount percentage relative to market baseline.
    """
    title = deal.get("title", "")
    current_price = float(deal.get("price") or 0.0)
    claimed_original_price = float(deal.get("original_price") or 0.0)
    store = deal.get("store", "Loja")
    
    # Calculate claimed discount
    claimed_discount_pct = 0.0
    if claimed_original_price > current_price > 0:
        claimed_discount_pct = (1.0 - current_price / claimed_original_price) * 100.0
    elif deal.get("discount_pct"):
        claimed_discount_pct = float(deal["discount_pct"])

    # Try pattern match against known Brazilian hardware database
    ref = match_hardware_reference(title)

    if ref:
        matched_model = ref.model_name
        baseline = ref.baseline_price
        great_deal_threshold = ref.great_deal_price
        max_normal = ref.max_normal_price

        # Real discount relative to estimated market baseline
        real_discount_pct = ((baseline - current_price) / baseline) * 100.0

        # Check 1: Is store original price absurdly inflated above market baseline?
        # e.g. Store says "De R$ 12.300 por R$ 3.700" for an RTX 4060 Ti (baseline R$ 2.700)
        price_inflation_detected = (
            claimed_original_price > (1.35 * baseline)
            and claimed_original_price > (1.25 * max_normal)
        )

        # Check 2: Is the current price actually OVERPRICED compared to market baseline?
        # User prompt example: RTX 5060 Ti advertised for R$ 3.700 claiming 70% OFF.
        # Baseline is R$ 2.700. Current price R$ 3.700 is 37% ABOVE baseline!
        if current_price > max_normal:
            pct_over = round(((current_price - baseline) / baseline) * 100.0, 1)
            reason = (
                f"Falso desconto ('Metade do Dobro'): {matched_model} anunciado por "
                f"R$ {current_price:,.2f} com '{claimed_discount_pct:.0f}% OFF' falso. "
                f"Preço médio de mercado é R$ {baseline:,.2f} (anunciado está +{pct_over}% acima)."
            ).replace(",", "X").replace(".", ",").replace("X", ".")
            
            return DealValidationResult(
                is_valid_deal=False,
                verdict_code=DealVerdictCode.FAKE_DISCOUNT,
                verdict_badge="⚠️ **PROMOÇÃO ENGANOSA**",
                real_discount_pct=real_discount_pct,
                claimed_discount_pct=claimed_discount_pct,
                expected_market_price=baseline,
                great_deal_price=great_deal_threshold,
                price_inflation_detected=price_inflation_detected,
                rejection_reason=reason,
                confidence_score=0.98,
                matched_model=matched_model,
            )

        # Check 3: Current price is not overpriced, but original price was heavily inflated ("Metade do dobro")
        # e.g., Store listed "De R$ 6.000 por R$ 2.650" (claimed 55% OFF), real price is R$ 2.650 (just market average, 2% OFF)
        if price_inflation_detected and real_discount_pct < 5.0:
            reason = (
                f"Falso desconto ('Metade do Dobro'): Loja inflacionou preço original (de R$ {claimed_original_price:,.2f}). "
                f"Preço real de R$ {current_price:,.2f} é o preço normal de mercado (R$ {baseline:,.2f}), sem oferta real."
            ).replace(",", "X").replace(".", ",").replace("X", ".")

            return DealValidationResult(
                is_valid_deal=False,
                verdict_code=DealVerdictCode.METADE_DO_DOBRO,
                verdict_badge="⚠️ **PREÇO INFLACIONADO**",
                real_discount_pct=real_discount_pct,
                claimed_discount_pct=claimed_discount_pct,
                expected_market_price=baseline,
                great_deal_price=great_deal_threshold,
                price_inflation_detected=True,
                rejection_reason=reason,
                confidence_score=0.95,
                matched_model=matched_model,
            )

        # Check 4: Valid deals with verdict assignment based on REAL discount
        if current_price <= great_deal_threshold or real_discount_pct >= 18.0:
            badge = "⚡ **OPORTUNIDADE IMPERDÍVEL**"
            verdict = DealVerdictCode.ULTRA_DEAL
        elif real_discount_pct >= 8.0:
            badge = "🔥 **OFERTA REAL**"
            verdict = DealVerdictCode.REAL_DEAL
        else:
            badge = "✅ **PREÇO JUSTO**"
            verdict = DealVerdictCode.FAIR_PRICE

        return DealValidationResult(
            is_valid_deal=True,
            verdict_code=verdict,
            verdict_badge=badge,
            real_discount_pct=real_discount_pct,
            claimed_discount_pct=claimed_discount_pct,
            expected_market_price=baseline,
            great_deal_price=great_deal_threshold,
            price_inflation_detected=price_inflation_detected,
            confidence_score=0.95,
            matched_model=matched_model,
        )

    # --- Heuristic Fallback (for generic products without exact model match) ---

    # Heuristic 1: If original price > 3.0 * current price (e.g. "De 10.000 por 1.000") without metrics
    price_inflation_detected = (
        claimed_original_price > 0 and claimed_original_price > 2.8 * current_price
    )
    if price_inflation_detected and claimed_discount_pct > 65.0:
        reason = (
            f"Falso desconto detectado: Loja alega {claimed_discount_pct:.0f}% OFF "
            f"(de R$ {claimed_original_price:,.2f} por R$ {current_price:,.2f}) com preço original desproporcional."
        ).replace(",", "X").replace(".", ",").replace("X", ".")
        return DealValidationResult(
            is_valid_deal=False,
            verdict_code=DealVerdictCode.FAKE_DISCOUNT,
            verdict_badge="⚠️ **DESCONTO SUSPEITO**",
            real_discount_pct=claimed_discount_pct * 0.5,
            claimed_discount_pct=claimed_discount_pct,
            expected_market_price=None,
            great_deal_price=None,
            price_inflation_detected=True,
            rejection_reason=reason,
            confidence_score=0.80,
        )

    # Generic pass with default confidence
    return DealValidationResult(
        is_valid_deal=True,
        verdict_code=DealVerdictCode.REAL_DEAL if claimed_discount_pct >= 25 else DealVerdictCode.FAIR_PRICE,
        verdict_badge="🔥 **OFERTA CONFIRMADA**" if claimed_discount_pct >= 25 else "✅ **PREÇO DE MERCADO**",
        real_discount_pct=claimed_discount_pct,
        claimed_discount_pct=claimed_discount_pct,
        expected_market_price=None,
        great_deal_price=None,
        price_inflation_detected=False,
        confidence_score=0.75,
    )


# =========================
# OPENROUTER AI FALLBACK
# =========================

async def evaluate_deal_with_ai(deal: dict) -> DealValidationResult:
    """
    Asynchronously queries OpenRouter AI (via AIProviderEngine) to evaluate deal 
    authenticity for unindexed or ambiguous products in the Brazilian market.
    """
    # First run rule-based validator
    rule_res = validate_deal(deal)
    if rule_res.matched_model or rule_res.confidence_score >= 0.90:
        return rule_res

    title = deal.get("title", "")
    price = deal.get("price", 0)
    orig_price = deal.get("original_price", 0)
    store = deal.get("store", "")
    category = deal.get("category", "")

    prompt = (
        f"Você é um especialista em hardware, tech e e-commerce no Brasil. "
        f"Avalie se a promoção a seguir é REAL ou um FALSO DESCONTO ('metade do dobro').\n"
        f"Produto: {title}\n"
        f"Preço Anunciado: R$ {price}\n"
        f"Preço Original Alegado (De): R$ {orig_price}\n"
        f"Loja: {store}\n"
        f"Categoria: {category}\n\n"
        f"Responda SOMENTE em formato JSON válido:\n"
        f"{{\n"
        f'  "is_valid": true/false,\n'
        f'  "estimated_market_price_brl": float,\n'
        f'  "is_fake_discount": true/false,\n'
        f'  "verdict_reason": "explicação curta em português"\n'
        f"}}\n"
    )

    try:
        from tiffany_core.ai.ai_provider import AIProviderEngine
        engine = AIProviderEngine(default_timeout_sec=4.0)
        
        loop = asyncio.get_running_loop()
        response_text = await loop.run_in_executor(
            None,
            lambda: engine.generate(
                prompt=prompt,
                system_instruction="Você é o validador de preços antifraude da Tiffany Bot.",
                temperature=0.1,
                max_tokens=200
            )
        )

        clean_json = response_text.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()

        data = json.loads(clean_json)
        is_valid = bool(data.get("is_valid", True))
        est_market = float(data.get("estimated_market_price_brl") or price)
        is_fake = bool(data.get("is_fake_discount", False))
        reason = str(data.get("verdict_reason", ""))

        if is_fake or not is_valid:
            return DealValidationResult(
                is_valid_deal=False,
                verdict_code=DealVerdictCode.FAKE_DISCOUNT,
                verdict_badge="⚠️ **FALSO DESCONTO (IA)**",
                real_discount_pct=max(0.0, ((est_market - price) / est_market) * 100.0) if est_market else 0.0,
                claimed_discount_pct=rule_res.claimed_discount_pct,
                expected_market_price=est_market,
                great_deal_price=est_market * 0.85,
                price_inflation_detected=True,
                rejection_reason=f"Análise de IA: {reason}",
                confidence_score=0.88,
            )

    except Exception as e:
        log.warning(f"AI deal evaluation fallback skipped: {e}")
        note = " [AI Validation Failed]"
        if note not in rule_res.rejection_reason:
            rule_res.rejection_reason = (rule_res.rejection_reason + note).strip()

    return rule_res
