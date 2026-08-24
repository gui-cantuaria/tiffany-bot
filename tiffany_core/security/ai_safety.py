"""
Tiffany OS — AI Safety & Tool Authorization Boundaries Layer (P0.3)
==================================================================
Provides defense-in-depth against adversarial AI exploitation including prompt injection,
Unicode/Base64 obfuscation, system prompt extraction, and instruction hijacking.
Implements the ToolAuthorizationGateway to guarantee zero cross-tenant, cross-user IDOR,
or privilege escalation vulnerabilities when executing LLM-proposed tool invocations.
"""

from __future__ import annotations
import base64
import binascii
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple

from tiffany_core.ai.semantic_cache_and_reflection import AuthorizationScope

log = logging.getLogger("tiffany.core.security.ai_safety")


# =============================================================================
# Exceptions for Tool Execution Security Boundaries
# =============================================================================

class ToolAuthorizationError(PermissionError):
    """Raised when an invoker lacks permissions/roles required for a tool."""
    pass

class ToolTenantIsolationError(PermissionError):
    """Raised on cross-tenant tool execution attempts."""
    pass

class ToolIDORViolationError(PermissionError):
    """Raised on cross-user Indirect Object Reference execution attempts."""
    pass

class ToolNotFoundError(KeyError):
    """Raised when an unregistered tool is invoked."""
    pass


# =============================================================================
# Prompt Injection & Obfuscation Defense (Input Normalizer)
# =============================================================================

class PromptInjectionGuard:
    """
    Normalizes inputs, decodes obfuscation, and evaluates prompt safety against
    adversarial manipulation, overrides, and jailbreaks.
    """
    # Regex patterns targeting common injections and system instructions
    FORBIDDEN_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
        (re.compile(r"ignore\s+(all\s+)?(previous\s+)?instructions?", re.IGNORECASE), "INSTRUCTION_OVERRIDE"),
        (re.compile(r"system\s+prompt\s+override", re.IGNORECASE), "SYSTEM_OVERRIDE"),
        (re.compile(r"(you\s+are\s+now|act\s+as)\s+(dan|unfiltered|jailbroken)", re.IGNORECASE), "JAILBREAK_ATTEMPT"),
        (re.compile(r"do\s+anything\s+now", re.IGNORECASE), "DAN_JAILBREAK"),
        (re.compile(r"(output|reveal|display|print)\s+(your\s+)?(system|initial)\s+(prompt|instructions?|rules?)", re.IGNORECASE), "PROMPT_EXTRACTION"),
        (re.compile(r"forget\s+(all\s+)?(your\s+)?(guidelines|rules|instructions)", re.IGNORECASE), "GUIDELINE_ERASURE"),
        (re.compile(r"developer\s+mode\s+enabled", re.IGNORECASE), "DEVELOPER_MODE_BYPASS"),
        (re.compile(r"bypass\s+(security|filters|safety)", re.IGNORECASE), "SECURITY_BYPASS"),
        (re.compile(r"as\s+an\s+ai\s+without\s+(restrictions|limits|rules)", re.IGNORECASE), "UNRESTRICTED_MODE"),
    ]

    # Invisible & problematic Unicode control characters used for obfuscation
    INVISIBLE_CHARS: Set[str] = {
        "\u200b",  # Zero-width space
        "\u200c",  # Zero-width non-joiner
        "\u200d",  # Zero-width joiner
        "\u2060",  # Word joiner
        "\ufeff",  # Zero-width no-break space (BOM)
        "\u00ad",  # Soft hyphen
        "\u200e",  # Left-to-right mark
        "\u200f",  # Right-to-left mark
    }

    def normalize(self, raw_text: str) -> str:
        """Applies Unicode NFKC normalization and strips invisible obfuscation characters."""
        # Step 1: NFKC Unicode decomposition and recombination (defers homographic attacks)
        norm = unicodedata.normalize("NFKC", raw_text)
        # Step 2: Strip invisible control/zero-width characters
        cleaned_chars = [c for c in norm if c not in self.INVISIBLE_CHARS and (c.isprintable() or c in "\r\n\t")]
        return "".join(cleaned_chars)

    def _decode_base64_candidates(self, text: str) -> List[str]:
        """Scans for Base64 blocks in input and attempts decoding to detect hidden payloads."""
        decoded_payloads: List[str] = []
        # Match potential Base64 strings (length >= 12, alphanumeric + '+' '/' '=')
        tokens = re.findall(r"[A-Za-z0-9+/]{12,}={0,2}", text)
        for tok in tokens:
            try:
                raw_bytes = base64.b64decode(tok, validate=True)
                dec_str = raw_bytes.decode("utf-8", errors="ignore")
                if len(dec_str) >= 6 and any(c.isalpha() for c in dec_str):
                    decoded_payloads.append(dec_str)
            except (ValueError, binascii.Error):
                continue
        return decoded_payloads

    def inspect(self, raw_prompt: str) -> Tuple[str, bool, List[str]]:
        """
        Inspects prompt for security violations.
        Returns: (normalized_prompt, is_safe, list_of_violation_codes)
        """
        cleaned_prompt = self.normalize(raw_prompt)
        violations: List[str] = []

        # Check against normal clean prompt
        for pattern, code in self.FORBIDDEN_PATTERNS:
            if pattern.search(cleaned_prompt):
                if code not in violations:
                    violations.append(code)

        # Check against Base64 decoded payloads (if any)
        b64_payloads = self._decode_base64_candidates(cleaned_prompt)
        for payload in b64_payloads:
            for pattern, code in self.FORBIDDEN_PATTERNS:
                if pattern.search(payload):
                    violation_code = f"OBFUSCATED_{code}"
                    if violation_code not in violations:
                        violations.append(violation_code)

        is_safe = len(violations) == 0
        if not is_safe:
            log.warning("[PromptInjectionGuard] Neutralized threat. Violations detected: %s", violations)

        return cleaned_prompt, is_safe, violations


# =============================================================================
# Tool Authorization Gateway (Secure Tool Executor)
# =============================================================================

@dataclass
class ToolDefinition:
    name: str
    description: str
    handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]
    required_permissions: Set[str] = field(default_factory=set)
    required_role: Optional[str] = None
    tenant_scoped_param: Optional[str] = "tenant_id"
    user_scoped_param: Optional[str] = None
    admin_only: bool = False


class ToolAuthorizationGateway:
    """
    Unbypassable security perimeter between LLM tool outputs and system execution.
    Verifies tenant isolation, user IDOR protection, and strict RBAC privileges.
    """
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]],
        required_permissions: Optional[Set[str]] = None,
        required_role: Optional[str] = None,
        tenant_scoped_param: Optional[str] = "tenant_id",
        user_scoped_param: Optional[str] = None,
        admin_only: bool = False
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            handler=handler,
            required_permissions=required_permissions or set(),
            required_role=required_role,
            tenant_scoped_param=tenant_scoped_param,
            user_scoped_param=user_scoped_param,
            admin_only=admin_only
        )
        log.debug("[ToolAuthorizationGateway] Registered secure tool '%s'", name)

    async def execute_tool_call(self, tool_name: str, arguments: Dict[str, Any], scope: AuthorizationScope) -> Dict[str, Any]:
        tool = self._tools.get(tool_name)
        if not tool:
            raise ToolNotFoundError(f"Tool '{tool_name}' is not registered in the gateway.")

        log.info("[ToolGateway] Evaluating access for tool '%s' under scope (tenant=%s, user=%s, admin=%s)",
                 tool_name, scope.tenant_id, scope.user_id, scope.is_admin)

        # 1. Admin boundary verification
        if tool.admin_only and not scope.is_admin:
            raise ToolAuthorizationError(f"Tool '{tool_name}' requires administrator privileges.")

        # 2. Role boundary verification
        if tool.required_role and not scope.is_admin:
            if tool.required_role not in scope.roles:
                raise ToolAuthorizationError(f"Missing required role '{tool.required_role}' for tool '{tool_name}'.")

        # 3. Permission boundary verification
        if tool.required_permissions and not scope.is_admin:
            if not tool.required_permissions.issubset(scope.permissions):
                missing = tool.required_permissions - scope.permissions
                raise ToolAuthorizationError(f"Missing permissions {missing} for tool '{tool_name}'.")

        # 4. Tenant isolation boundary verification
        if tool.tenant_scoped_param and tool.tenant_scoped_param in arguments:
            arg_tenant = arguments[tool.tenant_scoped_param]
            # Convert to int if possible for fair comparison
            try:
                arg_tenant_val = int(arg_tenant)
                scope_tenant_val = int(scope.tenant_id)
            except (ValueError, TypeError):
                arg_tenant_val = str(arg_tenant)
                scope_tenant_val = str(scope.tenant_id)

            if arg_tenant_val != scope_tenant_val and not scope.is_admin:
                log.error("[ToolGateway] Cross-tenant attempt! Scope tenant: %s | Arg tenant: %s", scope.tenant_id, arg_tenant)
                raise ToolTenantIsolationError(f"Tenant isolation violation: cannot execute tool on tenant '{arg_tenant}' from scope tenant '{scope.tenant_id}'.")

        # 5. User IDOR isolation boundary verification
        if tool.user_scoped_param and tool.user_scoped_param in arguments:
            arg_user = arguments[tool.user_scoped_param]
            try:
                arg_user_val = int(arg_user)
                scope_user_val = int(scope.user_id) if scope.user_id is not None else -1
            except (ValueError, TypeError):
                arg_user_val = str(arg_user)
                scope_user_val = str(scope.user_id)

            if arg_user_val != scope_user_val and not scope.is_admin:
                log.error("[ToolGateway] IDOR attempt! Scope user: %s | Arg user: %s", scope.user_id, arg_user)
                raise ToolIDORViolationError(f"IDOR security violation: cannot operate on user '{arg_user}' from scope of user '{scope.user_id}'.")

        # All perimeter defense checks passed; execute step handler safely
        log.debug("[ToolGateway] Authorization granted. Executing handler for '%s'", tool_name)
        return await tool.handler(arguments)


# Global singleton instances for direct import
prompt_injection_guard = PromptInjectionGuard()
tool_authorization_gateway = ToolAuthorizationGateway()
