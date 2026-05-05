"""Home Assistant tool for smart home device control."""

import os
from typing import Any, Awaitable, Callable

import aiohttp
from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage


class HaosTool(Tool):
    """
    Unified tool for Home Assistant OS device control.

    Supports multiple operations:
    - list: List all available entities or filter by domain (switch, light, camera, etc.)
    - get: Get detailed information about a specific entity
    - turn_on: Turn on a switch or light
    - turn_off: Turn off a switch or light
    - toggle: Toggle a switch or light state
    - capture_image: Capture image from a camera entity
    - call_service: Call any Home Assistant service with custom parameters

    Configuration is read from environment variables in ~/.nanobot/workspace/.env:
    - HAOS_URL: Home Assistant URL (default: http://homeassistant.local:8123)
    - HAOS_API_TOKEN: Long-lived access token
    """

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
        default_message_id: str | None = None,
    ):
        """Initialize the Home Assistant tool."""
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id
        self._default_message_id = default_message_id

        # Load configuration from environment
        self.ha_url = os.getenv("HAOS_URL", "http://homeassistant.local:8123").rstrip("/")
        self.api_token = os.getenv("HAOS_API_TOKEN", "")

        if not self.api_token:
            logger.warning("HAOS_API_TOKEN not set in environment variables")

    @property
    def name(self) -> str:
        return "haos"

    @property
    def description(self) -> str:
        return (
            "Home Assistant OS tool for smart home device control. "
            "Supports listing entities, controlling switches/lights, capturing camera images, "
            "and calling any Home Assistant service. "
            "Configuration is loaded from environment variables (HAOS_URL, HAOS_API_TOKEN). "
            "Use 'list' mode to discover available devices and their entity IDs."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": [
                        "list",
                        "get",
                        "turn_on",
                        "turn_off",
                        "toggle",
                        "capture_image",
                        "call_service",
                    ],
                    "description": (
                        "Operation mode:\n"
                        "- list: List all entities or filter by domain\n"
                        "- get: Get detailed entity information\n"
                        "- turn_on: Turn on a switch/light\n"
                        "- turn_off: Turn off a switch/light\n"
                        "- toggle: Toggle switch/light state\n"
                        "- capture_image: Capture camera image\n"
                        "- call_service: Call custom Home Assistant service"
                    ),
                },
                "entity_id": {
                    "type": "string",
                    "description": (
                        "[Required for get/turn_on/turn_off/toggle/capture_image] "
                        "Entity ID (e.g., 'switch.camera_power', 'light.living_room')"
                    ),
                },
                "domain": {
                    "type": "string",
                    "description": (
                        "[Optional for list mode] Filter entities by domain "
                        "(e.g., 'switch', 'light', 'camera', 'sensor'). "
                        "Leave empty to list all entities."
                    ),
                },
                "service_domain": {
                    "type": "string",
                    "description": (
                        "[Required for call_service mode] Service domain (e.g., 'switch', 'light', 'camera')"
                    ),
                },
                "service_name": {
                    "type": "string",
                    "description": (
                        "[Required for call_service mode] Service name (e.g., 'turn_on', 'snapshot')"
                    ),
                },
                "service_data": {
                    "type": "object",
                    "description": (
                        "[Optional for call_service mode] Service data as key-value pairs. "
                        'Example: {"entity_id": "switch.test", "brightness": 128}'
                    ),
                },
                "save_path": {
                    "type": "string",
                    "description": (
                        "[Optional for capture_image mode] Path to save captured image. "
                        "Default: ~/.nanobot/media/image/camera_capture.jpg"
                    ),
                },
            },
            "required": ["mode"],
        }

    def set_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Set the current message context."""
        self._default_channel = channel
        self._default_chat_id = chat_id
        self._default_message_id = message_id

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    async def execute(
        self,
        mode: str,
        entity_id: str = "",
        domain: str = "",
        service_domain: str = "",
        service_name: str = "",
        service_data: dict[str, Any] | None = None,
        save_path: str = "",
        **kwargs: Any,
    ) -> str:
        """
        Execute Home Assistant tool based on mode.

        Args:
            mode: Operation mode (list, get, turn_on, turn_off, toggle, capture_image, call_service)
            entity_id: Entity ID for entity-specific operations
            domain: Domain filter for list mode
            service_domain: Service domain for call_service mode
            service_name: Service name for call_service mode
            service_data: Service data for call_service mode
            save_path: Save path for captured images

        Returns:
            Result message based on operation
        """
        if not self.api_token:
            return (
                "Error: HAOS_API_TOKEN not configured. Please set it in ~/.nanobot/workspace/.env"
            )

        try:
            if mode == "list":
                return await self._execute_list(domain=domain)
            elif mode == "get":
                if not entity_id:
                    return "Error: entity_id is required for get mode"
                return await self._execute_get(entity_id=entity_id)
            elif mode == "turn_on":
                if not entity_id:
                    return "Error: entity_id is required for turn_on mode"
                return await self._execute_turn_on(entity_id=entity_id)
            elif mode == "turn_off":
                if not entity_id:
                    return "Error: entity_id is required for turn_off mode"
                return await self._execute_turn_off(entity_id=entity_id)
            elif mode == "toggle":
                if not entity_id:
                    return "Error: entity_id is required for toggle mode"
                return await self._execute_toggle(entity_id=entity_id)
            elif mode == "capture_image":
                if not entity_id:
                    return "Error: entity_id is required for capture_image mode"
                return await self._execute_capture_image(entity_id=entity_id, save_path=save_path)
            elif mode == "call_service":
                if not service_domain or not service_name:
                    return (
                        "Error: service_domain and service_name are required for call_service mode"
                    )
                return await self._execute_call_service(
                    domain=service_domain,
                    service=service_name,
                    service_data=service_data or {},
                )
            else:
                return f"Error: Invalid mode '{mode}'. Must be one of: list, get, turn_on, turn_off, toggle, capture_image, call_service"
        except Exception as e:
            logger.error(f"HaosTool execution error: {e}")
            return f"Error: {str(e)}"

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make API request to Home Assistant."""
        url = f"{self.ha_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=headers, **kwargs) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 201:
                        return {"status": "success"}
                    else:
                        error_text = await response.text()
                        return {"error": f"HTTP {response.status}: {error_text}"}
        except Exception as e:
            logger.error(f"HAOS connection error: {e}")
            return {"error": f"Connection error: {str(e)}"}

    async def _execute_list(self, domain: str = "") -> str:
        """List entities, optionally filtered by domain."""
        result = await self._make_request("GET", "/api/states")

        if "error" in result:
            return f"Error: Failed to get entities - {result['error']}"

        entities = result
        if not entities:
            return "No entities found"

        # Filter by domain if specified
        if domain:
            entities = [e for e in entities if e["entity_id"].startswith(f"{domain}.")]

        if not entities:
            return f"No entities found for domain: {domain}"

        # Group by domain
        domains = {}
        for entity in entities:
            entity_id = entity["entity_id"]
            domain_name = entity_id.split(".")[0]
            if domain_name not in domains:
                domains[domain_name] = []
            domains[domain_name].append(entity)

        # Format output
        output = f"Found {len(entities)} entity(s):\n\n"

        for domain_name, domain_entities in sorted(domains.items()):
            output += f"=== {domain_name.upper()} ({len(domain_entities)}) ===\n"
            for entity in domain_entities[:20]:  # Limit to 20 per domain
                entity_id = entity["entity_id"]
                state = entity.get("state", "unknown")
                attrs = entity.get("attributes", {})
                friendly_name = attrs.get("friendly_name", "Unknown")

                output += f"  • {entity_id}\n"
                output += f"    Name: {friendly_name}\n"
                output += f"    State: {state}\n"

                # Show relevant attributes
                if domain_name == "camera" and attrs.get("entity_picture"):
                    output += f"    Has stream: Yes\n"
                elif domain_name in ["light", "switch"]:
                    output += f"\n"

            if len(domain_entities) > 20:
                output += f"  ... and {len(domain_entities) - 20} more\n"
            output += "\n"

        output += "\n💡 Use 'get' mode with entity_id to see full details"
        return output.strip()

    async def _execute_get(self, entity_id: str) -> str:
        """Get detailed information about a specific entity."""
        result = await self._make_request("GET", f"/api/states/{entity_id}")

        if "error" in result:
            return f"Error: Failed to get entity {entity_id} - {result['error']}"

        entity = result
        if not entity:
            return f"Error: Entity {entity_id} not found"

        output = f"Entity: {entity_id}\n"
        output += f"State: {entity.get('state', 'unknown')}\n"
        output += f"Last changed: {entity.get('last_changed', 'N/A')}\n"
        output += f"Last updated: {entity.get('last_updated', 'N/A')}\n\n"

        output += "Attributes:\n"
        attrs = entity.get("attributes", {})
        for key, value in attrs.items():
            output += f"  {key}: {value}\n"

        return output

    async def _execute_turn_on(self, entity_id: str) -> str:
        """Turn on a switch or light."""
        domain = entity_id.split(".")[0]
        result = await self._make_request(
            "POST",
            f"/api/services/{domain}/turn_on",
            json={"entity_id": entity_id},
        )

        if "error" in result:
            return f"Error: Failed to turn on {entity_id} - {result['error']}"

        # Get updated state
        await self._execute_get(entity_id)
        return f"✅ Successfully turned on {entity_id}"

    async def _execute_turn_off(self, entity_id: str) -> str:
        """Turn off a switch or light."""
        domain = entity_id.split(".")[0]
        result = await self._make_request(
            "POST",
            f"/api/services/{domain}/turn_off",
            json={"entity_id": entity_id},
        )

        if "error" in result:
            return f"Error: Failed to turn off {entity_id} - {result['error']}"

        # Get updated state
        await self._execute_get(entity_id)
        return f"✅ Successfully turned off {entity_id}"

    async def _execute_toggle(self, entity_id: str) -> str:
        """Toggle a switch or light."""
        domain = entity_id.split(".")[0]
        result = await self._make_request(
            "POST",
            f"/api/services/{domain}/toggle",
            json={"entity_id": entity_id},
        )

        if "error" in result:
            return f"Error: Failed to toggle {entity_id} - {result['error']}"

        # Get updated state
        entity_info = await self._execute_get(entity_id)
        return f"✅ Successfully toggled {entity_id}\n\n{entity_info}"

    async def _execute_capture_image(self, entity_id: str, save_path: str = "") -> str:
        """Capture image from a camera entity."""
        import os

        if not save_path:
            save_path = os.path.expanduser("~/.nanobot/media/image/camera_capture.jpg")

        # Ensure directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # Method 1: Use camera proxy endpoint
        url = f"{self.ha_url}/api/camera_proxy/{entity_id}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(save_path, "wb") as f:
                            f.write(content)

                        file_size = os.path.getsize(save_path)
                        msg = f"✅ Image captured successfully!\n"
                        msg += f"Saved to: {save_path}\n"
                        msg += f"File size: {file_size} bytes"

                        # Send image to user if callback is available
                        if self._send_callback:
                            media_data = {
                                "data": save_path,
                                "file_name": os.path.basename(save_path),
                            }
                            outbound_msg = OutboundMessage(
                                channel=self._default_channel,
                                chat_id=self._default_chat_id,
                                content=f"Camera image captured from {entity_id}",
                                media=[media_data],
                                metadata={"msg_type": "image", "file_type": "image/jpeg"},
                            )
                            await self._send_callback(outbound_msg)

                        return msg
                    else:
                        error_text = await response.text()
                        return (
                            f"Error: Failed to capture image - HTTP {response.status}: {error_text}"
                        )
        except Exception as e:
            return f"Error: Failed to capture image - {str(e)}"

    async def _execute_call_service(
        self, domain: str, service: str, service_data: dict[str, Any]
    ) -> str:
        """Call a custom Home Assistant service."""
        result = await self._make_request(
            "POST",
            f"/api/services/{domain}/{service}",
            json=service_data,
        )

        if "error" in result:
            return f"Error: Failed to call service {domain}.{service} - {result['error']}"

        return f"✅ Successfully called service {domain}.{service}\nData: {service_data}"
