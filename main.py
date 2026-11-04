"""AstrBot entry point and authenticated bridge handlers.

 Copyright (c) 2026 Skylight Software Organization.
 Created by EternityBoundary
 All rights reserved.
 SPDX-License-Identifier: GPL-3.0-only
 
 File: main.py
 Project: AetherNexus for AstrBot
"""

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request, stream_response
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .client import ApiError, PlatformClient
from .service import WorkspaceService, usage_csv
from .storage import LocalStore

PLUGIN_NAME = "astrbot_plugin_aethernexus_for_astrbot"
MAX_BODY = 38 * 1024 * 1024


class AetherNexusPlugin(Star):
    """Serve AetherNexus through AstrBot's authenticated plugin view bridge."""

    def __init__(self, context: Context, config: AstrBotConfig):
        """Register namespaced routes without starting another web server.

        Args:
            context: AstrBot runtime context.
            config: Configuration containing environment variable names.
        """
        super().__init__(context)
        self.config = config
        self.secrets = {}
        self.jobs = {}
        self.uploads = {}
        self.client = PlatformClient(self.credential)
        self.service = None
        for path, handler, methods, description in (
            ("status", self.status, ["GET"], "Workspace status"),
            ("action", self.action, ["POST"], "Workspace operations"),
            ("credentials", self.credentials, ["POST"], "Set session credentials"),
            ("uploads", self.prepare_upload, ["POST"], "Prepare selected upload"),
            ("upload/<kind>", self.upload, ["POST"], "Upload selected content"),
            ("download", self.download, ["GET"], "Download file or usage CSV"),
            ("runs", self.start_run, ["POST"], "Start a Responses stream"),
            ("runs/<run_id>/events", self.run_events, ["GET"], "Responses events"),
            ("runs/<run_id>/cancel", self.cancel_run, ["POST"], "Stop waiting"),
        ):
            context.register_web_api(
                f"/{PLUGIN_NAME}/{path}", handler, methods, description
            )

    async def initialize(self):
        """Open non-secret storage in AstrBot's plugin data directory."""
        directory = Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME
        store = await asyncio.to_thread(LocalStore, directory)
        self.service = WorkspaceService(self.client, store)
        logger.info("AetherNexus workspace initialized.")

    def credential(self, kind: str) -> str:
        """Resolve a server-side key only for an explicit API operation.

        Args:
            kind: Independent api or admin slot.

        Returns:
            Session key or the configured server environment value.
        """
        if kind in self.secrets:
            return self.secrets[kind]
        default = "OPENAI_ADMIN_KEY" if kind == "admin" else "OPENAI_API_KEY"
        return os.environ.get(self.config.get(f"{kind}_key_env", default), "")

    async def status(self):
        """Return preferences and credential presence without key values.

        Returns:
            Workspace status for an authenticated Dashboard user.
        """
        settings = await asyncio.to_thread(self.service.store.settings)
        slots = {}
        for kind, default in (("api", "OPENAI_API_KEY"), ("admin", "OPENAI_ADMIN_KEY")):
            env = self.config.get(f"{kind}_key_env", default)
            source = (
                "session"
                if self.secrets.get(kind)
                else "environment"
                if kind not in self.secrets and env in os.environ
                else "missing"
            )
            slots[kind] = {"source": source, "env": env}
        return json_response(
            {
                "name": "AetherNexus",
                "settings": settings,
                "credentials": slots,
                "version": "1.0.0",
            }
        )

    async def action(self):
        """Dispatch one validated local or remote workspace operation.

        Returns:
            Operation result or a sanitized public error.
        """
        try:
            raw = await request.body()
            if len(raw) > MAX_BODY:
                raise ValueError("Request exceeds 38 MiB.")
            result = await self.service.action(json.loads(raw))
            return json_response(result, headers={"Cache-Control": "no-store"})
        except (ValueError, ApiError) as error:
            return error_response(
                str(error), status_code=400 if isinstance(error, ValueError) else 502
            )
        except Exception as error:
            logger.warning(f"AetherNexus operation failed ({type(error).__name__}).")
            return error_response(
                "Operation failed. No write is automatically retried.", status_code=500
            )

    async def credentials(self):
        """Update an in-memory key without writing it to document storage.

        Returns:
            An acknowledgement without a key value.
        """
        payload = await request.json(default={})
        if not isinstance(payload, dict) or payload.get("kind") not in ("api", "admin"):
            return error_response("Invalid credential slot.")
        kind, mode = payload["kind"], payload.get("mode", "set")
        if mode == "environment":
            self.secrets.pop(kind, None)
        elif mode == "clear":
            self.secrets[kind] = ""
        elif mode == "set":
            secret = payload.get("value")
            if not isinstance(secret, str) or not re.fullmatch(
                r"[!-~]{1,4096}", secret
            ):
                return error_response(
                    "Key must be 1–4096 printable ASCII characters without spaces."
                )
            self.secrets[kind] = secret
        else:
            return error_response("Invalid credential operation.")
        return json_response({"saved": True}, headers={"Cache-Control": "no-store"})

    async def prepare_upload(self):
        """Bind upload parameters to a short-lived ticket for the bridge file API.

        Returns:
            An opaque single-use upload ID owned by the Dashboard user.
        """
        payload = await request.json(default={})
        if (
            not isinstance(payload, dict)
            or payload.get("kind") not in ("files", "transcription", "translation")
            or not isinstance(payload.get("params", {}), dict)
        ):
            return error_response("Invalid upload options.")
        now = time.monotonic()
        self.uploads = {
            key: val for key, val in self.uploads.items() if now - val["created"] < 120
        }
        if len(self.uploads) >= 16:
            return error_response("Too many pending uploads.")
        upload_id = uuid.uuid4().hex
        self.uploads[upload_id] = {
            "owner": request.username,
            "created": now,
            "kind": payload["kind"],
            "params": payload.get("params", {}),
        }
        return json_response({"upload_id": upload_id})

    async def upload(self, kind: str):
        """Forward one explicitly selected file using the documented upload field.

        Args:
            kind: Single-use upload ticket ID.

        Returns:
            Upload result or a safe error.
        """
        try:
            options = self.uploads.get(kind)
            if (
                not options
                or options["owner"] != request.username
                or time.monotonic() - options["created"] >= 120
            ):
                raise ValueError("Upload ticket is missing or expired.")
            self.uploads.pop(kind)
            upload = (await request.files()).get("file")
            if upload is None:
                raise ValueError("Select a file first.")
            content = await upload.read(25 * 1024 * 1024 + 1)
            result = await self.service.upload(
                options["kind"],
                content,
                upload.filename or "upload.bin",
                upload.content_type or "application/octet-stream",
                options["params"],
            )
            return json_response(result)
        except (ValueError, ApiError) as error:
            return error_response(str(error))
        except Exception as error:
            logger.warning(f"AetherNexus upload failed ({type(error).__name__}).")
            return error_response(
                "Upload failed. The server may have received the file.", status_code=502
            )

    async def download(self):
        """Return bounded content through AstrBot's download bridge.

        Returns:
            Remote file or CSV, without arbitrary local paths or remote URLs.
        """
        try:
            if request.query.get("kind") == "usage":
                report = await self.service.usage(
                    {
                        key: request.query.get(key, "")
                        for key in ("start", "end", "project", "category", "group")
                    }
                )
                content, mime, filename = (
                    usage_csv(report),
                    "text/csv; charset=utf-8",
                    "aethernexus-usage.csv",
                )
            else:
                file_id = request.query.get("id", "")
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", file_id):
                    raise ValueError("Invalid file ID.")
                content, mime = await self.client.request(
                    "GET",
                    f"/files/{file_id}/content",
                    project=request.query.get("project", ""),
                    raw=True,
                )
                filename = file_id + ".bin"
            return stream_response(
                iter([content]),
                content_type=mime,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        except (ValueError, ApiError) as error:
            return error_response(str(error))

    async def start_run(self):
        """Create an owned job for the bridge's GET-only SSE subscription.

        Returns:
            An opaque run ID after explicit user submission.
        """
        try:
            raw = await request.body()
            if len(raw) > MAX_BODY:
                raise ValueError("Request exceeds 38 MiB.")
            payload = json.loads(raw)
            if not isinstance(payload, dict) or not isinstance(
                payload.get("body"), dict
            ):
                raise ValueError("Expected a Responses body.")
            body = payload["body"]
            if (
                not isinstance(body.get("model"), str)
                or not body["model"].strip()
                or "input" not in body
            ):
                raise ValueError("A model and input are required.")
            now = time.monotonic()
            for old_id, job in list(self.jobs.items()):
                if now - job["created"] > 600:
                    job["task"].cancel()
                    self.jobs.pop(old_id)
            if len(self.jobs) >= 8:
                raise ValueError(
                    "At most 8 pending streams are allowed. Close or cancel an existing stream."
                )
            run_id, queue = uuid.uuid4().hex, asyncio.Queue(maxsize=128)
            self.jobs[run_id] = {
                "created": now,
                "owner": request.username,
                "queue": queue,
                "subscribed": False,
                "task": asyncio.create_task(
                    self._run_stream(
                        queue, {"store": False, **body}, payload.get("project", "")
                    )
                ),
            }
            return json_response({"run_id": run_id})
        except (ValueError, ApiError) as error:
            return error_response(str(error))

    async def _run_stream(self, queue: asyncio.Queue, body: dict, project: str):
        """Produce bounded queued events for a browser-owned stream.

        Args:
            queue: Event queue, preserving output before subscription.
            body: Responses request body.
            project: Optional general-key project scope.
        """
        started = time.monotonic()
        try:
            async for event in self.client.stream_chat(body, project):
                if time.monotonic() - started > 600:
                    raise ApiError("Stream timed out after ten minutes.")
                await asyncio.wait_for(queue.put(event), timeout=120)
        except asyncio.CancelledError:
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait({"type": "cancelled"})
            raise
        except Exception as error:
            while queue.full():
                queue.get_nowait()
            message = (
                str(error)
                if isinstance(error, ApiError)
                else "Stream failed or timed out."
            )
            queue.put_nowait({"type": "error", "message": message})

    async def run_events(self, run_id: str):
        """Subscribe once to an owned job and cancel it on disconnect.

        Args:
            run_id: Opaque ID returned by start_run.

        Returns:
            Authenticated SSE stream with heartbeat comments.
        """
        job = self.jobs.get(run_id)
        if not job or job["owner"] != request.username:
            return error_response("Run not found.", status_code=404)
        if job["subscribed"]:
            return error_response(
                "This stream already has a subscriber.", status_code=409
            )
        job["subscribed"] = True

        async def events():
            """Yield events while owning the generation task lifetime."""
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(job["queue"].get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event["type"] in ("completed", "error", "cancelled"):
                        break
            finally:
                job["task"].cancel()
                await asyncio.gather(job["task"], return_exceptions=True)
                self.jobs.pop(run_id, None)

        return stream_response(
            events(), headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
        )

    async def cancel_run(self, run_id: str):
        """Stop local waiting without claiming remote processing was undone.

        Args:
            run_id: Owned generation run ID.

        Returns:
            Local cancellation acknowledgement.
        """
        job = self.jobs.get(run_id)
        if not job or job["owner"] != request.username:
            return error_response("Run not found.", status_code=404)
        job["task"].cancel()
        await asyncio.gather(job["task"], return_exceptions=True)
        if not job["subscribed"]:
            self.jobs.pop(run_id, None)
        return json_response(
            {
                "cancelled": True,
                "message": "Stopped waiting. The remote request may still incur usage.",
            }
        )

    @filter.command("aethernexus")
    async def workspace_command(self, event: AstrMessageEvent):
        """Explain how to open the authenticated workspace.

        Args:
            event: AstrBot message event.

        Yields:
            Dashboard navigation instructions.
        """
        yield event.plain_result(
            "請登入 AstrBot WebUI → 外掛 → AetherNexus → 可視化視圖 → AetherNexus 工作區。"
        )

    async def terminate(self):
        """Cancel streams, close transports and drop session credentials."""
        tasks = [job["task"] for job in self.jobs.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.jobs.clear()
        self.uploads.clear()
        self.secrets.clear()
        await self.client.close()
        self.context.registered_web_apis[:] = [
            api
            for api in self.context.registered_web_apis
            if getattr(api[1], "__self__", None) is not self
        ]
