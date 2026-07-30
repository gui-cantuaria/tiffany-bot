"""
Tiffany Bot — Anti-Bot Scraper Bypass (Phase 3)
===============================================
Provides advanced fetching logic for Premium 'News' configurations
to bypass basic anti-bot protections (like Cloudflare challenge blocks)
on Custom RSS feeds.
"""

import asyncio
import logging
import random
from typing import Optional

import aiohttp
import feedparser

log = logging.getLogger("tiffany-bot")

# A rotating list of modern User-Agents to prevent basic blocking
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
]

def get_random_headers() -> dict[str, str]:
    """Generates human-like headers to bypass simple blocks."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
    }


async def fetch_feed_premium(url: str, bypass_enabled: bool) -> Optional[feedparser.FeedParserDict]:
    """
    Fetches an RSS feed. If bypass_enabled is True, it uses rotating headers
    and standard browser impersonation to fetch the raw XML, then parses it.
    """
    if not bypass_enabled:
        # Standard fallback for non-premium or when bypass is disabled
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    feedparser.parse, url,
                    agent="TiffanyBot/2.0 (+https://discord.gg/tiffany)"
                ),
                timeout=15,
            )
        except Exception as e:
            log.warning("Standard feed fetch failed for %s: %s", url, e)
            return None

    # Premium Bypass Route
    headers = get_random_headers()
    connector = aiohttp.TCPConnector(limit=5, ssl=False)  # Some old RSS feeds have broken SSL
    
    try:
        async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
            # Adding a slight random jitter to prevent pattern recognition
            await asyncio.sleep(random.uniform(0.1, 1.5))
            
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    raw_xml = await resp.text()
                    # feedparser can parse raw string directly
                    return await asyncio.to_thread(feedparser.parse, raw_xml)
                else:
                    log.warning("Premium fetch got HTTP %d for %s", resp.status, url)
                    return None
                    
    except asyncio.TimeoutError:
        log.warning("Premium feed fetch timed out for %s", url)
    except Exception as e:
        log.exception("Premium feed fetch error for %s: %s", url, e)

    return None
