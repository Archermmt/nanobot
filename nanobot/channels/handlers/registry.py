"""Handler discovery and configuration registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nanobot.config.schema import Base


def discover_handler_configs() -> dict[str, type[Base]]:
    """Discover all handler modules and return their config classes.

    Iterates through BaseHandler._registry to extract name and config_cls
    from each registered handler class.

    Returns:
        Mapping of handler name to its config class.
    """
    from nanobot.channels.handlers.base_handler import BaseHandler

    configs: dict[str, type[Base]] = {}
    for handler_cls in BaseHandler._registry.values():
        name = getattr(handler_cls, "name", "")
        if not name or name in configs:
            continue
        config_cls = getattr(handler_cls, "config_cls", None)
        if name and config_cls:
            configs[name] = config_cls

    return configs
