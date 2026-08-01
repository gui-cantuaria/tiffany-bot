# Private Core Boundary

This directory (`tiffany_core/`) is **Tiffany OS Private Core** — proprietary platform intelligence.

## Status

- **Version:** 2.0.0 (package metadata in `__init__.py`)
- **Production integration:** Minimal (`mod_panel.py` command visibility sync only)
- **Default visibility:** **Private** — not intended for public ecosystem distribution

## Contains (non-exhaustive)

- AI Control Plane and model routing
- Policy Engine and AI safety guards
- Knowledge Graph, memory lifecycle, Digital Twin
- Plugin sandbox runtime (not public plugin marketplace)
- Enterprise reliability and observability primitives

## Public surface

External developers must interact through **versioned contracts** only (future: API types, plugin SDK, gateway ports). See `docs/open-ecosystem-strategy.md`.

## Do not

- Copy this package into public example repos without sanitization
- Document internal prompts or policy rules in public docs
- Grant plugins direct imports of this package in production (use capability-gated APIs)

## Planned relocation

This code will migrate to a **private repository** when Phase VI maturity gates are met. Until then, treat it as confidential intellectual property even if temporarily colocated in a public monorepo.
