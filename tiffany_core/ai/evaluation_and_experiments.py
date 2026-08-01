"""
Tiffany OS — Experimentation Platform & AI Quality Evaluation Tracker
=====================================================================
Enables controlled UX and cognitive experimentation via stable variant assignment without
process restarts. Tracks AI accuracy, latency percentiles, and hallucination risks over time
to automatically flag regressions before wide enterprise distribution.
"""

from __future__ import annotations
import hashlib
import logging
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

log = logging.getLogger("tiffany.core.ai.evaluation")

@dataclass
class ExperimentDefinition:
    exp_key: str
    hypothesis: str
    variants: List[str]  # e.g. ["control", "variant_apple_style", "variant_linear_polish"]
    weights: List[int]   # e.g. [50, 25, 25] (must sum to 100)
    success_metric: str
    is_active: bool = True
    created_at: float = field(default_factory=time.time)

class ExperimentationPlatform:
    """
    Stable A/B and canary testing facility. Ensures users experience consistent visual
    and behavior variants without storing session tokens or modifying database schema.
    """
    def __init__(self) -> None:
        self._experiments: Dict[str, ExperimentDefinition] = {}
        self._metric_tallies: Dict[str, Dict[str, int]] = {}

    def create_experiment(self, exp: ExperimentDefinition) -> None:
        if sum(exp.weights) != 100:
            raise ValueError("Experiment variant weights must sum exactly to 100.")
        self._experiments[exp.exp_key] = exp
        self._metric_tallies[exp.exp_key] = {var: 0 for var in exp.variants}
        log.info("[ExperimentPlatform] Registered experiment '%s': %s", exp.exp_key, exp.variants)

    def assign_variant(self, exp_key: str, entity_id: int) -> str:
        exp = self._experiments.get(exp_key)
        if not exp or not exp.is_active:
            return "control"
            
        hash_val = int(hashlib.md5(f"{exp_key}:{entity_id}".encode("utf-8")).hexdigest()[:8], 16)
        percentile = (hash_val % 100) + 1  # 1 to 100
        
        cumulative = 0
        for idx, var in enumerate(exp.variants):
            cumulative += exp.weights[idx]
            if percentile <= cumulative:
                return var
        return exp.variants[0]

    def record_success(self, exp_key: str, assigned_variant: str) -> None:
        if exp_key in self._metric_tallies and assigned_variant in self._metric_tallies[exp_key]:
            self._metric_tallies[exp_key][assigned_variant] += 1
            log.debug("[ExperimentPlatform] Recorded hit for '%s' -> %s (total: %d)", 
                      exp_key, assigned_variant, self._metric_tallies[exp_key][assigned_variant])

    def get_results(self, exp_key: str) -> Dict[str, int]:
        return self._metric_tallies.get(exp_key, {})


# =============================================================================
# Autonomous AI Quality & Regression Tracker
# =============================================================================

@dataclass
class CognitiveInteractionRecord:
    prompt_hash: str
    model: str
    latency_ms: float
    confidence_score: float
    was_fallback: bool
    had_hallucination_risk: bool
    timestamp_epoch: float = field(default_factory=time.time)

class AIEvaluationTracker:
    """
    Observes cognitive execution streams to establish Quality SLI benchmarks and detect
    silent accuracy regressions across prompt versions or model iterations.
    """
    def __init__(self) -> None:
        self._records: List[CognitiveInteractionRecord] = []
        self.regression_alert_threshold: float = 0.80  # Alert if trailing confidence drops below 80%

    def track(self, model: str, latency: float, confidence: float, 
              fallback: bool = False, hallucination_risk: bool = False) -> None:
        rec = CognitiveInteractionRecord(
            prompt_hash=uuid_compat_hash(f"{model}:{time.time()}"),
            model=model,
            latency_ms=latency,
            confidence_score=confidence,
            was_fallback=fallback,
            had_hallucination_risk=hallucination_risk
        )
        self._records.append(rec)
        if len(self._records) > 5000:
            self._records = self._records[-2500:]
            
        # Real-time quality regression evaluation
        self._check_regression_alert()

    def _check_regression_alert(self) -> None:
        if len(self._records) < 10:
            return
        trailing = self._records[-20:]
        avg_conf = sum(r.confidence_score for r in trailing) / len(trailing)
        if avg_conf < self.regression_alert_threshold:
            log.warning("⚠️ [AIEvaluationTracker: Regression Alert] Trailing confidence dropped to %.2f! Inspect prompts/models.", avg_conf)

    def generate_quality_scorecard(self) -> Dict[str, Any]:
        if not self._records:
            return {"status": "no_data"}
        total = len(self._records)
        avg_lat = round(sum(r.latency_ms for r in self._records) / total, 2)
        avg_conf = round(sum(r.confidence_score for r in self._records) / total, 4)
        fallbacks = sum(1 for r in self._records if r.was_fallback)
        hallucinations = sum(1 for r in self._records if r.had_hallucination_risk)
        return {
            "total_evaluations": total,
            "average_latency_ms": avg_lat,
            "mean_confidence_score": avg_conf,
            "fallback_rate_pct": round((fallbacks / total) * 100.0, 2),
            "hallucination_flag_rate_pct": round((hallucinations / total) * 100.0, 2),
            "quality_status": "ENTERPRISE_PASS" if avg_conf >= 0.88 else "ATTENTION_REQUIRED"
        }

def uuid_compat_hash(val: str) -> str:
    return hashlib.md5(val.encode("utf-8")).hexdigest()[:12]

experiment_platform = ExperimentationPlatform()
ai_eval_tracker = AIEvaluationTracker()
