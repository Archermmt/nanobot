"""Video generation provider implementations."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from nanobot.providers.registry import find_by_name

_DEFAULT_TIMEOUT_S = 120.0
_DASHSCOPE_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class GeneratedVideoResponse:
    """Video data and metadata returned by the provider."""

    video_data_url: str
    mime: str
    raw: dict[str, Any]


class VideoGenerationProvider(ABC):
    """Base class for video generation provider clients."""

    provider_name: str = ""
    missing_key_message: str = ""
    default_timeout: float = _DEFAULT_TIMEOUT_S

    def __init__(
        self,
        *,
        api_key: str | None,
        api_base: str | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_base = self._resolve_base_url(api_base)
        self.extra_headers = extra_headers or {}
        self.extra_body = extra_body or {}
        self.timeout = timeout if timeout is not None else self.default_timeout
        self._client = client

    def _resolve_base_url(self, api_base: str | None) -> str:
        if api_base:
            return api_base.rstrip("/")
        spec = find_by_name(self.provider_name)
        if spec and spec.default_api_base:
            return spec.default_api_base.rstrip("/")
        return self._default_base_url()

    def _default_base_url(self) -> str:
        return ""

    @abstractmethod
    async def generate(
        self,
        *,
        prompt: str,
        model: str,
        resolution: str = "1080P",
        ratio: str = "16:9",
        duration: int = 5,
        negative_prompt: str = "",
        ref_media: str | None = None,
        prompt_extend: bool = True,
        watermark: bool = False,
        seed: int | None = None,
    ) -> GeneratedVideoResponse: ...

    async def _http_post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, Any],
        client: httpx.AsyncClient | None = None,
    ) -> httpx.Response:
        if client is not None:
            return await client.post(url, headers=headers, json=body)
        if self._client is not None:
            return await self._client.post(url, headers=headers, json=body)
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            return await c.post(url, headers=headers, json=body)

    async def _http_get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        client: httpx.AsyncClient | None = None,
    ) -> httpx.Response:
        if client is not None:
            return await client.get(url, headers=headers)
        if self._client is not None:
            return await self._client.get(url, headers=headers)
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            return await c.get(url, headers=headers)


class DashScopeVideoGenerationClient(VideoGenerationProvider):
    """Async client for Alibaba Cloud DashScope Wanxiang Video Generation API.

    Supports:
    - Text-to-video via wan2.7-t2v (default model)
    - Audio-driven video generation with reference audio
    - Resolution selection (720P, 1080P)
    - Aspect ratio control (16:9, 9:16, 1:1, 4:3, 3:4)
    - Duration control (2-15 seconds)
    - Negative prompts
    - Watermark control
    - Prompt extension
    - Seed for reproducibility
    """

    provider_name = "dashscope"
    missing_key_message = (
        "DashScope API key is not configured. Set providers.dashscope.apiKey "
        "or DASHSCOPE_API_KEY environment variable."
    )
    default_timeout = _DASHSCOPE_TIMEOUT_S

    def _default_base_url(self) -> str:
        return "https://dashscope.aliyuncs.com/api/v1"

    def _resolve_base_url(self, api_base: str | None) -> str:
        region = os.getenv("DASHSCOPE_REGION", "beijing").lower()
        if region == "singapore":
            return "https://dashscope-intl.aliyuncs.com/api/v1"
        return self._default_base_url()

    async def generate(
        self,
        *,
        prompt: str,
        model: str,
        resolution: str = "1080P",
        ratio: str = "16:9",
        duration: int = 5,
        negative_prompt: str = "",
        ref_media: str | None = None,
        prompt_extend: bool = True,
        watermark: bool = False,
        seed: int | None = None,
    ) -> GeneratedVideoResponse:
        if not self.api_key:
            raise ValueError(self.missing_key_message)

        # Determine region and endpoints
        region = os.getenv("DASHSCOPE_REGION", "beijing").lower()
        if region == "beijing":
            create_endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
            query_base = "https://dashscope.aliyuncs.com/api/v1/tasks"
        elif region == "singapore":
            create_endpoint = "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
            query_base = "https://dashscope-intl.aliyuncs.com/api/v1/tasks"
        else:
            raise ValueError(f"Invalid region '{region}'. Must be 'beijing' or 'singapore'.")

        # Build input
        input_data: dict[str, Any] = {"prompt": prompt}
        if ref_media:
            input_data["audio_url"] = ref_media

        # Build parameters
        parameters: dict[str, Any] = {
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
            "prompt_extend": prompt_extend,
            "watermark": watermark,
        }

        if negative_prompt:
            parameters["negative_prompt"] = negative_prompt

        if seed is not None:
            parameters["seed"] = seed

        payload = {
            "model": model,
            "input": input_data,
            "parameters": parameters,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-DashScope-Async": "enable",
        }

        # Submit task
        response = await self._http_post(create_endpoint, headers=headers, body=payload)
        response.raise_for_status()
        result = response.json()

        task_id = result.get("output", {}).get("task_id")
        if not task_id:
            raise ValueError(
                f"No task_id in response. Response: {json.dumps(result, ensure_ascii=False)}"
            )

        # Poll for completion
        query_endpoint = f"{query_base}/{task_id}"
        query_headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        max_wait_time = 600  # 10 minutes
        poll_interval = 10
        elapsed_time = 0

        while elapsed_time < max_wait_time:
            await asyncio.sleep(poll_interval)
            elapsed_time += poll_interval

            query_response = await self._http_get(query_endpoint, headers=query_headers)
            query_response.raise_for_status()
            task_result = query_response.json()

            task_status = task_result.get("output", {}).get("task_status", "")

            if task_status == "SUCCEEDED":
                video_url = task_result.get("output", {}).get("video_url", "")
                if not video_url:
                    raise ValueError(
                        f"No video_url in response. Response: {json.dumps(task_result, ensure_ascii=False)}"
                    )

                # Download video content
                async with httpx.AsyncClient(timeout=120.0) as download_client:
                    video_response = await download_client.get(video_url)
                    video_response.raise_for_status()
                    video_data = video_response.content

                # Determine MIME type (DashScope returns MP4)
                mime = "video/mp4"

                # Build data URL
                encoded = base64.b64encode(video_data).decode("ascii")
                data_url = f"data:{mime};base64,{encoded}"

                return GeneratedVideoResponse(
                    video_data_url=data_url,
                    mime=mime,
                    raw=task_result,
                )

            elif task_status == "FAILED":
                error_code = task_result.get("output", {}).get("code", "unknown")
                error_message = task_result.get("output", {}).get("message", "Unknown error")
                raise ValueError(f"Video generation failed - [{error_code}] {error_message}")

            elif task_status in ["RUNNING", "PENDING"]:
                continue

            else:
                raise ValueError(f"Unknown task status: {task_status}")

        raise TimeoutError(
            f"Video generation timed out after {max_wait_time} seconds. Task ID: {task_id}"
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_VIDEO_GEN_PROVIDERS: dict[str, type[VideoGenerationProvider]] = {}


def register_video_gen_provider(cls: type[VideoGenerationProvider]) -> None:
    """Register a video provider at import time only.

    The registry is populated by module side effects so provider discovery
    stays lazy and consistent across the process.
    """
    name = cls.provider_name
    if not name:
        raise ValueError(f"{cls.__name__} must set provider_name")
    _VIDEO_GEN_PROVIDERS[name] = cls


def get_video_gen_provider(name: str) -> type[VideoGenerationProvider] | None:
    return _VIDEO_GEN_PROVIDERS.get(name)


def video_gen_provider_names() -> tuple[str, ...]:
    """Return registered video generation provider names in registry order."""
    return tuple(_VIDEO_GEN_PROVIDERS)


def video_gen_provider_configs(config: Any) -> dict[str, Any]:
    providers_cfg = config.providers
    return {
        name: pc
        for name in _VIDEO_GEN_PROVIDERS
        if (pc := getattr(providers_cfg, name, None)) is not None
    }


# Register providers
register_video_gen_provider(DashScopeVideoGenerationClient)
