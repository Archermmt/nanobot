"""WebSocket protocol implementations."""

from nanobot.channels.ws_proto.base_proto import BaseProto

from .nanoboard import NanoboardProto
from .xiaozhi import XiaoZhiProto

__all__ = ["BaseProto", "NanoboardProto", "XiaoZhiProto"]
