"""Launcher signal forwarding — local unit tests (no subprocess bots)."""

from __future__ import annotations

import signal
import unittest
import unittest.mock

import launcher


class TestLauncherSignals(unittest.TestCase):
    def test_sigterm_maps_to_keyboard_interrupt_on_unix(self):
        if launcher.sys.platform == "win32":
            self.skipTest("SIGTERM handler only on Unix")
        with self.assertRaises(KeyboardInterrupt):
            launcher._sigterm_handler(signal.SIGTERM, None)

    def test_start_bot_uses_new_session_on_unix(self):
        if launcher.sys.platform == "win32":
            self.skipTest("process groups via start_new_session on Unix only")
        with unittest.mock.patch("launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = unittest.mock.MagicMock()
            with unittest.mock.patch("launcher.open", unittest.mock.mock_open()):
                launcher.start_bot({"file": "notices.py", "name": "test"})
            _, kwargs = mock_popen.call_args
            self.assertTrue(kwargs.get("start_new_session"))


if __name__ == "__main__":
    unittest.main()
