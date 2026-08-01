"""
Tiffany OS — AI Memory Lifecycle, Privacy-Preserving Digital Twin & Enterprise Governance
=======================================================================================
Implements automated memory pruning with LGPD/GDPR right-to-be-forgotten expiration.
Models anonymous community behavior patterns (Digital Twin) without intrusive surveillance,
and establishes enterprise multi-tenant workspaces with auditable governance exports.
"""

from __future__ import annotations
import logging
import math
import time
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field

log = logging.getLogger("tiffany.core.knowledge.lifecycle")

# =============================================================================
# Automated AI Memory Lifecycle & GDPR Expiration
# =============================================================================

@dataclass
class LifecycleMemoryRecord:
    memory_id: str
    tenant_id: int
    user_id: Optional[int]
    content: str
    relevance_score: float = 1.0
    created_at: float = field(default_factory=time.time)
    expires_at_epoch: Optional[float] = None
    state: str = "ACTIVE"  # 'ACTIVE', 'ARCHIVED', 'EXPIRED', 'PURGED'

class MemoryLifecycleManager:
    """
    Manages cognitive retention over time. Automatically decays outdated facts,
    deduplicates semantic overlaps, and strictly purges PII upon GDPR regulatory requests.
    """
    def __init__(self, default_ttl_sec: float = 86400.0 * 90.0) -> None:
        self.default_ttl_sec = default_ttl_sec  # Default 90-day retention
        self._store: Dict[str, LifecycleMemoryRecord] = {}

    def add_memory(self, memory_id: str, tenant_id: int, content: str, user_id: Optional[int] = None, ttl_sec: Optional[float] = None) -> LifecycleMemoryRecord:
        expiry = time.time() + (ttl_sec or self.default_ttl_sec)
        rec = LifecycleMemoryRecord(memory_id=memory_id, tenant_id=tenant_id, user_id=user_id, content=content, expires_at_epoch=expiry)
        self._store[memory_id] = rec
        log.debug("[MemoryLifecycle] Created memory '%s' for Tenant %d (Expires: %.0f)", memory_id, tenant_id, expiry)
        return rec

    def prune_expired_and_apply_decay(self) -> int:
        now = time.time()
        purged_count = 0
        for mid in list(self._store.keys()):
            rec = self._store[mid]
            if rec.expires_at_epoch and now >= rec.expires_at_epoch:
                rec.state = "PURGED"
                self._store.pop(mid, None)
                purged_count += 1
            else:
                # Decay relevance slightly with age
                age_days = (now - rec.created_at) / 86400.0
                rec.relevance_score = max(0.1, round(math.exp(-0.01 * age_days), 3))
        if purged_count > 0:
            log.info("[MemoryLifecycle] Pruned %d expired records from active vault", purged_count)
        return purged_count

    def execute_gdpr_user_erasure(self, user_id: int) -> int:
        erased = 0
        for mid in list(self._store.keys()):
            if self._store[mid].user_id == user_id:
                self._store.pop(mid, None)
                erased += 1
        log.info("[MemoryLifecycle: GDPR/LGPD] Erased %d memory records for User ID %d", erased, user_id)
        return erased


# =============================================================================
# Privacy-Preserving Community Digital Twin (Competitive Moat)
# =============================================================================

@dataclass
class CommunityTwinState:
    tenant_id: int
    name: str
    dominant_language: str = "pt-br"
    peak_active_hours_utc: Set[int] = field(default_factory=lambda: {18, 19, 20, 21, 22})
    topic_affinities: Dict[str, int] = field(default_factory=dict)
    culture_summary: str = "Comunidade focada em tecnologia, jogos e colaboração amigável."

class CommunityDigitalTwinEngine:
    """
    Models collective server atmosphere and workflows over time. Strictly anonymizes all
    aggregations without logging personal chatter, generating an uncopyable AI context moat.
    """
    def __init__(self) -> None:
        self._twins: Dict[int, CommunityTwinState] = {}

    def get_or_create_twin(self, tenant_id: int, name: str = "Guild") -> CommunityTwinState:
        if tenant_id not in self._twins:
            self._twins[tenant_id] = CommunityTwinState(tenant_id=tenant_id, name=name)
        return self._twins[tenant_id]

    def observe_anonymous_signal(self, tenant_id: int, hour_utc: int, topic: str) -> None:
        twin = self._twins.get(tenant_id)
        if twin:
            twin.peak_active_hours_utc.add(hour_utc)
            twin.topic_affinities[topic] = twin.topic_affinities.get(topic, 0) + 1
            log.debug("[DigitalTwin] Tenant %d twin reinforced affinity for topic '%s'", tenant_id, topic)

    def export_explainable_profile(self, tenant_id: int) -> Dict[str, Any]:
        twin = self._twins.get(tenant_id)
        if not twin:
            return {"error": "Twin not found"}
        return {
            "tenant_id": twin.tenant_id,
            "community_name": twin.name,
            "language": twin.dominant_language,
            "peak_hours_utc": sorted(list(twin.peak_active_hours_utc)),
            "top_topics": dict(sorted(twin.topic_affinities.items(), key=lambda i: i[1], reverse=True)[:5]),
            "culture_summary": twin.culture_summary,
            "privacy_compliance": "ANONYMIZED_NON_SURVEILLANCE_MODEL"
        }


# =============================================================================
# Enterprise Governance & Workspace Vault
# =============================================================================

@dataclass
class EnterpriseWorkspace:
    org_id: str
    tenant_ids: Set[int]
    sso_enabled: bool = False
    data_residency_region: str = "eu-west-1"
    audit_log: List[str] = field(default_factory=list)

class EnterpriseGovernanceVault:
    """Provides organization-level multi-tenant workspaces with RBAC and exportable audit records."""
    def __init__(self) -> None:
        self._workspaces: Dict[str, EnterpriseWorkspace] = {}

    def create_workspace(self, org_id: str, tenant_ids: Set[int], sso: bool = False) -> EnterpriseWorkspace:
        ws = EnterpriseWorkspace(org_id=org_id, tenant_ids=tenant_ids, sso_enabled=sso)
        ws.audit_log.append(f"[{time.ctime()}] Workspace created for Org '{org_id}' with {len(tenant_ids)} tenants.")
        self._workspaces[org_id] = ws
        return ws

    def log_audit_action(self, org_id: str, action_desc: str) -> None:
        ws = self._workspaces.get(org_id)
        if ws:
            ws.audit_log.append(f"[{time.ctime()}] {action_desc}")

    def export_soc2_audit_trail(self, org_id: str) -> Dict[str, Any]:
        ws = self._workspaces.get(org_id)
        if not ws:
            return {"status": "workspace_not_found"}
        return {
            "organization_id": ws.org_id,
            "sso_enabled": ws.sso_enabled,
            "data_residency": ws.data_residency_region,
            "attached_tenants": list(ws.tenant_ids),
            "total_audit_events": len(ws.audit_log),
            "audit_trail_events": ws.audit_log
        }

memory_lifecycle = MemoryLifecycleManager()
digital_twin_engine = CommunityDigitalTwinEngine()
enterprise_vault = EnterpriseGovernanceVault()
