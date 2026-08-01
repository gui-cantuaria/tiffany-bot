"""
Tiffany OS — Intelligent AI Rerouting Engine & Cost Optimizer
============================================================
Implements dynamic intent classification to route casual queries to ultra-efficient
models (Flash-Lite / Llama-3) while reserving deep analytical models (Sonnet / Opus)
strictly for complex reasoning and multi-step planning tasks.
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass
from tiffany_core.domain.events import domain_event_bus, AIInferenceCompleted
from tiffany_core.ai.ai_provider import ai_provider_engine

log = logging.getLogger("tiffany.core.ai.router")

@dataclass
class ModelRouteConfig:
    model_name: str
    cost_per_1k_tokens: float
    max_tokens: int
    is_reasoning_heavy: bool
    description: str

MODELS: Dict[str, ModelRouteConfig] = {
    "flash_lite": ModelRouteConfig("google/gemini-3.1-flash-lite", 0.0001, 4096, False, "Ultra-fast low-cost model for simple queries"),
    "flash": ModelRouteConfig("google/gemini-3.1-flash", 0.0003, 8192, False, "Balanced conversational model"),
    "gpt_4o_mini": ModelRouteConfig("openai/gpt-4o-mini", 0.0005, 8192, False, "Advanced fast model"),
    "claude_sonnet": ModelRouteConfig("anthropic/claude-3.5-sonnet", 0.0030, 8192, True, "Complex reasoning and multi-step planning"),
    "gpt_5_opus": ModelRouteConfig("openai/gpt-5-opus", 0.0150, 16384, True, "State-of-the-art analytical intelligence"),
}

class IntentClassifier:
    """
    Evaluates prompt semantics and token density to classify query complexity.
    Prevents simple greetings or basic status lookups from draining expensive model quotas.
    """
    COMPLEX_KEYWORDS = {
        "analyze", "audit", "compare", "debug", "refactor", "summarize", 
        "architecture", "strategy", "roadmap", "eval", "explain why", 
        "analisar", "auditar", "comparar", "resumir", "arquitetura", "estratégia"
    }

    @classmethod
    def classify(cls, prompt: str, history_len: int = 0) -> str:
        prompt_lower = prompt.strip().lower()
        word_count = len(prompt_lower.split())
        
        # Simple greetings or very short inquiries route immediately to flash_lite
        if word_count <= 8 and not any(kw in prompt_lower for kw in cls.COMPLEX_KEYWORDS):
            return "simple"
            
        # Complex multi-step instructions or heavy historical contexts route to planning models
        if any(kw in prompt_lower for kw in cls.COMPLEX_KEYWORDS) or word_count > 120 or history_len > 15:
            return "complex"
            
        return "standard"

class AIRoutingEngine:
    """
    Orchestrates intelligent model selection, validation, and cost tracking.
    """
    def __init__(self) -> None:
        self.total_saved_usd: float = 0.0
        self.total_requests: int = 0

    async def route_and_execute(
        self, 
        user_id: int, 
        guild_id: int, 
        prompt: str, 
        requested_model: Optional[str] = None,
        history_len: int = 0,
        correlation_id: str = ""
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()
        self.total_requests += 1

        # 1. Intent Classification
        complexity = IntentClassifier.classify(prompt, history_len)
        
        # 2. Dynamic Router Decision
        selected_model_key = requested_model or self._select_model_for_complexity(complexity)
        if selected_model_key not in MODELS:
            selected_model_key = "flash_lite"
            
        target_model = MODELS[selected_model_key]
        
        # 3. Execute Model via AI Provider Engine with resilient retry
        provider_res = await ai_provider_engine.generate_completion(
            prompt=prompt,
            model=target_model.model_name,
            max_tokens=target_model.max_tokens
        )
        
        # Calculate exact token usage and financial impact
        usage = provider_res.get("usage", {})
        estimated_prompt_tokens = usage.get("prompt_tokens", max(10, len(prompt) // 4))
        estimated_completion_tokens = usage.get("completion_tokens", 150 if complexity == "simple" else 650)
        total_tokens = estimated_prompt_tokens + estimated_completion_tokens
        
        actual_cost = (total_tokens / 1000.0) * target_model.cost_per_1k_tokens
        
        # Calculate what cost would have been if blindly routed to gpt-5-opus / sonnet
        max_cost = (total_tokens / 1000.0) * MODELS["gpt_5_opus"].cost_per_1k_tokens
        savings = max(0.0, max_cost - actual_cost)
        self.total_saved_usd += savings
        
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # 4. Dispatch Immutable Telemetry Event
        event = AIInferenceCompleted(
            user_id=user_id,
            guild_id=guild_id,
            model=target_model.model_name,
            prompt_tokens=estimated_prompt_tokens,
            completion_tokens=estimated_completion_tokens,
            cost_usd=actual_cost,
            latency_ms=latency_ms,
            cached=False,
            correlation_id=correlation_id
        )
        await domain_event_bus.publish(event)
        
        log.info("AI Route complete. Complexity: %s | Model: %s | Cost: $%.5f | Saved vs Opus: $%.5f", 
                 complexity, selected_model_key, actual_cost, savings)
                 
        return {
            "model_used": provider_res.get("model_used", target_model.model_name),
            "content": provider_res.get("content", ""),
            "is_fallback": provider_res.get("is_fallback", False),
            "complexity": complexity,
            "cost_usd": actual_cost,
            "saved_usd": savings,
            "latency_ms": latency_ms,
            "status": provider_res.get("status", "success")
        }

    def _select_model_for_complexity(self, complexity: str) -> str:
        if complexity == "simple":
            return "flash_lite"
        elif complexity == "complex":
            return "claude_sonnet"
        return "flash"

# Global routing engine instance
ai_router = AIRoutingEngine()
