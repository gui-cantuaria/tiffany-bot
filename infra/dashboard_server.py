"""
Tiffany Bot — Internal Dashboard API Server
===========================================
Exposes REST endpoints for the Next.js frontend to read and write
guild configurations, interacting directly with the bot's memory cache.
"""

import os
import logging
import asyncio
from aiohttp import web
import guild_config

log = logging.getLogger("tiffany-bot")

_guild_locks = {}

def _get_guild_lock(guild_id: int) -> asyncio.Lock:
    if guild_id not in _guild_locks:
        _guild_locks[guild_id] = asyncio.Lock()
    return _guild_locks[guild_id]

DASHBOARD_API_HOST = os.getenv("DASHBOARD_API_HOST", "127.0.0.1")
DASHBOARD_API_PORT = int(os.getenv("DASHBOARD_API_PORT", "8081"))

async def _get_guild_config(request: web.Request) -> web.Response:
    guild_id_str = request.match_info.get("guild_id")
    if not guild_id_str or not guild_id_str.isdigit():
        return web.json_response({"error": "Invalid guild ID"}, status=400)
    
    guild_id = int(guild_id_str)
    # Get config (loads from disk if not cached)
    config = guild_config.get_guild_config(guild_id)
    return web.json_response({"guild_id": guild_id, "config": config})

async def _update_guild_config(request: web.Request) -> web.Response:
    guild_id_str = request.match_info.get("guild_id")
    if not guild_id_str or not guild_id_str.isdigit():
        return web.json_response({"error": "Invalid guild ID"}, status=400)
    
    guild_id = int(guild_id_str)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    lock = _get_guild_lock(guild_id)
    async with lock:
        # We merge with existing config to not overwrite unprovided fields
        current_config = guild_config.get_guild_config(guild_id)
        
        # Strict type casting and validation for allowed top-level fields
        if "strict_filter" in data and type(data["strict_filter"]) is bool:
            current_config["strict_filter"] = data["strict_filter"]
        if "anti_spam" in data and type(data["anti_spam"]) is bool:
            current_config["anti_spam"] = data["anti_spam"]
        
        # Integers (IDs)
        for key in ["dj_role", "mod_log_channel", "offers_channel"]:
            if key in data:
                val = data[key]
                current_config[key] = int(val) if val else None

        # Lists
        if "blacklist" in data and isinstance(data["blacklist"], list):
            current_config["blacklist"] = [int(x) for x in data["blacklist"] if str(x).isdigit()]
        
        if "allowed_categories" in data and isinstance(data["allowed_categories"], list):
            current_config["allowed_categories"] = [str(x) for x in data["allowed_categories"]]
            
        # Dicts
        if "affiliate_tags" in data and isinstance(data["affiliate_tags"], dict):
            current_config["affiliate_tags"] = {str(k): str(v) for k, v in data["affiliate_tags"].items()}
                
        if "features" in data and isinstance(data["features"], dict):
            for f_key, f_val in data["features"].items():
                if f_key in current_config["features"] and type(f_val) is bool:
                    current_config["features"][f_key] = f_val
                    
        await guild_config.async_save_guild_config(guild_id, current_config)
    
    log.info("Dashboard API updated config for guild %s", guild_id)
    
    return web.json_response({"status": "success", "config": current_config})

async def _health_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "healthy", "service": "tiffany-dashboard-api"})

_runner = None

async def start_dashboard_server() -> None:
    global _runner
    if _runner is not None:
        return

    app = web.Application()
    # Add CORS headers since frontend might be on a different port during dev
    
    async def cors_middleware(app, handler):
        async def middleware_handler(request):
            if request.method == "OPTIONS":
                response = web.Response()
            else:
                response = await handler(request)
            
            # Very permissive for internal dashboard API, trust the network
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return response
        return middleware_handler
        
    app.middlewares.append(cors_middleware)
    
    app.router.add_get("/api/health", _health_handler)
    app.router.add_get("/api/guilds/{guild_id}/config", _get_guild_config)
    app.router.add_patch("/api/guilds/{guild_id}/config", _update_guild_config)

    _runner = web.AppRunner(app)
    await _runner.setup()
    site = web.TCPSite(_runner, DASHBOARD_API_HOST, DASHBOARD_API_PORT)
    await site.start()
    
    log.info("Dashboard API server started on %s:%d", DASHBOARD_API_HOST, DASHBOARD_API_PORT)

async def stop_dashboard_server() -> None:
    global _runner
    if _runner is not None:
        await _runner.cleanup()
        _runner = None
        log.info("Dashboard API server stopped")
