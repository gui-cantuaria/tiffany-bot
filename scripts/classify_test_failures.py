#!/usr/bin/env python3
# Tiffany OS — Phase 10: Automated Test Failure Classification & Diagnostic Engine
# Parses test run output and tracebacks to categorize CI and local failures into actionable failure domains:
# [TEST FAILURE], [IMPORT FAILURE], [ENVIRONMENT FAILURE], [INFRASTRUCTURE FAILURE], [ACTUAL REGRESSION], or [FLAKY TEST].

import sys
import subprocess
import re
from typing import Tuple, List

class FailureClassifier:
    """
    Analyzes test output and tracebacks to classify the failure root cause.
    Prevents treating every test drop as an application logic bug or rerunning blindly.
    """

    @staticmethod
    def classify(output_text: str, command: str = "") -> Tuple[str, str, str]:
        """
        Returns: (Classification Tag, Root Cause Diagnosis, Recommended Action)
        """
        text_lower = output_text.lower()

        # 1. IMPORT FAILURE
        if "importerror" in text_lower or "modulenotfounderror" in text_lower or "cannot import name" in text_lower:
            match = re.search(r"(?:ModuleNotFoundError|ImportError):.*", output_text, re.IGNORECASE)
            err_msg = match.group(0) if match else "Import graph error detected"
            return (
                "[IMPORT FAILURE]",
                f"A Python dependency or circular import broke module loading: {err_msg}",
                "Do NOT patch logic blindly. Verify virtualenv packages and check circular import boundaries (Phase 7)."
            )

        # 2. INFRASTRUCTURE FAILURE
        if any(w in text_lower for w in ("connection refused", "socket.error", "could not connect to server", "connection reset", "redis_client", "asyncpg.exceptions.cannotconnectnowerror", "connectiontimedouterror")):
            return (
                "[INFRASTRUCTURE FAILURE]",
                "An external service (PostgreSQL 16 DB or Redis 7 cache) is offline or unreachable.",
                "Verify local Docker Compose containers or VPS daemon status. This is NOT an application code defect."
            )

        # 3. ENVIRONMENT FAILURE
        if any(w in text_lower for w in ("missing environment variable", "stripe_secret_key", "openrouter_api_key", "token not found", "invalid auth", "permission denied")):
            return (
                "[ENVIRONMENT FAILURE]",
                "Required runtime secrets or configuration environment variables are absent or misconfigured.",
                "Check .env file or GitHub Actions Repository Secrets. Ensure optional degraded fallback paths are preserved."
            )

        # 4. ACTUAL REGRESSION (Music / Rollback / Critical Invariants)
        if any(m in command or m in text_lower for m in ("test_music_regression", "test_deployment_rollback", "gate c", "voice subsystem", "lavalink")):
            return (
                "[ACTUAL REGRESSION]",
                "A critical reliability boundary or legacy minimalist user experience invariant was violated.",
                "CRITICAL: Do NOT deploy to production. Review recent changes against tiffany_voice.py and release locks."
            )

        # 5. FLAKY TEST (Timeout or Async Event Loop closed)
        if any(w in text_lower for w in ("asyncio.exceptions.timeoutout", "timeout error", "event loop is closed", "concurrent future cancelled", "task was destroyed but it is pending")):
            return (
                "[FLAKY TEST / ASYNC TIMEOUT]",
                "An asyncio timing condition or gateway mock reconnect timeout occurred under heavy CPU load.",
                "Review asyncio watchdog cleanup idempotence (Phase 3 & 5) and task termination order."
            )

        # 6. GENERAL TEST FAILURE
        return (
            "[TEST FAILURE]",
            "Standard business logic assertion or test expectation failure occurred.",
            "Inspect test traceback and verify if recent code adjustments altered expected return data models."
        )

    @classmethod
    def analyze_and_report(cls, output: str, command: str) -> str:
        tag, diagnosis, action = cls.classify(output, command)
        report = (
            "\n"
            "========================================================================\n"
            "🔍 TIFFANY OS — AUTOMATED TEST FAILURE CLASSIFICATION & DIAGNOSTIC REPORT\n"
            "========================================================================\n"
            f"Classification  : {tag}\n"
            f"Command Executed: {command}\n\n"
            f"Root Cause      : {diagnosis}\n"
            f"Actionable Fix  : {action}\n"
            "========================================================================\n"
        )
        return report

def main():
    if len(sys.argv) < 2:
        print("Usage: python classify_test_failures.py <command to run...>")
        sys.exit(0)

    cmd_args = sys.argv[1:]
    cmd_str = " ".join(cmd_args)
    
    print(f"[Phase 10] Executing under diagnostic classification harness: {cmd_str}")
    process = subprocess.Popen(
        cmd_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    
    output, _ = process.communicate()
    print(output)
    
    if process.returncode != 0:
        report = FailureClassifier.analyze_and_report(output, cmd_str)
        print(report)
        sys.exit(process.returncode)
    else:
        print("[Phase 10] Execution PASSED without failures.")
        sys.exit(0)

if __name__ == "__main__":
    main()
