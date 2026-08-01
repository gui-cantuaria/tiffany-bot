"""
Tiffany OS — Centralized Policy Engine (Enterprise RBAC & ABAC Governance)
==========================================================================
Decouples complex decision rules (entitlements, GDPR residency, budgets, moderation)
from UI and service layers into an explainable, auditable central governance engine.
"""

from __future__ import annotations
import logging
import time
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

log = logging.getLogger("tiffany.core.security.policy")

@dataclass
class EvaluationContext:
    tenant_id: int
    user_id: int
    tier: str = "free"  # 'free', 'pro', 'enterprise'
    ai_tokens_used_today: int = 0
    ai_token_budget: int = 25000
    is_eu_region: bool = False
    nsfw_requested: bool = False
    is_voice_channel: bool = False
    is_admin: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PolicyEvaluationResult:
    allowed: bool
    policy_name: str
    reason: str
    evaluated_at_epoch: float = field(default_factory=time.time)
    denied_code: Optional[str] = None

class CentralPolicyEngine:
    """
    Centralized governance arbitrator. Evaluates requests against declarative rules
    to ensure compliance with business tiers, AI budgets, and legal regimes (GDPR/LGPD).
    """
    def __init__(self) -> None:
        # Pre-compiled rule evaluators mapped by policy topic
        self._policy_registry = {
            "ai:inference": self._eval_ai_inference,
            "ai:premium_model": self._eval_premium_ai,
            "feature:music_24_7": self._eval_music_24_7,
            "privacy:store_long_term_memory": self._eval_store_memory,
            "admin:manage_guild_os": self._eval_admin_manage
        }

    def evaluate(self, context: EvaluationContext, policy_name: str) -> PolicyEvaluationResult:
        evaluator = self._policy_registry.get(policy_name)
        if not evaluator:
            # Default Fail-Closed for unhandled or unknown policies!
            log.warning("[PolicyEngine] Unknown policy '%s' -> Fail-Closed default executed", policy_name)
            return PolicyEvaluationResult(
                allowed=False,
                policy_name=policy_name,
                reason="Política de segurança desconhecida ou não registrada (Fail-Closed).",
                denied_code="ERR_UNKNOWN_POLICY"
            )
        
        result = evaluator(context)
        log.debug("[PolicyEngine: %s] Tenant %d -> Allowed=%s (%s)", 
                  policy_name, context.tenant_id, result.allowed, result.reason)
        return result

    def _eval_ai_inference(self, ctx: EvaluationContext) -> PolicyEvaluationResult:
        if ctx.nsfw_requested:
            return PolicyEvaluationResult(
                False, "ai:inference", "Conteúdo adulto/NSFW é terminantemente proibido pelo motor cognitivo.",
                denied_code="ERR_SAFETY_POLICY_VIOLATION"
            )
        if ctx.ai_tokens_used_today >= ctx.ai_token_budget:
            return PolicyEvaluationResult(
                False, "ai:inference", "Orçamento diário de tokens de IA esgotado para o seu plano.",
                denied_code="ERR_BUDGET_EXCEEDED"
            )
        return PolicyEvaluationResult(True, "ai:inference", "Inferência de IA permitida.")

    def _eval_premium_ai(self, ctx: EvaluationContext) -> PolicyEvaluationResult:
        if ctx.tier.lower() not in ["pro", "enterprise"]:
            return PolicyEvaluationResult(
                False, "ai:premium_model", "Modelos de IA de alta densidade requerem plano Pro ou Enterprise.",
                denied_code="ERR_UPGRADE_REQUIRED"
            )
        return self._eval_ai_inference(ctx)

    def _eval_music_24_7(self, ctx: EvaluationContext) -> PolicyEvaluationResult:
        if ctx.tier.lower() not in ["pro", "enterprise"]:
            return PolicyEvaluationResult(
                False, "feature:music_24_7", "Transmissão ininterrupta 24/7 requer plano Pro ou Enterprise.",
                denied_code="ERR_UPGRADE_REQUIRED"
            )
        return PolicyEvaluationResult(True, "feature:music_24_7", "Modo 24/7 liberado.")

    def _eval_store_memory(self, ctx: EvaluationContext) -> PolicyEvaluationResult:
        # In EU jurisdiction, explicit GDPR opt-in flag in metadata is required for persistent memory
        if ctx.is_eu_region and not ctx.metadata.get("gdpr_explicit_consent", False):
            return PolicyEvaluationResult(
                False, "privacy:store_long_term_memory", "Armazenamento de longo prazo suspenso (GDPR Opt-in Ausente).",
                denied_code="ERR_GDPR_CONSENT_REQUIRED"
            )
        return PolicyEvaluationResult(True, "privacy:store_long_term_memory", "Conformidade de memória verificada.")

    def _eval_admin_manage(self, ctx: EvaluationContext) -> PolicyEvaluationResult:
        if not ctx.is_admin and ctx.tier.lower() != "enterprise":
            return PolicyEvaluationResult(
                False, "admin:manage_guild_os", "Privilégios de Administrador da Comunidade requeridos.",
                denied_code="ERR_UNAUTHORIZED_ROLE"
            )
        return PolicyEvaluationResult(True, "admin:manage_guild_os", "Acesso administrativo concedido.")

policy_engine = CentralPolicyEngine()
