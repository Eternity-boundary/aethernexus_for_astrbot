"""Async official-API transport; tests inject HTTP/WebSocket substitutes.

 Copyright (c) 2026 Skylight Software Organization.
 Created by EternityBoundary
 All rights reserved.
 SPDX-License-Identifier: GPL-3.0-only

 File: client.py
 Project: AetherNexus for AstrBot
"""

import asyncio
import base64
import io
import json
import re
import wave
from collections.abc import Callable

import httpx
from websockets.asyncio.client import connect

MAX_BYTES = 40 * 1024 * 1024


class ApiError(Exception):
    """A public transport error that never includes a private response body."""


class PlatformClient:
    """Keep general and administrator credentials on the server."""

    def __init__(
        self, credential: Callable[[str], str], transport=None, websocket=None
    ):
        """Initialize a lazy transport without reading credentials or making requests.

        Args:
            credential: Lazy lookup for independent api/admin credentials.
            transport: Optional httpx transport for offline contract tests.
            websocket: Optional async context manager factory for offline Realtime tests.
        """
        self.credential = credential
        self.websocket = websocket or connect
        self.http = httpx.AsyncClient(
            base_url="https://api.openai.com/v1/",
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(180, connect=15),
        )

    def headers(
        self, admin: bool = False, project: str = "", traces: bool = False
    ) -> dict:
        """Build headers only when an explicit operation is executed.

        Args:
            admin: Use the separate administrator slot.
            project: Optional general-key project scope.
            traces: Enable the public agent tracing API header.

        Returns:
            HTTP headers kept inside the backend.

        Raises:
            ApiError: Required credentials are missing or malformed.
        """
        secret = self.credential("admin" if admin else "api")
        if not secret:
            raise ApiError(
                "缺少 Admin Key。請前往設定。"
                if admin
                else "缺少一般 API Key。請前往設定。"
            )
        if not isinstance(secret, str) or not re.fullmatch(r"[!-~]{1,4096}", secret):
            raise ApiError("Invalid credential format.")
        headers = {"Authorization": f"Bearer {secret}", "Cookie": ""}
        if project:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", project):
                raise ValueError("Invalid project ID.")
            headers["OpenAI-Project"] = project
        if traces:
            headers["OpenAI-Beta"] = "agents=v1"
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        body=None,
        params=None,
        admin=False,
        project="",
        files=None,
        raw=False,
        traces=False,
    ):
        """Send a single bounded request without retries or redirects.

        Args:
            method: HTTP method chosen by the operation registry.
            path: Validated API resource path.
            body: JSON body, or multipart fields when files are present.
            params: Query parameters, preserving repeated array keys.
            admin: Whether this is an organization operation.
            project: Optional generation project scope.
            files: Optional multipart file tuples.
            raw: Return bounded bytes and content type for downloads.
            traces: Add the agent tracing version header.

        Returns:
            Parsed JSON or a bytes/content-type pair.

        Raises:
            ApiError: The transport, HTTP status, or response contract fails.
        """
        if not re.fullmatch(r"/[A-Za-z0-9_/-]+", path) or "//" in path:
            raise ValueError("Invalid API resource path.")
        headers = self.headers(admin, project, traces)
        kwargs = {"data": body, "files": files} if files is not None else {"json": body}
        try:
            async with self.http.stream(
                method, path.lstrip("/"), params=params, headers=headers, **kwargs
            ) as response:
                if not 200 <= response.status_code < 300:
                    raise ApiError(
                        f"OpenAI HTTP {response.status_code}. 請檢查權限、參數與配額；寫入不會自動重試。"
                    )
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ApiError("Response exceeds the 40 MiB transfer limit.")
                    chunks.append(chunk)
                content = b"".join(chunks)
                if raw:
                    return content, response.headers.get(
                        "content-type", "application/octet-stream"
                    )
                result = json.loads(content) if content else {}
                if not isinstance(result, dict):
                    raise ApiError("Unexpected API response shape.")
                return result
        except (httpx.HTTPError, OSError, json.JSONDecodeError):
            raise ApiError(
                "API connection or response failed. 寫入結果可能未知，請重新整理核對。"
            ) from None

    async def stream_chat(self, body: dict, project: str = ""):
        """Parse Responses SSE across chunk boundaries and require a terminal event.

        Args:
            body: Responses request with a model and input.
            project: Optional project scope.

        Yields:
            Normalized delta and completed events.

        Raises:
            ApiError: The stream fails or ends without a completed response.
        """
        headers = self.headers(project=project)
        completed, size, data = False, 0, []
        try:
            async with self.http.stream(
                "POST", "responses", json={**body, "stream": True}, headers=headers
            ) as response:
                if response.status_code != 200:
                    raise ApiError(
                        f"OpenAI HTTP {response.status_code}. 請檢查金鑰與模型參數。"
                    )
                async for line in response.aiter_lines():
                    size += len(line.encode())
                    if size > MAX_BYTES:
                        raise ApiError("Stream exceeds 40 MiB.")
                    if line.startswith("data:"):
                        data.append(line[5:].lstrip())
                    elif not line and data:
                        payload = "\n".join(data)
                        data.clear()
                        if payload == "[DONE]":
                            continue
                        event = json.loads(payload)
                        kind = event.get("type")
                        if kind == "response.output_text.delta":
                            yield {"type": "delta", "text": event.get("delta", "")}
                        elif kind == "response.completed":
                            completed = True
                            yield {
                                "type": "completed",
                                "response": event.get("response", {}),
                            }
                            break
                        elif kind in (
                            "response.failed",
                            "response.incomplete",
                            "error",
                        ):
                            raise ApiError(
                                "Response failed or was incomplete. 請檢查模型與輸出限制。"
                            )
                if not completed:
                    raise ApiError(
                        "Stream ended before response.completed; partial text is not a completed response."
                    )
        except (httpx.HTTPError, OSError, json.JSONDecodeError):
            raise ApiError("Streaming connection or event parsing failed.") from None

    async def realtime(self, body: dict, project: str = "") -> dict:
        """Bound the full Realtime exchange, including the configuration handshake.

        Args:
            body: Model, instructions and one text or WAV input turn.
            project: Optional general-key project scope.

        Returns:
            A completed text/audio response.

        Raises:
            ApiError: The exchange exceeds three minutes.
        """
        try:
            return await asyncio.wait_for(self._realtime_turn(body, project), 180)
        except asyncio.TimeoutError:
            raise ApiError("Realtime timed out after three minutes.") from None

    async def _realtime_turn(self, body: dict, project: str = "") -> dict:
        """Run one GA Realtime turn and return text with PCM audio as WAV.

        Args:
            body: Model, voice, instructions, text and optional 24-kHz mono PCM WAV.
            project: Optional general-key project scope.

        Returns:
            Text, WAV base64, and response metadata.

        Raises:
            ValueError: Audio or model input is invalid.
            ApiError: Realtime fails or does not complete within three minutes.
        """
        model = body.get("model", "")
        if not isinstance(model, str) or not re.fullmatch(
            r"[A-Za-z0-9_.:-]{1,200}", model
        ):
            raise ValueError("Invalid Realtime model.")
        voice = body.get("voice", "marin")
        if voice not in (
            "alloy",
            "ash",
            "ballad",
            "coral",
            "echo",
            "sage",
            "shimmer",
            "verse",
            "marin",
            "cedar",
        ):
            raise ValueError("Invalid voice.")
        audio_input = body.get("audio")
        pcm = None
        if audio_input:
            try:
                with wave.open(
                    io.BytesIO(base64.b64decode(audio_input, validate=True)), "rb"
                ) as wav:
                    if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (
                        1,
                        2,
                        24000,
                    ) or wav.getnframes() > 24000 * 180:
                        raise ValueError(
                            "Realtime requires 24-kHz mono 16-bit WAV, at most 3 minutes."
                        )
                    pcm = wav.readframes(wav.getnframes())
            except (wave.Error, EOFError) as error:
                raise ValueError("Invalid WAV audio.") from error
        headers = self.headers(project=project)
        text, audio, size = [], [], 0
        try:
            async with self.websocket(
                f"wss://api.openai.com/v1/realtime?model={model}",
                additional_headers=headers,
                max_size=MAX_BYTES,
                proxy=None,
            ) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "type": "session.update",
                            "session": {
                                "type": "realtime",
                                "instructions": body.get("instructions", ""),
                                "output_modalities": ["audio"],
                                "audio": {
                                    "input": {
                                        "format": {
                                            "type": "audio/pcm",
                                            "rate": 24000,
                                        },
                                        "turn_detection": None,
                                    },
                                    "output": {
                                        "format": {
                                            "type": "audio/pcm",
                                            "rate": 24000,
                                        },
                                        "voice": voice,
                                    },
                                },
                            },
                        }
                    )
                )
                # Wait for acknowledgement so invalid session settings cannot be ignored.
                async for raw_event in ws:
                    event = json.loads(raw_event)
                    if event.get("type") == "error":
                        raise ApiError("Realtime session configuration was rejected.")
                    if event.get("type") == "session.updated":
                        break
                else:
                    raise ApiError(
                        "Realtime session closed before configuration completed."
                    )
                history = body.get("history", [])
                if not isinstance(history, list) or len(history) > 40:
                    raise ValueError("Realtime history is limited to 40 messages.")
                for message in history:
                    role = message.get("role")
                    if role not in ("user", "assistant") or not isinstance(
                        message.get("content"), str
                    ):
                        raise ValueError("Invalid Realtime history.")
                    await ws.send(
                        json.dumps(
                            {
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "message",
                                    "role": role,
                                    "content": [
                                        {
                                            "type": "input_text"
                                            if role == "user"
                                            else "output_text",
                                            "text": message["content"],
                                        }
                                    ],
                                },
                            }
                        )
                    )
                if pcm is not None:
                    for offset in range(0, len(pcm), 48000):
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "input_audio_buffer.append",
                                    "audio": base64.b64encode(
                                        pcm[offset : offset + 48000]
                                    ).decode(),
                                }
                            )
                        )
                    await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                else:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "input_text",
                                            "text": body.get("input", ""),
                                        }
                                    ],
                                },
                            }
                        )
                    )
                await ws.send(json.dumps({"type": "response.create"}))
                async for raw_event in ws:
                    size += len(raw_event)
                    if size > MAX_BYTES:
                        raise ApiError("Realtime response exceeds 40 MiB.")
                    event = json.loads(raw_event)
                    kind = event.get("type")
                    if kind == "response.output_audio.delta":
                        audio.append(base64.b64decode(event["delta"], validate=True))
                    elif kind in (
                        "response.output_audio_transcript.delta",
                        "response.output_text.delta",
                    ):
                        text.append(event.get("delta", ""))
                    elif kind == "error":
                        raise ApiError("Realtime request was rejected.")
                    elif kind == "response.done":
                        if event.get("response", {}).get("status") != "completed":
                            raise ApiError("Realtime response did not complete.")
                        buffer = io.BytesIO()
                        with wave.open(buffer, "wb") as wav:
                            wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                            wav.writeframes(b"".join(audio))
                        return {
                            "text": "".join(text),
                            "audio": base64.b64encode(buffer.getvalue()).decode(),
                            "mime": "audio/wav",
                            "response": event.get("response", {}),
                        }
            raise ApiError("Realtime ended without a completed response.")
        except ApiError:
            raise
        except (TimeoutError, OSError, ValueError):
            raise ApiError("Realtime connection or response failed.") from None

    async def close(self):
        """Release HTTP connection pools when AstrBot unloads the plugin."""
        await self.http.aclose()
