import pytest
from tiffany_core.reliability.resilience import openrouter_breaker, lavalink_breaker
from tiffany_core.ai.ai_provider import ai_provider_engine

@pytest.fixture(autouse=True)
def reset_global_resilience_state():
    """
    Autouse fixture that ensures clean state for global circuit breakers and provider engines
    across all test executions, preventing cross-suite test pollution.
    """
    openrouter_breaker.reset()
    lavalink_breaker.reset()
    ai_provider_engine.set_custom_transport(None)
    yield
    openrouter_breaker.reset()
    lavalink_breaker.reset()
    ai_provider_engine.set_custom_transport(None)
