"""Auto-discovery for protocol handlers in ws_proto directory."""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from nanobot.channels.ws_proto.base_proto import BaseProto


def discover_proto_names() -> list[str]:
    """Return all built-in protocol module names by scanning the ws_proto package."""
    import nanobot.channels.ws_proto as pkg

    # Scan subdirectories (packages) under ws_proto
    proto_names = []
    for _, name, ispkg in pkgutil.iter_modules(pkg.__path__):
        # Skip private modules and base modules
        if not name.startswith("_") and name not in ("base_proto",) and ispkg:
            proto_names.append(name)

    return proto_names


def load_proto_class(module_name: str) -> type[BaseProto] | None:
    """Import *module_name* and return the first BaseProto subclass found."""
    from nanobot.channels.ws_proto.base_proto import BaseProto

    try:
        mod = importlib.import_module(f"nanobot.channels.ws_proto.{module_name}")
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if isinstance(obj, type) and issubclass(obj, BaseProto) and obj is not BaseProto:
                return obj
    except ImportError as e:
        logger.debug("Failed to import proto module '{}': {}", module_name, e)

    return None


def discover_all_protos() -> dict[str, type[BaseProto]]:
    """Return all discovered protocol handlers.

    Scans ws_proto subdirectories and loads the first BaseProto subclass from each.
    """
    protos: dict[str, type[BaseProto]] = {}

    for modname in discover_proto_names():
        try:
            cls = load_proto_class(modname)
            if cls is not None:
                protos[modname] = cls
                logger.debug("Discovered protocol handler: {}", modname)
        except Exception as e:
            logger.warning("Failed to load protocol handler '{}': {}", modname, e)

    return protos
