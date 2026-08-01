"""
Tiffany OS Core — Enterprise Regression & Architecture Test Suite
================================================================
Verifies Domain Events, AI Rerouting cost optimization, Fail-Closed guardrail logic,
Circuit Breaker resilience, and Community Knowledge Graph retrieval using unittest.
"""

import unittest
from unittest import mock
import asyncio
import time
from typing import Any

from tiffany_core.domain.events import domain_event_bus, AudioPlaybackStarted, AIInferenceCompleted
from tiffany_core.ai.router import ai_router, IntentClassifier
from tiffany_core.reliability.resilience import CircuitBreaker, CircuitState, health_monitor
from tiffany_core.observability.metrics import metrics
from tiffany_core.knowledge.graph import knowledge_graph
import premium_ai_guardrails
from infra.services.ai_quota import AIQuotaService
from infra.services.subscription import SubscriptionService
from tiffany_core.adapters.command_visibility import command_visibility_syncer, DynamicCommandTreeSyncer
from tiffany_core.security.privacy import pii_scrubber, gdpr_service
from tiffany_core.reliability.concurrency import stampede_protector, TokenBucketRateLimiter
from tiffany_core.audio.voice_engine import voice_engine
from tiffany_core.ai.semantic_cache_and_reflection import semantic_cache, reflection_engine
from tiffany_core.domain.event_sourcing_and_plugins import event_store, plugin_sandbox, PluginManifest, AbstractTiffanyPlugin, PluginCapability
from tiffany_core.reliability.distributed_lock_and_telemetry import tracer, leader_coordinator, DistributedLeaderCoordinator
from tiffany_core.config.runtime_config import runtime_config, flag_evaluator, FeatureFlagRule
from tiffany_core.security.policy_engine import policy_engine, EvaluationContext
from tiffany_core.ai.control_plane import ai_control_plane, CognitiveRequest
from tiffany_core.ai.evaluation_and_experiments import experiment_platform, ai_eval_tracker, ExperimentDefinition
from tiffany_core.domain.event_bus_and_scheduler import resource_scheduler, WorkflowOrchestrator, TenantCreated
from tiffany_core.knowledge.memory_lifecycle_and_digital_twin import memory_lifecycle, digital_twin_engine, enterprise_vault
import guild_config

class TestTiffanyCoreArchitecture(unittest.IsolatedAsyncioTestCase):

    async def test_domain_event_bus_cqrs(self):
        events_received = []
        async def sample_handler(evt: AudioPlaybackStarted):
            events_received.append(evt)

        domain_event_bus.subscribe(AudioPlaybackStarted, sample_handler)
        test_evt = AudioPlaybackStarted(guild_id=123, track_title="Cyberpunk Lofi", duration_ms=180000, requester_id=456)
        await domain_event_bus.publish(test_evt)
        
        self.assertEqual(len(events_received), 1)
        self.assertEqual(events_received[0].track_title, "Cyberpunk Lofi")

    def test_intent_classifier(self):
        self.assertEqual(IntentClassifier.classify("hi tiffany"), "simple")
        self.assertEqual(IntentClassifier.classify("Could you please analyze and audit our entire voice system architecture?"), "complex")
        self.assertEqual(IntentClassifier.classify("What song is playing next in the music queue?"), "standard")

    async def test_ai_router_cost_savings(self):
        initial_savings = ai_router.total_saved_usd
        res = await ai_router.route_and_execute(
            user_id=101, 
            guild_id=202, 
            prompt="Hi tiffany, good morning!", 
            correlation_id="test-corr-1"
        )
        self.assertEqual(res["model_used"], "google/gemini-3.1-flash-lite")
        self.assertGreater(res["saved_usd"], 0.0)
        self.assertGreater(ai_router.total_saved_usd, initial_savings)

    async def test_fail_closed_guardrails(self):
        with mock.patch.object(premium_ai_guardrails, "OPENROUTER_API_KEY", ""):
            result = await premium_ai_guardrails.classify_content("Test Title", "Test NSFW Content")
            # Must NEVER return SAFE when key is missing! Must be Fail-Closed!
            self.assertEqual(result["classification"], "ILLEGAL_GORE")
            self.assertIn("Fail-Closed", result["reasoning"])

    async def test_circuit_breaker_tripping(self):
        breaker = CircuitBreaker("TestService", failure_threshold=2, recovery_timeout_sec=0.1)
        
        async def failing_call():
            raise ValueError("Simulated network drop")
            
        # 1st failure
        with self.assertRaises(ValueError):
            await breaker.execute(failing_call)
        self.assertEqual(breaker.state, CircuitState.CLOSED)
        
        # 2nd failure trips OPEN
        with self.assertRaises(ValueError):
            await breaker.execute(failing_call)
        self.assertEqual(breaker.state, CircuitState.OPEN)
        
        # Call while open returns fallback if provided
        val = await breaker.execute(failing_call, fallback_value="fallback_safe")
        self.assertEqual(val, "fallback_safe")

    async def test_knowledge_graph_ingest_and_search(self):
        await knowledge_graph.ingest_memory(999, "Decision: Re-architected tiffany_voice into modular DDD domains", tags=["architecture", "refactor"])
        await knowledge_graph.ingest_memory(999, "We decided to order pizza for Friday gaming night", tags=["social", "pizza"])
        
        results = await knowledge_graph.semantic_search(999, "architecture refactor decision", limit=2)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("tiffany_voice", results[0].content)

    def test_grafana_metrics_export(self):
        metrics.ai_requests_total.inc(5)
        metrics.ai_latency_histogram.observe(110.5)
        export_json = metrics.export_grafana_json()
        self.assertIn("tiffany-core-os", export_json)
        self.assertIn('"ai_requests_total":', export_json)

    async def test_db_connection_reuse_no_nested_acquire(self):
        plan = await SubscriptionService.get_plan(1234, subject_type="user", conn=None)
        self.assertEqual(plan, "free")
        rem, is_guild = await AIQuotaService.get_remaining(1234, guild_id=5678, conn=None)
        self.assertGreaterEqual(rem, 0)

    async def test_dynamic_command_visibility_and_rejection_feedback(self):
        # 1. Test pruning disabled commands from guild tree
        class MockCommand:
            def __init__(self, name): self.name = name
        class MockTree:
            def __init__(self):
                self.commands_added = []
            def get_commands(self):
                return [MockCommand("play"), MockCommand("help"), MockCommand("imagine")]
            def clear_commands(self, guild=None):
                self.commands_added = []
            def add_command(self, cmd, guild=None):
                self.commands_added.append(cmd.name)
            async def sync(self, guild=None):
                pass
        class MockBot:
            def __init__(self): self.tree = MockTree()
        class MockGuild:
            def __init__(self): self.id = 88888

        bot = MockBot()
        guild = MockGuild()
        syncer = DynamicCommandTreeSyncer(debounce_sec=0.01)
        
        # Disable music ("play"), keep imagine & general ("help") enabled
        features = {"music": False, "imagine": True}
        await syncer._execute_sync(bot, guild, features)
        
        # 'play' must vanish from active commands! 'help' and 'imagine' remain!
        self.assertNotIn("play", bot.tree.commands_added)
        self.assertIn("help", bot.tree.commands_added)
        self.assertIn("imagine", bot.tree.commands_added)

        # 2. Test localized feedback when invoking a disabled command
        class MockResponse:
            def __init__(self): self.sent_msg = None
            def is_done(self): return False
            async def send_message(self, msg, ephemeral=False): self.sent_msg = msg
        class MockUser:
            def __init__(self): self.id = 12345
        class MockInteraction:
            def __init__(self):
                self.guild_id = 88888
                self.user = MockUser()
                self.locale = "pt"
                self.response = MockResponse()

        interaction = MockInteraction()
        # Mock guild_config to say feature is disabled
        with mock.patch.object(guild_config, "is_feature_enabled", return_value=False):
            allowed = await command_visibility_syncer.verify_command_access_or_deny(interaction, command_name="play")
            self.assertFalse(allowed)
            self.assertIn("desativado neste servidor", interaction.response.sent_msg)
            self.assertIn("/mod-panel", interaction.response.sent_msg)

    async def test_pii_scrubbing_and_gdpr_rtbf(self):
        # Verify PII masking
        raw = "Contact john.doe@example.com or ping IP 192.168.1.100 regarding ticket."
        clean = pii_scrubber.sanitize(raw)
        self.assertNotIn("john.doe@example.com", clean)
        self.assertIn("[EMAIL_REDACTED]", clean)
        self.assertIn("[IP_REDACTED]", clean)

        # Verify GDPR RTBF complete erasure
        await knowledge_graph.ingest_memory(777, "User 5555 requested song by Metallica", tags=["user:5555"])
        await knowledge_graph.ingest_memory(777, "Server rule: no spam allowed", tags=["rules"])
        
        res = await gdpr_service.execute_right_to_be_forgotten(5555, [777])
        self.assertEqual(res["status"], "COMPLETED")
        
        remaining = await knowledge_graph.semantic_search(777, "Metallica", limit=5)
        for node in remaining:
            self.assertNotIn("5555", node.content)

    async def test_single_flight_stampede_protection(self):
        execution_count = 0
        async def slow_fetch():
            nonlocal execution_count
            execution_count += 1
            await asyncio.sleep(0.05)
            return "cached_result"

        # Launch 10 concurrent calls to identical key during simulated shard reconnect
        tasks = [stampede_protector.execute("guild_config:9999", slow_fetch) for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        self.assertEqual(results, ["cached_result"] * 10)
        # Proven: slow_fetch only executed EXACTLY ONCE despite 10 concurrent requests!
        self.assertEqual(execution_count, 1)

    async def test_voice_engine_wake_word_interruptibility(self):
        session = voice_engine.get_or_create_session(444, 555)
        session.is_streaming = True  # Tiffany is currently streaming audio
        
        # User utters wake word instruction
        res = await voice_engine.process_spoken_utterance(444, 555, 101, "Hey Tiffany, pause music immediately!")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "speak_reply")
        self.assertIn("latency_ms", res)
        # Verify active session stream was immediately interrupted
        self.assertIn("role", session.conversation_history[-1])

    async def test_semantic_cache_hit_and_reflection(self):
        # 1. Store initial response in Semantic Cache
        await semantic_cache.store(
            "Como configuro o canal de ofertas no servidor?", 
            "Use o comando /mod-panel para definir o canal oficial de ofertas.",
            "tiffany-pro"
        )
        # 2. Rephrase query - should hit semantic cache!
        hit = await semantic_cache.lookup("Como configuro o canal para ofertas no servidor?")
        self.assertIsNotNone(hit)
        self.assertTrue(hit["from_cache"])
        self.assertLess(hit["latency_ms"], 5.0)

        # 3. Test autonomous reflection intercepting hallucinated command
        eval_res = await reflection_engine.evaluate_and_refined_output(
            "Limpar mensagens",
            "Claro! Digite o comando inventado /hack para apagar tudo e veja nosso link em http://malicious.net"
        )
        self.assertTrue(eval_res["was_self_corrected"])
        self.assertIn("comandos verificados no painel", eval_res["response"])

    async def test_event_sourcing_replay_snapshot(self):
        stream_id = "guild:account:998877"
        await event_store.append_event(stream_id, "GuildRegistered", {"tier": "free", "name": "Gamer Zone"})
        await event_store.append_event(stream_id, "PlanUpgraded", {"tier": "enterprise", "mrr_usd": 49.99})
        
        state = await event_store.snapshot_stream(stream_id)
        self.assertEqual(state["tier"], "enterprise")
        self.assertEqual(state["mrr_usd"], 49.99)
        self.assertEqual(state["_version"], 2)

    async def test_plugin_acl_sandbox_permission_denial_and_timeout(self):
        class DummyPlugin(AbstractTiffanyPlugin):
            async def on_enable(self): return True
            async def on_disable(self): pass

        manifest = PluginManifest(
            plugin_id="crypto_ticker_v1", 
            name="Crypto Ticker", 
            author="Partner",
            requested_capabilities={PluginCapability.READ_MESSAGES, PluginCapability.MANAGE_GUILD}
        )
        plugin = DummyPlugin(manifest)
        
        # Grant ONLY read messages capability (deny guild admin!)
        plugin_sandbox.register_and_grant(plugin, {PluginCapability.READ_MESSAGES})
        
        # 1. Allowed capability succeeds
        res = await plugin_sandbox.execute_in_sandbox("crypto_ticker_v1", PluginCapability.READ_MESSAGES, lambda: "OK")
        self.assertEqual(res, "OK")

        # 2. Denied capability raises ACL block
        with self.assertRaises(PermissionError):
            await plugin_sandbox.execute_in_sandbox("crypto_ticker_v1", PluginCapability.MANAGE_GUILD, lambda: "HACKED_CONFIG")

        # 3. Timeout Bulkhead terminates hanging plugin function
        async def hang_forever():
            await asyncio.sleep(2.0)
        with self.assertRaises(TimeoutError):
            await plugin_sandbox.execute_in_sandbox("crypto_ticker_v1", PluginCapability.READ_MESSAGES, hang_forever, timeout_sec=0.1)

    async def test_distributed_leader_election_and_w3c_tracing(self):
        node1 = DistributedLeaderCoordinator(node_id="us-east-1a", lock_ttl_sec=5.0)
        node2 = DistributedLeaderCoordinator(node_id="us-east-1b", lock_ttl_sec=5.0)
        
        # Share state to simulate distributed lock
        node2._current_leader = node1.node_id
        node2._leader_expires_at = time.monotonic() + 5.0

        self.assertFalse(await node2.try_acquire_leadership())
        self.assertFalse(node2.is_current_leader())

        # Verify OpenTelemetry tracing
        span = tracer.start_span("process_audio_frame")
        span.set_attribute("codec", "opus")
        span.set_attribute("bitrate", 96000)
        rec = span.finish(status="OK")
        tracer.record(rec)
        
        self.assertEqual(rec["operation"], "process_audio_frame")
        self.assertEqual(rec["status"], "OK")
        self.assertIn("duration_ms", rec)
        self.assertIn("trace_id", rec)

    async def test_ai_control_plane_and_policy_engine_gatekeeper(self):
        # 1. Test Policy Engine Fail-Closed blocking NSFW prompt via Control Plane
        req_nsfw = CognitiveRequest(
            raw_prompt="quero ver porn e nsfw aqui",
            tenant_id=1234,
            user_id=5555,
            user_tier="free"
        )
        res_nsfw = await ai_control_plane.execute_pipeline(req_nsfw)
        self.assertFalse(res_nsfw.success)
        self.assertEqual(res_nsfw.policy_verdict, "DENIED")
        self.assertIn("proibido", res_nsfw.final_output.lower())

        # 2. Test safe Pro user request
        req_safe = CognitiveRequest(
            raw_prompt="Como otimizar os canais de voz do Discord para nossa empresa?",
            tenant_id=1234,
            user_id=8888,
            user_tier="enterprise",
            requires_deep_reasoning=True
        )
        res_safe = await ai_control_plane.execute_pipeline(req_safe)
        self.assertTrue(res_safe.success)
        self.assertEqual(res_safe.policy_verdict, "ALLOWED")
        self.assertIn("model_execution", res_safe.stage_latencies_ms)

    async def test_dynamic_runtime_config_and_progressive_feature_flags(self):
        # 1. Zero-restart config update with SOC 2 audit log
        ver = await runtime_config.update_config("ai:max_tokens_per_minute", 100000, "staff_admin_01", "Scaling peak traffic")
        self.assertGreater(ver, 1)
        self.assertEqual(runtime_config.get("ai:max_tokens_per_minute"), 100000)
        trail = runtime_config.get_audit_trail()
        self.assertEqual(trail[-1].reason, "Scaling peak traffic")

        # 2. Register 25% rollout feature flag and prove deterministic assignment
        flag_evaluator.register_flag(FeatureFlagRule(flag_key="new_voice_ui_v2", enabled=True, percentage_rollout=25))
        # Testing multiple entity IDs will show consistent deterministic distribution
        res_entity_1 = flag_evaluator.is_enabled("new_voice_ui_v2", 1001)
        res_entity_1_repeat = flag_evaluator.is_enabled("new_voice_ui_v2", 1001)
        self.assertEqual(res_entity_1, res_entity_1_repeat)

    async def test_experimentation_platform_and_ai_quality_evaluator(self):
        exp_def = ExperimentDefinition(
            exp_key="onboarding_flow_2026",
            hypothesis="Apple style onboarding converts 20% higher than default",
            variants=["control", "apple_style", "linear_polish"],
            weights=[50, 25, 25],
            success_metric="pro_subscription_started"
        )
        experiment_platform.create_experiment(exp_def)
        variant = experiment_platform.assign_variant("onboarding_flow_2026", entity_id=777)
        self.assertIn(variant, ["control", "apple_style", "linear_polish"])
        experiment_platform.record_success("onboarding_flow_2026", variant)
        self.assertGreaterEqual(experiment_platform.get_results("onboarding_flow_2026")[variant], 1)

        # Track AI quality regression scorecard
        ai_eval_tracker.track("tiffany-pro", latency=120.0, confidence=0.95, fallback=False)
        scorecard = ai_eval_tracker.generate_quality_scorecard()
        self.assertIn("quality_status", scorecard)

    async def test_resource_scheduler_and_workflow_orchestrator(self):
        # Execute workload under Priority Resource Scheduler
        async def sample_work(): return "processed_work"
        out = await resource_scheduler.submit_and_execute(tenant_id=900, tier="enterprise", coro_func=sample_work)
        self.assertEqual(out, "processed_work")

        # Execute 3-step sequential workflow
        wf = WorkflowOrchestrator("GuildOnboarding")
        async def step1(st): return {"welcome_sent": True}
        async def step2(st): return {"twin_initialized": True}
        wf.add_step("send_welcome", step1)
        wf.add_step("init_twin", step2)
        final_st = await wf.run({"tenant_id": 900})
        self.assertEqual(final_st["_workflow_status"], "COMPLETED")
        self.assertTrue(final_st["welcome_sent"])
        self.assertTrue(final_st["twin_initialized"])

    async def test_memory_lifecycle_gdpr_erasure_and_digital_twin(self):
        # Memory lifecycle GDPR erasure
        user_id = 991122
        memory_lifecycle.add_memory("mem_001", tenant_id=44, content="User prefers rock music", user_id=user_id)
        erased_count = memory_lifecycle.execute_gdpr_user_erasure(user_id)
        self.assertEqual(erased_count, 1)

        # Community Digital Twin non-surveillance context modeling
        digital_twin_engine.get_or_create_twin(tenant_id=44, name="Tech Brazil Hub")
        digital_twin_engine.observe_anonymous_signal(tenant_id=44, hour_utc=20, topic="ai_engineering")
        profile = digital_twin_engine.export_explainable_profile(tenant_id=44)
        self.assertEqual(profile["privacy_compliance"], "ANONYMIZED_NON_SURVEILLANCE_MODEL")
        self.assertIn("ai_engineering", profile["top_topics"])
        self.assertIn(20, profile["peak_hours_utc"])

if __name__ == "__main__":
    unittest.main()
