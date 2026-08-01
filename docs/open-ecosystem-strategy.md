# Tiffany OS — Open Ecosystem & Private Core Strategy Report

**Version:** 1.0  
**Date:** 2026-08-01  
**Scope:** Repository audit + strategic recommendation + boundary design  
**Status:** Strategic document — not legal advice

---

## 1. Executive Summary

Tiffany is transitioning from a Discord bot into a community AI platform (Tiffany OS). The repository today is a **single public monorepo** (`gui-cantuaria/tiffany-bot`) that simultaneously contains:

- A **production Discord bot** (news, offers, music, chat, moderation) used on a live VPS.
- An **experimental enterprise layer** (`tiffany_core/`) with AI Control Plane, Policy Engine, Knowledge Graph, Digital Twin, plugin sandbox, and gateway abstractions — **mostly not wired to production**.
- **Premium/monetization infrastructure** (Stripe, pricing, entitlements) — partially implemented, not fully exposed in production.

The hypothesis **“Open Ecosystem, Closed Intelligence” (Model D)** is **strategically correct** for Tiffany’s long-term goals, but **not correctly implemented today**. The current public monorepo exposes components that the strategy marks as private (pricing logic, premium entitlements, policy engine, control plane, anti-abuse internals).

**Immediate priorities:**

1. **Do not open additional surface area** (no public SDK repos, no plugin marketplace) until Phase VI maturity gates pass.
2. **Restructure repositories** so private intelligence is not co-located with community-facing code without access controls.
3. **Security must not depend on obscurity** — auth, isolation, rate limits, and secrets management remain primary controls regardless of visibility.
4. **Clarify narrative**: README currently invites open-source contribution under MIT while referencing a missing `LICENSE` file and omitting `tiffany_core/` entirely.

**Bottom line:** Tiffany should **not** become fully open source. Tiffany should **not** remain fully private. Tiffany should adopt **Private Core + Open Ecosystem**, executed incrementally with measurable maturity gates — not ideology.

---

## 2. Strategic Recommendation — Model Comparison

| Criterion | A — Fully Closed | B — Fully Open | C — Open Core | D — Private Core + Open Ecosystem | E — Source-Available |
|---|---|---|---|---|---|
| IP protection | Strong | Weak | Medium | **Strong (core private)** | Medium |
| Competitive cloning risk | Low exposure | High | Medium-high | **Low for intelligence** | Medium |
| Security transparency | Low trust | High trust | Medium | **High via contracts, not core source** | Medium |
| Community growth | Low | High | Medium-high | **High via SDK/plugins** | Medium |
| Developer adoption | Low | High | Medium | **High (stable APIs)** | Medium |
| Contribution potential | None | High | Medium | **Targeted (ecosystem only)** | Low |
| Ecosystem growth | None | High | Medium | **High without moat leak** | Low |
| Monetization | Easy to gate | Hard | Natural split | **Natural (premium in private core)** | Flexible |
| Enterprise trust | Requires sales | Mixed | Common pattern | **Strong if security program exists** | Mixed |
| Maintenance burden | Low surface | High | Medium | **Medium (multi-repo)** | Medium |
| Support burden | Internal only | Public | Split | **Split by layer** | Internal |
| Governance complexity | Low | High | Medium | **Medium** | Low |
| Talent attraction | Lower OSS appeal | High | Medium | **High (public tools + hard problems private)** | Low |
| Vulnerability disclosure | Opaque | Standard OSS | Mixed | **Public layer: OSS process; private: coordinated** | Limited |
| Cloning risk | Behavior-only clone | Full fork | Partial fork | **Fork SDK/adapters, not intelligence** | Inspect-only clone |
| Long-term defensibility | Brand + ops | Network effects | Feature gating | **Data + ops + contracts + brand** | Legal friction only |

### Attempt to disprove Model D

**Counter-argument:** Discord bots historically succeed as open-source forks (FredBoat, Red-DiscordBot). Transparency accelerates trust and contributors.

**Rebuttal with repository evidence:**

- Tiffany’s roadmap targets **AI orchestration, memory, policy, monetization, enterprise governance** — not a music bot alone.
- `config/pricing.json`, `infra/stripe_server.py`, `infra/premium.py`, and `tiffany_core/security/policy_engine.py` are **economics and governance**, not community features. Publishing them simplifies competitor undercutting and abuse evasion.
- Production moat today is **operational** (WARP proxy, VPS tuning, affiliate relationships, curated feeds, 16-language i18n, live community) — but **future moat** is **accumulated context + routing quality + enterprise relationships**. Model D protects the latter without sacrificing developer ecosystem.

**Conclusion:** Model D survives scrutiny. Models A and B are inferior for Tiffany’s stated platform vision. Model C is acceptable but still exposes too much intelligence in a monolith like this repo. Model E is a fallback for selective inspection, not the primary strategy.

---

## 3. Recommended Model

> **Open Ecosystem, Closed Intelligence** — **YES**, with conditions.

| Layer | Visibility | Rationale |
|---|---|---|
| Private Core | Private repositories, production-only deploy | Competitive intelligence, economics, sensitive heuristics |
| Open Ecosystem | Public repositories when mature | SDK, types, examples, adapter interfaces, developer docs |
| Discord Bot (integration layer) | **Source-available or open after sanitization** | Drives adoption; must not embed proprietary prompts/routing |
| Data & secrets | Never public | Legal, security, and trust requirements |

---

## 4. Private Core Inventory

Components that **should remain private** (currently in repo — relocation required):

| Component | Location | Why private |
|---|---|---|
| AI Control Plane | `tiffany_core/ai/control_plane.py` | Orchestration pipeline, cost optimization, routing decisions |
| AI Router & model selection | `tiffany_core/ai/router.py`, `config/ai_models.json` | Cost/quality tradeoffs, quota weights |
| Semantic cache & reflection | `tiffany_core/ai/semantic_cache_and_reflection.py` | Cross-tenant isolation logic; leakage risk if misconfigured |
| Policy Engine (RBAC/ABAC) | `tiffany_core/security/policy_engine.py` | Tier gates, budget rules, enterprise policy |
| AI safety / injection guard internals | `tiffany_core/security/ai_safety.py` | Attackers optimize against known rules |
| PII scrubber / GDPR implementation | `tiffany_core/security/privacy.py` | Compliance detail + erasure paths |
| Knowledge Graph intelligence | `tiffany_core/knowledge/graph.py` | Future moat; retrieval/ranking logic |
| Memory lifecycle / Digital Twin | `tiffany_core/knowledge/memory_lifecycle_and_digital_twin.py` | Community behavior modeling |
| Evaluation & experiments | `tiffany_core/ai/evaluation_and_experiments.py` | A/B and quality systems |
| Monetization & Stripe webhook | `infra/stripe_server.py`, `infra/services/subscription.py` | Billing, entitlements, commercial logic |
| Premium entitlements | `infra/premium.py`, `premium_panel.py`, `config/pricing.json` | Pricing strategy |
| AI quota enforcement | `infra/services/ai_quota.py` | Economic controls |
| Premium AI guardrails (news/offers) | `premium_ai_guardrails.py` | Content classification thresholds |
| Premium scraper | `premium_scraper.py` | Commercial feed access patterns |
| Anti-abuse L2/L3 internals | `infra/moderation/pipeline.py`, `moderation_auto.py` (L3 prompts) | Evasion risk |
| Safe Browsing integration patterns | `infra/moderation/safe_browsing.py` | Operational abuse patterns |
| Production deploy & infra scripts | `scripts/deploy.sh`, WARP scripts, systemd units | Operational security |
| Internal telemetry pipelines | `infra/services/telemetry.py`, owner dashboards | Operational data |
| Proprietary prompts (chat, news, offers, games) | Embedded in `notices.py`, `tiffany_voice.py`, `game_recommendations.py` | IP + injection surface |
| Affiliate commercial logic | `affiliate_config.py` | Commercial relationships |

---

## 5. Public Ecosystem Inventory

Safe to publish **after maturity gates** (not necessarily safe **today** as-is):

| Component | Current location | Public form |
|---|---|---|
| Public API types | *Not extracted* | `tiffany-api-types` package |
| Event schemas | `tiffany_core/domain/events.py` | Sanitized JSON Schema repo |
| Gateway adapter interfaces | `tiffany_core/adapters/gateway_protocol.py` | Public interface-only package |
| Plugin SDK contracts | `tiffany_core/domain/event_sourcing_and_plugins.py` | Public manifest + capability enums |
| Example plugins | *None* | `tiffany-examples` repo |
| Developer documentation | `docs/*-technical.md` (sanitized) | Public docs site |
| i18n locale files (non-secret) | `locales/` | Can remain public |
| Brand constants | `brand_colors.py` | Public |
| Generic Discord cog patterns | giveaways, embed builder (without premium hooks) | Open examples |
| Test utilities (non-adversarial) | portions of `test_smoke.py` | Public CI examples |
| CONTRIBUTING / governance | `CONTRIBUTING.md` | Public, updated |

**Production bot modules that could remain open with sanitization:**

- Dice mechanics (generic)
- Embed builder UX (without internal moderation hooks)
- Giveaways (generic)
- i18n tooling scripts (without API keys)
- Lavalink/docker compose templates (without production secrets)

---

## 6. Potentially Open Later

| Component | Maturity required |
|---|---|
| PostgreSQL schema (generic tables) | After PII review; strip commercial columns |
| Redis abstractions | After production hardening |
| `infra/postgres.py`, `infra/redis_client.py` | After secret handling audit |
| Moderation L1 regex rules | After measuring evasion impact |
| `imagine_safety.py` keyword lists | After legal review |
| Voice engine abstraction | `tiffany_core/audio/voice_engine.py` — when stable |
| Reliability patterns (circuit breaker) | Generic patterns OK later |
| Discord adapter implementation | After stripping premium/policy hooks |
| HA architecture docs | Already public; keep sanitized |

---

## 7. Never Public

| Asset | Reason |
|---|---|
| `.env`, production tokens | Credential compromise |
| VPS SSH keys, GitHub secrets | Infrastructure takeover |
| `guild_config.json`, `user_settings.json`, all runtime JSON state | Customer/tenant data |
| Chat memory, roleplay history | User privacy |
| Stripe secret keys, webhook secrets, price IDs (live) | Financial fraud |
| Production Discord guild/channel/role IDs | Targeted abuse |
| Internal evaluation datasets | Privacy + competitive |
| Fraud signals, abuse heuristics (L3 AI prompts) | Evasion |
| Customer contracts, enterprise tenant configs | Confidential |
| WARP/production IP addresses | Operational security |
| Hardcoded owner IDs | Targeting (`admin_dashboard_cog.py`) |

---

## 8. IP & Competitive Moat Analysis

### Question: If a competitor had full source tomorrow, could they reproduce Tiffany’s business?

**Partially — but not the durable business.**

| Moat source | Replicable from source? | Evidence |
|---|---|---|
| Source code structure | **Yes** | Monorepo is public today |
| Live Discord distribution & brand | **No** | Top.gg presence, community, trust |
| Operational deployment (WARP, VPS tuning) | **Hard** | `docs/voice-technical.md`, deploy scripts |
| Curated news/offers pipelines + affiliate deals | **Hard** | Relationships, thresholds in `notices.py` / `offers_cog.py` |
| 16-language i18n investment | **Medium** | `locales/` copyable but expensive to maintain |
| Historical community memory | **No** | Runtime JSON / future PG — not in repo |
| AI quality at scale | **No** | Not wired; control plane immature |
| Enterprise relationships | **No** | Not in code |
| Switching costs (configured servers) | **No** | Per-guild config, playlists, macros |
| Network effects (plugins, integrations) | **Not yet** | Ecosystem not launched |

**Still difficult to replicate even with code:** accumulated usage data, routing quality tuned from production traffic, premium subscriber base, moderation reputation, and integrated commercial feeds.

**Protect:** data flywheel, orchestration quality, policy economics, enterprise trust — **not** `#ifdef PRIVATE` theater.

---

## 9. Security Boundary

### Public developers MAY access (future ecosystem)

- Versioned HTTP/Webhook APIs (documented)
- Plugin SDK with declared capabilities
- Event schemas (non-PII)
- OAuth/API keys scoped to tenant + capability set
- Sandbox execution environment
- Public documentation and examples

### Public developers MUST NOT access

- Production databases (PG/Redis)
- Raw user messages, memory stores, knowledge graph nodes
- Internal prompts and policy rules
- Billing systems and entitlement overrides
- Stripe admin operations
- Cross-tenant data
- Internal telemetry and fraud scores
- Deploy/production infrastructure

### Security controls (must hold even if code leaks)

- Authentication (bot token, API keys, Stripe signatures)
- Authorization (guild/user/feature flags, `@requires_premium`)
- Tenant isolation (cache scopes, PG row-level logic — **needs hardening**)
- Encryption in transit (TLS) and at rest (PG, backups)
- Secrets in env/secret managers only
- Rate limits (`docs/rate-limits.md`, quota services)
- Abuse prevention (L1/L2/L3 moderation)
- Monitoring & audit (`moderation_auto.py`, future real observability)
- Vulnerability response (`SECURITY.md`)

**Known gaps (Phase V/VI audit — must fix before public ecosystem):**

- Semantic cache cross-user leakage class — tests exist; production bot bypasses control plane
- Workflow idempotency incomplete outside tests
- Prompt injection guards exist in `tiffany_core` but production uses direct OpenRouter paths
- PII scrubber regex bypass documented in tests
- Fake/hardcoded health metrics in test adversarial suite
- `telemetry_ai_usage` referenced without SQL migration
- PostgreSQL/Redis optional — JSON fallbacks in production path

---

## 10. Open-Source Architecture

### Target structure

```
Tiffany OS (company)
│
├── tiffany-core (PRIVATE)
│   ├── ai/                 # Control plane, router, cache, eval
│   ├── security/           # Policy engine, privacy, ai_safety
│   ├── knowledge/          # Graph, memory, digital twin
│   ├── monetization/         # Stripe, entitlements, quota
│   └── infra/              # Production telemetry, deploy
│
├── tiffany-bot (PUBLIC or source-available)
│   ├── discord/            # notices, voice, cogs (integration only)
│   ├── locales/
│   └── launcher
│
└── tiffany-ecosystem (PUBLIC)
    ├── tiffany-api-types
    ├── tiffany-plugin-sdk
    ├── tiffany-event-schemas
    ├── tiffany-adapter-interfaces
    ├── tiffany-examples
    └── tiffany-docs
```

### Repository strategy: **Multiple repositories** (recommended)

| Approach | Verdict |
|---|---|
| Monorepo (public + private mixed) | **Reject** — current state; caused strategic confusion |
| Monorepo with private submodules | Possible but high friction |
| **Multi-repo with stable contracts** | **Accept** — clearest boundary, independent versioning |

Communication: **only through versioned contracts** (HTTP API, event bus schema, plugin manifest). No shared DB credentials for plugins.

### Versioning policy

- **Public APIs:** semver; breaking changes only in major versions
- **Deprecations:** minimum 90-day notice for ecosystem APIs
- **Internal core:** calendar versioning or continuous deploy
- **Compatibility tests:** contract tests in CI for SDK vs core mock

---

## 11. Plugin Architecture

Based on existing design in `tiffany_core/domain/event_sourcing_and_plugins.py`:

```
Plugin Manifest
      ↓
Capability Request (explicit list)
      ↓
Policy Engine Validation (tenant tier, budget, NSFW policy)
      ↓
Permission Grant (least privilege)
      ↓
Sandboxed Execution (timeout, resource limits, no direct DB)
      ↓
Audit Log (append-only event stream)
```

### Capability examples (from code)

- `read:messages`
- `write:audio`
- `admin:guild_config`
- `network:http`

### Rules

- Plugins **never** receive raw connection strings
- Plugins **never** call OpenRouter directly unless granted `ai:invoke` with quota envelope
- Revocation via manifest version bump + runtime disable per guild
- Supply-chain: signed releases for verified plugins (future)

---

## 12. Licensing Strategy

| Component | Recommended license | Notes |
|---|---|---|
| Public SDK / types / examples | **Apache-2.0** | Patent grant; enterprise-friendly |
| Public bot integration layer | **Apache-2.0** or **MIT** | Align with Discord ecosystem norms |
| Documentation | **CC BY 4.0** | Standard for docs |
| Private core | **Proprietary** | All rights reserved |
| Source-available preview (optional) | **BUSL / SSPL** | **Legal review required** — not legal advice |

| License | Commercial use | Modification | Redistribution | Patent | Risk |
|---|---|---|---|---|---|
| MIT | Yes | Yes | Yes | Weak | Competitors can close-source forks |
| Apache-2.0 | Yes | Yes | Yes | Stronger | Preferred for SDK |
| GPL-family | Constrained | Yes | Must open derivatives | Varies | Poor fit for Discord ecosystem |
| BUSL/SSPL | Restricted | Limited | Limited | N/A | Delayed open / anti-cloud |

**Action:** Add `LICENSE` (Apache-2.0 for public repos when split). Current README claims MIT but **no LICENSE file exists** — legal gap.

---

## 13. Security & Vulnerability Management

Implement now (even before public SDK):

| Item | Status | Action |
|---|---|---|
| `SECURITY.md` | Created | Reporting process |
| Private security contact | Defined | tiffanydiscordbot@gmail.com or GitHub private reporting |
| Responsible disclosure | Document | 90-day coordinated disclosure target |
| Secret scanning | Partial | Enable GitHub secret scanning |
| Dependency scanning | Partial | Dependabot / pip-audit in CI |
| SAST | Missing | Add bandit/ruff security rules |
| Signed releases | Missing | When publishing SDK packages |

---

## 14. Governance

**Recommended model:** **Founder-led, commercially governed** (early stage) → **maintainer team** as ecosystem grows.

| Element | Policy |
|---|---|
| Contributions | PRs welcome for **public repos only**; CLA optional until enterprise contributors |
| Code of conduct | Add when opening public ecosystem |
| Roadmap transparency | Public for ecosystem; private core roadmap internal |
| Release process | Tagged releases for SDK; continuous deploy for bot |

Do **not** create heavy foundation bureaucracy until contributor volume justifies it.

---

## 15. Public Release Readiness

### Is Tiffany ready to open any part of the ecosystem today?

**No.**

| Gate | Status |
|---|---|
| Architecture stability | ❌ Monolith mixing bot + core + premium |
| API stability | ❌ No public API |
| P0 security issues | ❌ Cache scope, PII scrubber bypass, production bypasses control plane |
| Real PostgreSQL/Redis in production | ⚠️ Optional, JSON fallback |
| Real observability | ❌ Fake metrics in tests; limited production telemetry |
| Vulnerability reporting | ⚠️ SECURITY.md added; process immature |
| CI/CD for ecosystem | ⚠️ Only `test_smoke.py` in CI |
| Documentation accuracy | ❌ README omits `tiffany_core`, LICENSE missing |
| Secret scanning | ⚠️ Partial |

**What can be public today without new exposure:** Sanitized **documentation of intent** (this report), governance files, and **honest README** clarifying experimental vs production paths.

**What must NOT be promoted as “open ecosystem” yet:** Plugin marketplace, external SDK, third-party core access.

---

## 16. Migration Roadmap

### Immediate (0–7 days)

- [x] Publish this strategy document
- [x] Add `SECURITY.md` and `LICENSE`
- [ ] Update README to distinguish **Tiffany Bot (production)** vs **Tiffany OS Core (experimental, private-boundary)**
- [ ] Mark `tiffany_core/` with `PRIVATE_CORE.md` boundary notice
- [ ] Fix deploy.sh to include or **exclude** `tiffany_core/` intentionally (today: inconsistent — `mod_panel.py` imports it but deploy omits it)
- [ ] Remove hardcoded owner IDs from any future public surface
- [ ] Add `telemetry_ai_usage` migration or remove dead code

### 30 days

- [ ] Extract **contract definitions** (`GatewayPort`, `PluginManifest`, domain events) to standalone package skeleton (private until tested)
- [ ] Wire production chat **or** explicitly defer — no half-public control plane
- [ ] Enable dependency + secret scanning in GitHub Actions
- [ ] Run `test_tiffany_core.py` + phase tests in CI (gate on critical security tests)
- [ ] Legal review of licensing split

### 90 days

- [ ] Create private `tiffany-core` repository; migrate `tiffany_core/` + premium + stripe
- [ ] Sanitize public `tiffany-bot` integration repo
- [ ] Define v1 plugin manifest spec + mock sandbox API
- [ ] Real PG/Redis required for premium path in production
- [ ] Coordinated vulnerability disclosure drill

### 6 months

- [ ] Publish `tiffany-api-types` + `tiffany-plugin-sdk` (read-only contracts)
- [ ] Example plugins in `tiffany-examples`
- [ ] Public adapter interface for Discord (implementation stays split)
- [ ] Plugin capability enforcement in production gateway
- [ ] Enterprise SSO / tenant isolation review

### Future (maturity-based, not date-based)

Open additional layers when **all** are true:

- Public API semver stable for 2+ release cycles
- Zero open P0 security issues for 60 days
- Real observability with on-call rotation
- Maintainer capacity for external PRs
- Demonstrated demand (≥3 external integration partners or ≥10 plugin authors in preview)

---

## 17. Final Recommendation

| Question | Answer |
|---|---|
| Should Tiffany become fully open source? | **No** |
| Should Tiffany remain fully private? | **No** |
| Should Tiffany adopt Private Core + Open Ecosystem? | **Yes** |
| What should be public today? | Governance docs, accurate README, sanitized technical docs — **not** SDK/marketplace |
| What should remain private? | Control plane, policy engine, memory/KG/twin, monetization, premium guardrails, production infra, proprietary prompts |
| What should open later? | SDK, types, examples, generic adapters — after gates in §15 |
| Maturity gates? | See §15 and §16 — measured criteria, not calendar hype |

### Strategic target (validated)

> **Open Ecosystem. Closed Intelligence. Strong Security. Transparent Contracts. Private Competitive Moat.**

The objective is to make Tiffany **easier to build upon** without making Tiffany’s **intelligence, data, economics, or operational advantage** easier to replicate.

---

## Appendix A — IP & Exposure Matrix (major components)

| Component | Current Location | Strategic Value | Security Sensitivity | Competitive Moat | Open Candidate | Recommendation | Reason |
|---|---|---|---|---|---|---|---|
| Discord client + news | `notices.py` | High | Medium | Medium | Partial | Sanitized public | Drives adoption; strip prompts |
| Voice/music/chat | `tiffany_voice.py` | High | Medium | Medium | Partial | Sanitized public | Large file; split integration from AI routing |
| Offers cog | `offers_cog.py` | High | Low | High | Partial | Private logic / public UI patterns | Affiliate + curation moat |
| Game recommendations | `game_recommendations.py` | Medium | Low | Medium | No | Private | AI + store pipeline |
| Imagine | `imagine.py`, `imagine_safety.py` | Medium | High | Low | Partial | Public safety API later | Keyword lists sensitive |
| Feature flags | `feature_flags.py`, `guild_config.py` | Medium | Medium | Low | Yes | Public | Generic pattern |
| Mod panel | `mod_panel.py` | Medium | Medium | Low | Partial | Public UI / private policy | Uses core syncer |
| Moderation L1 | `infra/moderation/rules.py` | High | High | Medium | No | Private | Evasion risk |
| Moderation pipeline | `infra/moderation/pipeline.py` | High | High | High | No | Private | Anti-abuse moat |
| AI Control Plane | `tiffany_core/ai/control_plane.py` | Critical | Critical | Critical | No | **Private** | Core intelligence |
| AI Router | `tiffany_core/ai/router.py` | Critical | High | Critical | No | **Private** | Routing economics |
| Semantic cache | `tiffany_core/ai/semantic_cache_and_reflection.py` | Critical | Critical | High | No | **Private** | Isolation logic |
| Policy Engine | `tiffany_core/security/policy_engine.py` | Critical | Critical | Critical | No | **Private** | Governance |
| Knowledge Graph | `tiffany_core/knowledge/graph.py` | Critical | High | Critical | No | **Private** | Future moat |
| Digital Twin | `tiffany_core/knowledge/memory_lifecycle_and_digital_twin.py` | Critical | Critical | Critical | No | **Private** | Sensitive modeling |
| Plugin sandbox | `tiffany_core/domain/event_sourcing_and_plugins.py` | High | High | Medium | Interface only | Public manifest / private runtime | ACL design is sensitive |
| Gateway protocol | `tiffany_core/adapters/gateway_protocol.py` | Medium | Low | Low | Yes | Public interfaces | Enables ecosystem |
| Stripe server | `infra/stripe_server.py` | Critical | Critical | High | No | **Private** | Financial |
| Premium entitlements | `infra/premium.py` | Critical | High | High | No | **Private** | Monetization |
| Pricing config | `config/pricing.json` | Critical | Medium | High | No | **Private** | Commercial strategy |
| i18n locales | `locales/` | Medium | Low | Medium | Yes | Public | Community benefit |
| JSON runtime state | `*.json` gitignored | High | Critical | High | Never | **Never public** | User data |
| Deploy scripts | `scripts/deploy.sh` | Medium | Critical | Low | No | Private | Ops exposure |
| Tests smoke | `test_smoke.py` | Low | Low | None | Yes | Public | CI example |
| Tests adversarial | `test_phase5_adversarial.py` | Medium | High | Medium | No | Private | Reveals weaknesses |

---

## Appendix B — Competitive Risk Assessment

| Scenario | Material risk? | Mitigation |
|---|---|---|
| Competitor forks public bot code | Medium | Moat is ops + data + brand, not dice commands |
| Competitor clones SDK | Low | Expected; SDK is meant to spread integrations |
| Competitor copies public adapters | Low | Commodity; intelligence stays private |
| Competitor studies plugin interfaces | Low | Interfaces are intentional |
| Competitor reconstructs behavior without source | **High** | Always possible; defend with data + quality + distribution |
| Competitor obtains private core leak | **Critical** | Legal + security response; not primary defense line |

**Do not exaggerate protection from private source.** Assume APIs and behavior will be reverse-engineered.

---

## Appendix C — Continuous Validation Checklist

After any public release:

- [ ] Secret scan on all public repos (pre-push)
- [ ] No private paths in public docs/examples
- [ ] Build artifacts contain no `tiffany_core` source
- [ ] Plugin permissions enforced in integration tests
- [ ] Contract tests pass against core mock
- [ ] Production credentials isolated from contributor environments
- [ ] Quarterly boundary audit (this matrix updated)

---

*Document owner: Tiffany OS architecture. Review quarterly or after major phase completion.*
