"""
Tiffany OS — Hexagonal Ports & Adapters: Gateway Protocol Abstraction
=====================================================================
Establishes clear architectural boundaries so business domain rules NEVER depend directly
on Discord client implementations. Allows seamless routing across Discord, Slack,
Microsoft Teams, Telegram, and enterprise Web Dashboards without altering core logic.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Coroutine
import time
import uuid

class GatewayType(Enum):
    DISCORD = "discord"
    SLACK = "slack"
    MS_TEAMS = "teams"
    WEB_SOCKET = "websocket"
    MOBILE_APP = "mobile"

@dataclass(frozen=True)
class NormalizedCommandRequest:
    """Platform-agnostic representation of an incoming user directive or slash command."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    gateway: GatewayType = GatewayType.DISCORD
    origin_channel_id: str = ""
    origin_guild_id: str = ""
    user_id: str = ""
    username: str = ""
    command_name: str = ""
    raw_text_prompt: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    received_at: float = field(default_factory=time.time)

@dataclass(frozen=True)
class NormalizedGatewayResponse:
    """Universal outbound payload suitable for rendering in any target communication gateway."""
    response_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target_channel_id: str = ""
    target_user_id: Optional[str] = None
    text_content: str = ""
    embed_title: Optional[str] = None
    embed_color_hex: str = "#FF80AB" # Tiffany Brand Pink
    interactive_buttons: List[Dict[str, str]] = field(default_factory=list)
    audio_stream_uri: Optional[str] = None
    is_ephemeral: bool = False

class AbstractGatewayPort(ABC):
    """
    Port abstraction defining mandatory lifecycle and presentation contracts
    for client gateways connecting to the Tiffany AI Operating System.
    """
    def __init__(self, gateway_type: GatewayType) -> None:
        self.gateway_type = gateway_type
        self.is_connected = False

    @abstractmethod
    async def initialize_connection(self) -> bool:
        """Establishes upstream websocket/webhook links with external platform providers."""
        pass

    @abstractmethod
    async def dispatch_response(self, response: NormalizedGatewayResponse) -> bool:
        """Translates normalized OS responses into native platform visual components."""
        pass

    @abstractmethod
    async def terminate_connection(self) -> None:
        """Gracefully disconnects sockets without terminating ongoing user transactions."""
        pass


class DiscordGatewayAdapter(AbstractGatewayPort):
    """
    Adapter implementation translating Discord commands/events into Tiffany Core requests.
    """
    def __init__(self) -> None:
        super().__init__(GatewayType.DISCORD)

    async def initialize_connection(self) -> bool:
        self.is_connected = True
        return True

    async def dispatch_response(self, response: NormalizedGatewayResponse) -> bool:
        # In runtime, translates NormalizedGatewayResponse into discord.Embed & View
        return True

    async def terminate_connection(self) -> None:
        self.is_connected = False


class SlackGatewayAdapter(AbstractGatewayPort):
    """
    Adapter demonstrating enterprise platform extensibility for Slack Workspaces.
    """
    def __init__(self) -> None:
        super().__init__(GatewayType.SLACK)

    async def initialize_connection(self) -> bool:
        self.is_connected = True
        return True

    async def dispatch_response(self, response: NormalizedGatewayResponse) -> bool:
        # Translates response into Slack Block Kit formatting JSON
        return True

    async def terminate_connection(self) -> None:
        self.is_connected = False
