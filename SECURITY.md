# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| `main` branch (production VPS deploy) | Yes |
| Older commits | No |

## Reporting a vulnerability

**Do not open public GitHub issues for security vulnerabilities.**

Report privately via:

1. **GitHub Security Advisories** (preferred): use *Report a vulnerability* on the repository security tab.
2. **Email**: contact us directly at tiffanydiscordbot@gmail.com (reserved for administrative or security disclosures).

Include:

- Description of the issue and impact
- Steps to reproduce
- Affected component (bot command, API, infra, etc.)
- Proof-of-concept if available (no destructive testing on production)

## Response timeline (targets)

| Stage | Target |
|-------|--------|
| Initial acknowledgment | 72 hours |
| Severity assessment | 7 days |
| Fix or mitigation plan | 14 days (critical), 30 days (high) |
| Coordinated disclosure | After fix deployed or workaround documented |

## Scope

**In scope:**

- Tiffany Bot Discord commands and interactions
- Moderation, premium, and AI features exposed to users
- Deploy scripts and infrastructure configuration in this repository
- `tiffany_core/` experimental modules when enabled

**Out of scope:**

- Third-party services (Discord, OpenRouter, Stripe, Promobit, Google Safe Browsing)
- Social engineering against server admins
- Issues requiring physical access to the VPS

## Safe harbor

Good-faith security research that:

- Avoids privacy violations and data destruction
- Avoids service disruption on production
- Reports findings privately before public disclosure

will not be pursued as malicious activity.

## Security architecture note

Tiffany's security does **not** rely on source code secrecy. Assume public knowledge of APIs, commands, and architecture. Controls include authentication, authorization, tenant isolation, rate limits, moderation pipelines, and secrets management.

## Private core boundary

Components marked as **Private Core** in `docs/open-ecosystem-strategy.md` may move to separate private repositories. Vulnerabilities in public integration layers that expose private data or bypass policy controls are treated as **critical**.
