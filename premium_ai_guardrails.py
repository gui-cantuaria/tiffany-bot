"""
Tiffany Bot — AI Content Guardrails (Phase 3)
==============================================
Classifies raw News and Offers content into SAFE, NSFW, or ILLEGAL/GORE
to respect the premium configuration settings and protect the bot.
"""

import json
import logging
from typing import Any

import aiohttp

log = logging.getLogger("tiffany-bot")

# Assuming OPENROUTER_API_KEY is available in env
import os
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ---------------------------------------------------------------------------
# Gemini Tool/Function Calling Structure
# ---------------------------------------------------------------------------

CLASSIFICATION_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_content",
        "description": "Evaluates the raw text of a news article or product offer and classifies it.",
        "parameters": {
            "type": "object",
            "properties": {
                "classification": {
                    "type": "string",
                    "enum": ["SAFE", "NSFW", "ILLEGAL_GORE"],
                    "description": "SAFE: Normal tech/gaming news or safe products. NSFW: Adult toys, pornography, sexually explicit content. ILLEGAL_GORE: Violence, gore, illegal substances, weapons, hate speech."
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score from 0.0 to 1.0"
                },
                "reasoning": {
                    "type": "string",
                    "description": "A brief 1-sentence explanation of why this classification was chosen."
                }
            },
            "required": ["classification", "confidence", "reasoning"]
        }
    }
}

async def classify_content(raw_title: str, raw_description: str) -> dict[str, Any]:
    """
    Calls the OpenRouter API (Gemini 3.1 Flash) to evaluate the content.
    Returns a dict with 'classification', 'confidence', and 'reasoning'.
    """
    if not OPENROUTER_API_KEY:
        log.error("OPENROUTER_API_KEY not set. Operating in Fail-Closed mode: blocking request.")
        return {"classification": "ILLEGAL_GORE", "confidence": 1.0, "reasoning": "Fail-Closed: Missing API Key"}

    prompt = (
        "You are an AI Safety Guardrail for a Discord bot.\n"
        "Analyze the following content (Title and Description) and classify it.\n"
        "Strictly use the 'classify_content' function to respond.\n\n"
        f"TITLE: {raw_title}\n"
        f"DESCRIPTION: {raw_description}"
    )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://discord.com",
        "X-Title": "Tiffany Bot Guardrails",
    }

    payload = {
        "model": "google/gemini-3.1-flash-lite",
        "messages": [{"role": "user", "content": prompt}],
        "tools": [CLASSIFICATION_TOOL],
        "tool_choice": {"type": "function", "function": {"name": "classify_content"}},
        "temperature": 0.1,  # Low temperature for consistent classification
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    message = data["choices"][0]["message"]
                    
                    if "tool_calls" in message and message["tool_calls"]:
                        func_args = message["tool_calls"][0]["function"]["arguments"]
                        return json.loads(func_args)
                else:
                    log.error("Failed to classify content: HTTP %d", resp.status)
        except Exception as e:
            log.exception("Error during API classification: %s", e)

    # Fail-Closed: Block content if API fails to protect community and maintain compliance
    return {"classification": "ILLEGAL_GORE", "confidence": 1.0, "reasoning": "Fail-Closed: Moderation API Error"}


# ---------------------------------------------------------------------------
# Integration with Guild Configuration
# ---------------------------------------------------------------------------
def should_allow_content(classification_result: dict, guild_nsfw_enabled: bool) -> bool:
    """
    Determines if the content should be posted based on the AI classification
    and the server's Premium NSFW setting.
    """
    cls = classification_result.get("classification", "SAFE")
    
    if cls == "ILLEGAL_GORE":
        return False  # Hard block, never post
        
    if cls == "NSFW":
        return guild_nsfw_enabled  # Only post if the guild explicitly enabled it
        
    return True  # SAFE content is always allowed
