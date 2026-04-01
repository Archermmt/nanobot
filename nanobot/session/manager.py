"""Session management for conversation history."""

import asyncio
import json
import random
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.config.paths import get_legacy_sessions_dir
from nanobot.config.schema import SessionConfig
from nanobot.utils.helpers import ensure_dir, safe_filename
from nanobot.utils.message import RetType


class SessionState(Enum):
    """Chat status enum."""

    READY = "ready"
    STANDBY = "standby"


@dataclass
class Session:
    """
    A conversation session.

    Stores messages in JSONL format for easy reading and persistence.

    Important: Messages are append-only for LLM cache efficiency.
    The consolidation process writes summaries to MEMORY.md/HISTORY.md
    but does NOT modify the messages list or get_history() output.
    """

    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_consolidated: int = 0  # Number of messages already consolidated to files
    _last_activity_time: float = 0.0  # Last activity timestamp in milliseconds
    _status: SessionState = field(default=SessionState.STANDBY)  # Current chat status
    _timeout_task: Any = None  # Background timeout check task
    _stop_timeout_check: bool = False  # Flag to stop timeout checking

    def setup(self, config: SessionConfig, send_callback=None) -> None:
        self.wakeup_words = config.wakeup_words
        self.wakeup_response = config.wakeup_response
        if self.wakeup_words:
            self.goodbye_words = config.goodbye_words
            self.goodbye_response = config.goodbye_response
        else:
            self.goodbye_words, self.goodbye_response = [], []
        self._status = SessionState.STANDBY if self.wakeup_words else SessionState.READY
        self._default_channel = None
        self._default_chat_id = None
        self._default_message_id = None
        self._send_callback = send_callback
        self._last_meta = None
        # Start background timeout checking task
        if self.wakeup_words:
            self._stop_timeout_check = False
            self._timeout_task = asyncio.create_task(
                self._check_timeout_loop(
                    timeout_seconds=config.timeout_seconds, check_interval=config.check_interval
                )
            )
        else:
            self._stop_timeout_check, self._timeout_task = True, None

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {"role": role, "content": content, "timestamp": datetime.now().isoformat(), **kwargs}
        self.messages.append(msg)
        self.updated_at = datetime.now()

    @staticmethod
    def _find_legal_start(messages: list[dict[str, Any]]) -> int:
        """Find first index where every tool result has a matching assistant tool_call."""
        declared: set[str] = set()
        start = 0
        for i, msg in enumerate(messages):
            role = msg.get("role")
            if role == "assistant":
                for tc in msg.get("tool_calls") or []:
                    if isinstance(tc, dict) and tc.get("id"):
                        declared.add(str(tc["id"]))
            elif role == "tool":
                tid = msg.get("tool_call_id")
                if tid and str(tid) not in declared:
                    start = i + 1
                    declared.clear()
                    for prev in messages[start : i + 1]:
                        if prev.get("role") == "assistant":
                            for tc in prev.get("tool_calls") or []:
                                if isinstance(tc, dict) and tc.get("id"):
                                    declared.add(str(tc["id"]))
        return start

    def get_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        """Return unconsolidated messages for LLM input, aligned to a legal tool-call boundary."""
        unconsolidated = self.messages[self.last_consolidated :]
        sliced = unconsolidated[-max_messages:]

        # Drop leading non-user messages to avoid starting mid-turn when possible.
        for i, message in enumerate(sliced):
            if message.get("role") == "user":
                sliced = sliced[i:]
                break

        # Some providers reject orphan tool results if the matching assistant
        # tool_calls message fell outside the fixed-size history window.
        start = self._find_legal_start(sliced)
        if start:
            sliced = sliced[start:]

        out: list[dict[str, Any]] = []
        for message in sliced:
            entry: dict[str, Any] = {"role": message["role"], "content": message.get("content", "")}
            for key in ("tool_calls", "tool_call_id", "name"):
                if key in message:
                    entry[key] = message[key]
            out.append(entry)
        return out

    def clear(self) -> None:
        """Clear all messages and reset session to initial state."""
        self.messages = []
        self.last_consolidated = 0
        self.updated_at = datetime.now()

    def retain_recent_legal_suffix(self, max_messages: int) -> None:
        """Keep a legal recent suffix, mirroring get_history boundary rules."""
        if max_messages <= 0:
            self.clear()
            return
        if len(self.messages) <= max_messages:
            return

        start_idx = max(0, len(self.messages) - max_messages)

        # If the cutoff lands mid-turn, extend backward to the nearest user turn.
        while start_idx > 0 and self.messages[start_idx].get("role") != "user":
            start_idx -= 1

        retained = self.messages[start_idx:]

        # Mirror get_history(): avoid persisting orphan tool results at the front.
        start = self._find_legal_start(retained)
        if start:
            retained = retained[start:]

        dropped = len(self.messages) - len(retained)
        self.messages = retained
        self.last_consolidated = max(0, self.last_consolidated - dropped)
        self.updated_at = datetime.now()

    def _check_status(self, msg: InboundMessage) -> dict[str, Any]:
        """Check the chat status based on the message content."""
        response, metadata = "", msg.metadata
        if self._status == SessionState.READY and msg.content in self.goodbye_words:
            self._status = SessionState.STANDBY
            response = random.choice(self.goodbye_response)
            metadata["_session_state"] = "ready"
            if "need_tts" in metadata:
                metadata.pop("need_tts")
        elif self._status == SessionState.STANDBY and msg.content in self.wakeup_words:
            self._status = SessionState.READY
            response = random.choice(self.wakeup_response)
            metadata["_session_state"] = "standby"
            if "_as_input" in metadata:
                metadata.pop("_as_input")

        # Update last activity time when in LISTEN state and received a message
        if self._status == SessionState.READY:
            self._last_meta = msg.metadata
            self._last_activity_time = time.time() * 1000

        return {"status": self._status, "response": response, "metadata": metadata}

    async def check_reply(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Check message and return reply if needed.

        Args:
            msg: The inbound message to check.

        Returns:
            OutboundMessage if a reply is needed, None otherwise.
        """

        self._default_channel = msg.channel
        self._default_chat_id = msg.chat_id

        # Handle non-normal return types
        if msg.metadata.get("ret_type", RetType.NORMAL) != RetType.NORMAL:
            if msg.metadata.get("ret_type", RetType.NORMAL) == RetType.PASSBY:
                msg.metadata.setdefault("_hide_message", True)
                msg.metadata.setdefault("_is_final", True)
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=msg.content,
                metadata=msg.metadata,
            )

        # Check session status
        s_info = self._check_status(msg)
        if s_info.get("response"):
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=s_info["response"],
                metadata=s_info["metadata"],
            )

        # Handle muted session
        if s_info["status"] == SessionState.STANDBY:
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="Session standby, please wake up.",
                metadata=s_info["metadata"],
            )

        return None

    async def _check_timeout_loop(
        self, timeout_seconds: int = 300, check_interval: float = 10.0
    ) -> None:
        """
        Background task to continuously check for connection timeout.

        Args:
            timeout_seconds: Timeout threshold in seconds (default: 5 minutes)
            check_interval: How often to check for timeout in seconds (default: 10 seconds)
        """
        try:
            while not self._stop_timeout_check:
                await asyncio.sleep(check_interval)

                # Only check timeout if _last_activity_time has been initialized
                if self._last_activity_time > 0.0:
                    current_time = time.time() * 1000
                    if current_time - self._last_activity_time > timeout_seconds * 1000:
                        logger.info(f"Session {self.key} timed out, setting status to MUTE")
                        self._status = SessionState.STANDBY
                        # Reset _last_activity_time to avoid repeated triggers
                        self._last_activity_time = 0.0
                        if self.goodbye_response:
                            content = random.choice(self.goodbye_response)
                        else:
                            content = "GoodBye"
                        msg = OutboundMessage(
                            channel=self._default_channel,
                            chat_id=self._default_chat_id,
                            content=content,
                            metadata={**self._last_meta, "_connect_state": "standby"},
                        )
                        await self._send_callback(msg)
        except asyncio.CancelledError:
            logger.debug(f"Timeout check loop cancelled for session {self.key}")
        except Exception as e:
            logger.error(f"Error in timeout check loop for session {self.key}: {e}")

    async def stop_timeout_check(self) -> None:
        """Stop the background timeout checking task."""
        self._stop_timeout_check = True
        if self._timeout_task:
            try:
                self._timeout_task.cancel()
                await self._timeout_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error stopping timeout check: {e}")
            finally:
                self._timeout_task = None


class SessionManager:
    """
    Manages conversation sessions.

    Sessions are stored as JSONL files in the sessions directory.
    """

    def __init__(self, workspace: Path, config: SessionConfig, send_callback=None):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(self.workspace / "sessions")
        self.legacy_sessions_dir = get_legacy_sessions_dir()
        self._cache: dict[str, Session] = {}
        self._config = config
        self._send_callback = send_callback

    def _get_session_path(self, key: str) -> Path:
        """Get the file path for a session."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"

    def _get_legacy_session_path(self, key: str) -> Path:
        """Legacy global session path (~/.nanobot/sessions/)."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.legacy_sessions_dir / f"{safe_key}.jsonl"

    def get_or_create(self, key: str) -> Session:
        """
        Get an existing session or create a new one.

        Args:
            key: Session key (usually channel:chat_id).

        Returns:
            The session.
        """
        if key in self._cache:
            return self._cache[key]

        session = self._load(key)
        if session is None:
            session = Session(key=key)
            session.setup(self._config, send_callback=self._send_callback)

        self._cache[key] = session
        return session

    def _load(self, key: str) -> Session | None:
        """Load a session from disk."""
        path = self._get_session_path(key)
        if not path.exists():
            legacy_path = self._get_legacy_session_path(key)
            if legacy_path.exists():
                try:
                    shutil.move(str(legacy_path), str(path))
                    logger.info("Migrated session {} from legacy path", key)
                except Exception:
                    logger.exception("Failed to migrate session {}", key)

        if not path.exists():
            return None

        try:
            messages = []
            metadata = {}
            created_at = None
            last_consolidated = 0

            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    data = json.loads(line)

                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = (
                            datetime.fromisoformat(data["created_at"])
                            if data.get("created_at")
                            else None
                        )
                        last_consolidated = data.get("last_consolidated", 0)
                    else:
                        messages.append(data)

            session = Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata,
                last_consolidated=last_consolidated,
            )
            session.setup(self._config, send_callback=self._send_callback)
            return session
        except Exception as e:
            logger.warning("Failed to load session {}: {}", key, e)
            return None

    def save(self, session: Session) -> None:
        """Save a session to disk."""
        path = self._get_session_path(session.key)

        with open(path, "w", encoding="utf-8") as f:
            metadata_line = {
                "_type": "metadata",
                "key": session.key,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata,
                "last_consolidated": session.last_consolidated,
            }
            f.write(json.dumps(metadata_line, ensure_ascii=False) + "\n")
            for msg in session.messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

        self._cache[session.key] = session

    def invalidate(self, key: str) -> None:
        """Remove a session from the in-memory cache."""
        self._cache.pop(key, None)

    def list_sessions(self) -> list[dict[str, Any]]:
        """
        List all sessions.

        Returns:
            List of session info dicts.
        """
        sessions = []

        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                # Read just the metadata line
                with open(path, encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            key = data.get("key") or path.stem.replace("_", ":", 1)
                            sessions.append(
                                {
                                    "key": key,
                                    "created_at": data.get("created_at"),
                                    "updated_at": data.get("updated_at"),
                                    "path": str(path),
                                }
                            )
            except Exception:
                continue

        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
