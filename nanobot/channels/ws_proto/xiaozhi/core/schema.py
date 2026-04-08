from pydantic import Field

from nanobot.config.schema import Base


class XiaoZhiProtoConfig(Base):
    """XiaoZhi ESP32 WebSocket channel configuration."""

    enabled: bool = False
    http_port: int = 8003  # Http server bind port
    auth_enabled: bool = False  # Enable device authentication
    auth_key: str = ""  # Authentication key/token for device verification
    allowed_devices: list[str] = Field(
        default_factory=list
    )  # Device whitelist (empty = all devices need auth)
    expire_seconds: int | None = None  # Token expiration time in seconds
    firmware_cache_ttl: int = 30  # Firmware cache TTL in seconds
    timezone_offset: int = 8  # Timezone offset in hours
    mqtt_gateway: str | None = None  # MQTT gateway endpoint
    mqtt_signature_key: str = ""  # MQTT signature key for password generation
    read_config_from_api: bool = False
    depends_folder: str = "~/.nanobot/depends/xiaozhi"
