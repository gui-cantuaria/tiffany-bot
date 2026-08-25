import asyncio
import aiohttp
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import infra.dashboard_server as dashboard_server
import guild_config

import unittest

class TestDashboardConcurrency(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_concurrent_updates(self):
        # Point the config file to a temporary file
        test_config_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_guild_config.json"))
        guild_config._CONFIG_FILE = test_config_file
        
        if os.path.exists(test_config_file):
            os.remove(test_config_file)
            
        guild_config._cache = {}
        guild_config._loaded = False
        
        # Initialize basic config for guild 9999
        guild_config.save_guild_config(9999, {
            "strict_filter": False,
            "anti_spam": False,
            "dj_role": None,
            "features": {"music": True}
        })

        # Start the API server on a test port
        dashboard_server.DASHBOARD_API_HOST = "127.0.0.1"
        dashboard_server.DASHBOARD_API_PORT = 18082
        
        await dashboard_server.start_dashboard_server()
        
        try:
            async with aiohttp.ClientSession() as session:
                tasks = []
                
                for i in range(50):
                    payload = {
                        "strict_filter": bool(i % 2 == 0),
                        "dj_role": 1000 + i,
                        "features": {"chat": bool(i % 2 == 1)}
                    }
                    url = "http://127.0.0.1:18082/api/guilds/9999/config"
                    tasks.append(session.patch(url, json=payload))
                
                responses = await asyncio.gather(*tasks)
                
                for r in responses:
                    self.assertEqual(r.status, 200, f"FAILED: Status {r.status}")
                    data = await r.json()
                    self.assertEqual(data.get("status"), "success", "FAILED: Did not return success")

            # Verify final state
            with open(test_config_file, "r") as f:
                final_data = json.load(f)
                
            self.assertIn("9999", final_data)
            cfg = final_data["9999"]
            self.assertIsInstance(cfg["strict_filter"], bool)
            self.assertIsInstance(cfg["dj_role"], int)
            self.assertIsInstance(cfg["features"]["chat"], bool)
            
        finally:
            await dashboard_server.stop_dashboard_server()
            if os.path.exists(test_config_file):
                os.remove(test_config_file)

if __name__ == "__main__":
    unittest.main()
