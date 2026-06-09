from pathlib import Path

import pytest

from nanobot.agent.tools.context import RequestContext
from nanobot.agent.tools.media import MediaTool, MediaToolConfig
from nanobot.bus.events import OutboundMessage


def _tool(tmp_path: Path, sent: list[OutboundMessage] | None = None) -> MediaTool:
    async def send_callback(msg: OutboundMessage) -> None:
        if sent is not None:
            sent.append(msg)

    return MediaTool(
        workspace=tmp_path,
        config=MediaToolConfig(enabled=True),
        send_callback=send_callback,
    )


@pytest.mark.asyncio
async def test_image_display_sends_media_via_callback(tmp_path: Path) -> None:
    image_file = tmp_path / "plot.png"
    image_file.write_bytes(b"png")
    sent: list[OutboundMessage] = []
    tool = _tool(tmp_path, sent)
    tool.set_context(RequestContext(channel="websocket", chat_id="chat-1", message_id="msg-1"))

    result = await tool.execute(
        media_type="image",
        mode="display",
        media_path=str(image_file),
    )

    assert result == "Sent image to the user."
    assert len(sent) == 1
    assert sent[0].channel == "websocket"
    assert sent[0].chat_id == "chat-1"
    assert sent[0].content == ""
    assert sent[0].media == [str(image_file)]
    assert sent[0].metadata["message_id"] == "msg-1"
    assert sent[0].metadata["_record_channel_delivery"] is True


@pytest.mark.asyncio
async def test_html_display_returns_file_content(tmp_path: Path) -> None:
    html_file = tmp_path / "index.html"
    html_file.write_text("<h1>Hello</h1>", encoding="utf-8")
    sent: list[OutboundMessage] = []
    tool = _tool(tmp_path, sent)
    tool.set_context(RequestContext(channel="websocket", chat_id="chat-1"))

    result = await tool.execute(
        media_type="html",
        mode="display",
        media_path=str(html_file),
    )

    assert result == "<h1>Hello</h1>"
    assert sent == []
