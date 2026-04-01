"""Built-in slash command handlers."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from loguru import logger

from nanobot import __version__
from nanobot.bus.events import OutboundMessage
from nanobot.command.router import CommandContext, CommandRouter
from nanobot.utils.helpers import build_status_content


async def cmd_stop(ctx: CommandContext) -> OutboundMessage:
    """Cancel all active tasks and subagents for the session."""
    loop = ctx.loop
    msg = ctx.msg
    tasks = loop._active_tasks.pop(msg.session_key, [])
    cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
    for t in tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    sub_cancelled = await loop.subagents.cancel_by_session(msg.session_key)
    total = cancelled + sub_cancelled
    content = f"Stopped {total} task(s)." if total else "No active task to stop."
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content=content, metadata={"_is_final": True}
    )


async def cmd_restart(ctx: CommandContext) -> OutboundMessage:
    """Restart the process in-place via os.execv."""
    msg = ctx.msg

    async def _do_restart():
        await asyncio.sleep(1)
        os.execv(sys.executable, [sys.executable, "-m", "nanobot"] + sys.argv[1:])

    asyncio.create_task(_do_restart())
    return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="Restarting...")


async def cmd_status(ctx: CommandContext) -> OutboundMessage:
    """Build an outbound status message for a session."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    ctx_est = 0
    try:
        ctx_est, _ = loop.memory_consolidator.estimate_session_prompt_tokens(session)
    except Exception:
        pass
    if ctx_est <= 0:
        ctx_est = loop._last_usage.get("prompt_tokens", 0)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_status_content(
            version=__version__,
            model=loop.model,
            start_time=loop._start_time,
            last_usage=loop._last_usage,
            context_window_tokens=loop.context_window_tokens,
            session_msg_count=len(session.get_history(max_messages=0)),
            context_tokens_estimate=ctx_est,
        ),
        metadata={"render_as": "text"},
    )


async def cmd_new(ctx: CommandContext) -> OutboundMessage:
    """Start a fresh session."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    snapshot = session.messages[session.last_consolidated :]
    session.clear()
    loop.sessions.save(session)
    loop.sessions.invalidate(session.key)
    if snapshot:
        loop._schedule_background(loop.memory_consolidator.archive_messages(snapshot))
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="New session started.",
    )


async def cmd_help(ctx: CommandContext) -> OutboundMessage:
    """Return available slash commands."""
    lines = [
        "🐈 nanobot commands:",
        "/new — Start a new conversation",
        "/stop — Stop the current task",
        "/restart — Restart the bot",
        "/status — Show bot status",
        "/help — Show available commands",
    ]
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="\n".join(lines),
        metadata={"render_as": "text"},
    )


async def cmd_clear(ctx: CommandContext) -> OutboundMessage:
    """Clear the current session."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    session.clear()
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id, content="Session cleared."
    )


async def cmd_history(ctx: CommandContext) -> OutboundMessage:
    """Show the conversation history."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    history = []

    def _add_msg(msg):
        if not msg.get("content") or not isinstance(msg.get("content"), str):
            return
        if msg["role"] == "user":
            history.append({"role": "user", "content": msg["content"]})
        if msg["role"] == "assistant" and "tool_calls" not in msg:
            history.append({"role": "assistant", "content": msg["content"]})
        return

    for message in session.messages:
        _add_msg(message)
    metadata = {"_task_ref": "history", "_hide_message": True}
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=json.dumps(history),
        metadata=metadata,
    )


async def cmd_inspect(ctx: CommandContext) -> OutboundMessage:
    """Build an outbound status message for a session."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    mode = loop.provider.get_default_mode()
    if mode == "auto":
        modes = [f"{m['model']}({m['name']})" for m in loop.provider.list_models()]
    else:
        modes = [
            f"{m['model']}({m['name']})" for m in loop.provider.list_models() if m["name"] == mode
        ]
    status = {
        "mode": loop.provider.get_default_mode(),
        "model": "\n".join(modes),
        "history": len(session.messages),
        "skills": len(loop.context.skills.list_skills()),
        "tools": len(loop.tools),
        "msg_handlers": list(loop.bus.handlers.keys()),
        "_session_state": session.status,
    }
    metadata = {"_task_ref": "status", "_hide_message": True}
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=json.dumps(status),
        metadata=metadata,
    )


async def cmd_register_extern_tools(ctx: CommandContext) -> OutboundMessage:
    """Register external tools."""
    metadata = ctx.msg.metadata or {}
    required_fields = {"type", "tools"}
    assert all(field in metadata for field in required_fields), "Missing required fields " + str(
        required_fields
    )
    tool_type, kwargs = metadata["type"], metadata.get("kwargs", {})
    # Get the ExternTool subclass by type
    from nanobot.agent.tools.extern import ExternTool

    tool_class, tools = ExternTool.get_registered_type(tool_type), []
    if tool_class:
        # Register each tool spec as an instance of the ExternTool subclass
        for spec in metadata["tools"]:
            try:
                spec.update(kwargs)
                tool_instance = tool_class(**spec)
                ctx.loop.tools.register(tool_instance)
                logger.info(f"Registered extern tool({tool_type}): {tool_instance.name}")
                tools.append(tool_instance.name)
            except Exception as e:
                logger.warning(f"Failed to register extern tool {spec.get('name', 'unknown')}: {e}")
                continue
    else:
        logger.warning(f"ExternTool type '{tool_type}' not registered")
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="Registered extern tools: " + ",".join(tools),
        metadata={"_task_ref": "register_extern_tools"},
    )


async def cmd_update_features(ctx: CommandContext) -> OutboundMessage:
    """Update features."""

    if ctx.msg.metadata.get("reset", False):
        ctx.loop.features = {}
    else:
        ctx.loop.features.update(ctx.msg.metadata.get("features", {}))
        content = "Update features: " + ",".join([f"{k}={v}" for k, v in ctx.loop.features.items()])
        logger.info(content)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="",
        metadata={"_task_ref": "update_features", "_hide_message": True},
    )


def register_builtin_commands(router: CommandRouter) -> None:
    """Register the default set of slash commands."""
    router.priority("/stop", cmd_stop)
    router.priority("/restart", cmd_restart)
    router.priority("/status", cmd_status)
    router.exact("/new", cmd_new)
    router.exact("/status", cmd_status)
    router.exact("/help", cmd_help)
    router.exact("/clear", cmd_clear)
    router.exact("/history", cmd_history)
    router.exact("/inspect", cmd_inspect)
    router.exact("/register_extern_tools", cmd_register_extern_tools)
    router.exact("/update_features", cmd_update_features)
