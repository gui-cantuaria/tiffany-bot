# Tiffany OS — Phase 10: Automated Test Failure Classification Verification Suite
# Enforces that CI and diagnostic tooling correctly distinguishes between application defects, infrastructure outages, imports, and regressions.

import unittest
import sys
import os

# Ensure scripts directory is accessible for import
sys.path.append(os.path.join(os.path.dirname(__file__), "scripts"))
try:
    from classify_test_failures import FailureClassifier
except ImportError:
    import importlib.util
    spec = importlib.util.spec_from_file_location("classify_test_failures", os.path.join(os.path.dirname(__file__), "scripts", "classify_test_failures.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    FailureClassifier = module.FailureClassifier

class TestFailureClassificationEngine(unittest.TestCase):
    """
    Verifies Phase 10 diagnostic categories.
    """

    def test_01_import_failure_classification(self):
        log_sample = "Traceback: ModuleNotFoundError: No module named 'stripe_panel_v2'"
        tag, diag, action = FailureClassifier.classify(log_sample, "pytest test_smoke.py")
        self.assertEqual(tag, "[IMPORT FAILURE]")
        self.assertIn("Python dependency or circular import", diag)

    def test_02_infrastructure_failure_classification(self):
        log_sample = "asyncpg.exceptions.CannotConnectNowError: connection refused to port 5432 PostgreSQL server offline"
        tag, diag, action = FailureClassifier.classify(log_sample, "pytest test_outbox.py")
        self.assertEqual(tag, "[INFRASTRUCTURE FAILURE]")
        self.assertIn("external service", diag)

    def test_03_environment_failure_classification(self):
        log_sample = "RuntimeError: Missing environment variable OPENROUTER_API_KEY during AI model init"
        tag, diag, action = FailureClassifier.classify(log_sample, "python test_ai.py")
        self.assertEqual(tag, "[ENVIRONMENT FAILURE]")
        self.assertIn("runtime secrets or configuration", diag)

    def test_04_actual_regression_classification(self):
        log_sample = "AssertionError: 'Now Playing' thumbnail bulky field detected! Legacy minimalist style broken!"
        tag, diag, action = FailureClassifier.classify(log_sample, "python -m unittest test_music_regression")
        self.assertEqual(tag, "[ACTUAL REGRESSION]")
        self.assertIn("legacy minimalist user experience invariant was violated", diag)

    def test_05_flaky_async_timeout_classification(self):
        log_sample = "asyncio.exceptions.TimeoutError: event loop is closed before watchdog finished"
        tag, diag, action = FailureClassifier.classify(log_sample, "pytest test_phase11_lifecycle.py")
        self.assertEqual(tag, "[FLAKY TEST / ASYNC TIMEOUT]")
        self.assertIn("asyncio timing condition", diag)

    def test_06_general_test_failure_classification(self):
        log_sample = "AssertionError: expected 500 got 200 in payment pricing calculation"
        tag, diag, action = FailureClassifier.classify(log_sample, "pytest test_payments_phase3.py")
        self.assertEqual(tag, "[TEST FAILURE]")
        self.assertIn("Standard business logic assertion", diag)

    def test_07_formatted_diagnostic_report_generation(self):
        log_sample = "ImportError: cannot import name 'has_premium' from 'infra.premium'"
        report = FailureClassifier.analyze_and_report(log_sample, "python -m unittest test_smoke")
        self.assertIn("AUTOMATED TEST FAILURE CLASSIFICATION & DIAGNOSTIC REPORT", report)
        self.assertIn("[IMPORT FAILURE]", report)

if __name__ == "__main__":
    unittest.main()
