"""AetherNexus workspace operations independent of AstrBot request contexts.

Copyright (c) 2026 Skylight Software Organization.
Created by EternityBoundary
All rights reserved.
SPDX-License-Identifier: GPL-3.0-only

File: service.py
Project: AetherNexus for AstrBot
"""

import asyncio
import base64
import csv
import io
import json
import math
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .client import ApiError
from .operations import describe_operations, prepare_operation
from .storage import LocalStore, render_variables
from .workflow import export_python, run_workflow

USAGE_CATEGORIES = (
    "completions",
    "costs",
    "embeddings",
    "images",
    "audio_speeches",
    "audio_transcriptions",
    "moderations",
    "vector_stores",
    "code_interpreter_sessions",
    "file_search_calls",
    "web_search_calls",
)


class WorkspaceService:
    """Coordinate portable storage, management, generation and workflow services."""

    def __init__(self, client, store: LocalStore):
        """Compose a workspace with injectable dependencies.

        Args:
            client: Async platform client, using a fake transport in tests.
            store: Non-secret local document database.
        """
        self.client, self.store = client, store
        self.latest_command_dashboard = None

    async def usage(self, payload: dict) -> dict:
        """Fetch complete daily usage pages without inventing missing metrics.

        Args:
            payload: UTC dates, category, optional project and group.

        Returns:
            Daily bucket data, totals and weighted cache percentage.

        Raises:
            ValueError: The query range or grouping is invalid.
            ApiError: Pagination or response shape is invalid.
        """
        category = payload.get("category", "completions")
        if category not in USAGE_CATEGORIES:
            raise ValueError("Invalid usage category.")
        now = datetime.now(timezone.utc)
        try:
            start = datetime.strptime(payload["start"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            end = datetime.strptime(payload["end"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            ) + timedelta(days=1)
        except (KeyError, TypeError, ValueError):
            raise ValueError("Use UTC dates in YYYY-MM-DD format.") from None
        end = min(end, now)
        if not start < end or end - start > timedelta(days=366):
            raise ValueError("Usage range must be 1–366 days and not in the future.")
        project, group = payload.get("project", ""), payload.get("group", "")
        if project and (
            not isinstance(project, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", project)
        ):
            raise ValueError("Invalid project ID.")
        allowed = (
            ("", "project_id", "line_item", "api_key_id", "api_source")
            if category == "costs"
            else ("", "project_id")
            if category in ("vector_stores", "code_interpreter_sessions")
            else ("", "project_id", "model", "api_key_id", "user_id", "vector_store_id")
            if category == "file_search_calls"
            else ("", "project_id", "model", "api_key_id", "user_id")
        )
        if group not in allowed:
            raise ValueError("Unsupported grouping for this category.")
        params = [
            ("start_time", int(start.timestamp())),
            ("end_time", int(end.timestamp())),
            ("bucket_width", "1d"),
            ("limit", 31),
        ]
        if project:
            params.append(("project_ids", project))
        if group:
            params.append(("group_by", group))
        path = (
            "/organization/costs"
            if category == "costs"
            else f"/organization/usage/{category}"
        )
        buckets, cursors = [], set()
        page = ""
        for _ in range(1000):
            response = await self.client.request(
                "GET",
                path,
                params=params + ([("page", page)] if page else []),
                admin=True,
            )
            if not isinstance(response.get("data"), list):
                raise ApiError("Usage response is missing bucket data.")
            for bucket in response["data"]:
                if (
                    not isinstance(bucket, dict)
                    or not isinstance(bucket.get("results"), list)
                    or type(bucket.get("start_time")) not in (int, float)
                ):
                    raise ApiError("Invalid usage bucket.")
                buckets.append(bucket)
            if not response.get("has_more"):
                break
            page = response.get("next_page")
            if not isinstance(page, str) or not page or page in cursors:
                raise ApiError("Invalid or repeated usage pagination cursor.")
            cursors.add(page)
        else:
            raise ApiError("Usage pagination exceeds 1000 pages.")
        daily = {
            timestamp: {
                "start_time": timestamp,
                "end_time": min(timestamp + 86400, int(end.timestamp())),
                "results": [],
            }
            for timestamp in range(int(start.timestamp()), int(end.timestamp()), 86400)
        }
        for bucket in buckets:
            timestamp = bucket["start_time"]
            if not math.isfinite(timestamp) or timestamp not in daily:
                raise ApiError("Usage bucket is outside the requested UTC day range.")
            daily[timestamp]["results"].extend(bucket["results"])
        buckets = list(daily.values())
        totals, missing, rows = {}, set(), []
        for bucket in buckets:
            for record in bucket["results"]:
                if not isinstance(record, dict):
                    raise ApiError("Invalid usage result.")
                row = {
                    "start_time_unix_utc": bucket["start_time"],
                    "end_time_unix_utc": bucket.get("end_time"),
                    "category": category,
                    **record,
                }
                if category == "costs":
                    amount = record.get("amount", {})
                    if amount.get("currency", "usd").lower() != "usd":
                        raise ApiError(
                            "Non-USD cost cannot be combined into a USD total."
                        )
                    amount_value = amount.get("value")
                    if amount_value is None:
                        missing.add("amount_usd")
                    else:
                        try:
                            amount_decimal = Decimal(str(amount_value))
                            if not amount_decimal.is_finite():
                                raise ValueError
                        except Exception:
                            raise ApiError("Invalid cost amount.") from None
                        totals["amount_usd"] = (
                            totals.get("amount_usd", Decimal(0)) + amount_decimal
                        )
                        row["amount_usd"] = str(amount_decimal)
                    row.pop("amount", None)
                for key, val in record.items():
                    if key.endswith("_tokens") or key in (
                        "num_model_requests",
                        "images",
                        "characters",
                        "seconds",
                        "usage_bytes",
                        "num_sessions",
                        "num_requests",
                        "num_calls",
                    ):
                        if val is None:
                            missing.add(key)
                        elif (
                            type(val) in (int, float)
                            and math.isfinite(val)
                            and val >= 0
                        ):
                            totals[key] = totals.get(key, 0) + val
                        else:
                            raise ApiError("Invalid usage metric.")
                if (
                    record.get("input_cached_tokens") is not None
                    and record.get("input_tokens") is not None
                    and record["input_cached_tokens"] > record["input_tokens"]
                ):
                    raise ApiError("Cached input tokens exceed input tokens.")
                rows.append(row)
        # A populated bucket missing a metric is not evidence of zero activity.
        for key in list(totals):
            if any(key not in row or row[key] is None for row in rows):
                missing.add(key)
        totals = {
            key: None
            if key in missing or key == "usage_bytes"
            else float(val)
            if isinstance(val, Decimal)
            else val
            for key, val in totals.items()
        }
        for key in missing:
            totals[key] = None
        if not rows:
            metrics = {
                "costs": ["amount_usd"],
                "images": ["images", "num_model_requests"],
                "audio_speeches": ["characters", "num_model_requests"],
                "audio_transcriptions": ["seconds", "num_model_requests"],
                "vector_stores": ["usage_bytes"],
                "code_interpreter_sessions": ["num_sessions"],
                "file_search_calls": ["num_calls"],
                "web_search_calls": ["num_calls"],
            }.get(category, ["input_tokens", "output_tokens", "num_model_requests"])
            totals = {key: None if key == "usage_bytes" else 0 for key in metrics}
        denominator = totals.get("input_tokens")
        cached = totals.get("input_cached_tokens")
        ratio = (
            100 * cached / denominator if denominator and cached is not None else None
        )
        return {
            "category": category,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "project": project,
            "group": group,
            "buckets": buckets,
            "rows": rows,
            "totals": totals,
            "cache_percent": ratio,
        }

    async def dashboard(self, payload: dict) -> dict:
        """Refresh token, month-to-date cost, project and local preference data.

        Args:
            payload: Date range and optional admin project filter.

        Returns:
            Fresh reports and projects with independent error states.
        """
        now = datetime.now(timezone.utc)
        month = now.replace(day=1).strftime("%Y-%m-%d")
        reports = await asyncio.gather(
            self.usage({**payload, "category": "completions"}),
            self.usage(
                {
                    "start": month,
                    "end": now.strftime("%Y-%m-%d"),
                    "project": payload.get("project", ""),
                    "category": "costs",
                }
            ),
            return_exceptions=True,
        )
        result = {"settings": await asyncio.to_thread(self.store.settings)}
        for name, report in zip(("usage", "costs"), reports):
            result[name] = (
                {
                    "error": str(report)
                    if isinstance(report, (ValueError, ApiError))
                    else "Unable to load report."
                }
                if isinstance(report, Exception)
                else report
            )
        projects, after, cursors = [], "", set()
        try:
            for _ in range(1000):
                response = await self.client.request(
                    "GET",
                    "/organization/projects",
                    params={
                        "include_archived": "true",
                        "limit": 100,
                        **({"after": after} if after else {}),
                    },
                    admin=True,
                )
                records = response.get("data")
                if not isinstance(records, list):
                    raise ApiError("Project response is missing data.")
                for record in records:
                    if (
                        not isinstance(record, dict)
                        or not isinstance(record.get("id"), str)
                        or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", record["id"])
                        or not isinstance(record.get("name", ""), str)
                    ):
                        raise ApiError("Invalid project metadata.")
                    projects.append(
                        {key: record.get(key, "") for key in ("id", "name", "status")}
                    )
                if not response.get("has_more"):
                    result["projects"] = {"data": projects}
                    break
                after = response.get("last_id") or (
                    records[-1]["id"] if records else ""
                )
                if (
                    not isinstance(after, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", after)
                    or after in cursors
                ):
                    raise ApiError("Invalid or repeated project pagination cursor.")
                cursors.add(after)
            else:
                raise ApiError("Project pagination exceeds 1000 pages.")
        except Exception as error:
            result["projects"] = {
                "error": str(error)
                if isinstance(error, ApiError)
                else "Unable to load projects."
            }
        result["range"] = {
            "start": payload.get("start", ""),
            "end": payload.get("end", ""),
            "project": payload.get("project", ""),
        }
        result["refreshed_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def action(self, payload: dict) -> dict:
        """Execute one local action or validated remote operation.

        Args:
            payload: Action identifier with its bounded parameters.

        Returns:
            JSON-safe operation result.

        Raises:
            ValueError: Payload is invalid or confirmation is missing.
        """
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object.")
        action = payload.get("action")
        if not isinstance(action, str):
            raise ValueError("An action name is required.")
        if action == "catalog":
            return {
                "operations": describe_operations(),
                "usage_categories": USAGE_CATEGORIES,
            }
        if action == "settings.get":
            return await asyncio.to_thread(self.store.settings)
        if action == "settings.save":
            return await asyncio.to_thread(self.store.settings, payload.get("body", {}))
        if action == "dashboard.latest":
            return {"report": self.latest_command_dashboard}
        if action == "prompts.list":
            return {"revisions": await asyncio.to_thread(self.store.prompts)}
        if action == "prompts.save":
            return {
                "revisions": await asyncio.to_thread(
                    self.store.prompts, payload.get("body", {})
                )
            }
        if action == "prompts.delete":
            if not payload.get("id") or payload.get("confirm") != payload["id"]:
                raise ValueError("Confirm the prompt ID.")
            return {
                "revisions": await asyncio.to_thread(
                    self.store.prompts, remove=payload["id"]
                )
            }
        if action == "prompts.test":
            draft, variables = payload.get("body", {}), payload.get("variables", {})
            if not isinstance(draft, dict) or not draft.get("model"):
                raise ValueError("A prompt model is required.")
            options = draft.get("options", {})
            if isinstance(options, str):
                options = json.loads(options)
            body = {
                **options,
                "model": draft["model"],
                "instructions": render_variables(
                    draft.get("instructions", ""), variables
                ),
                "input": render_variables(draft.get("input", ""), variables),
                "store": False,
                "stream": False,
            }
            return await self.client.request(
                "POST", "/responses", body=body, project=payload.get("project", "")
            )
        if action == "workflow.export":
            return {"code": export_python(payload.get("body", {}))}
        if action == "workflow.run":
            return await run_workflow(
                payload.get("body", {}),
                payload.get("input", ""),
                self.client,
                payload.get("project", ""),
            )
        if action == "storyboard.validate":
            board = payload.get("body")
            if (
                not isinstance(board, dict)
                or board.get("version") != 1
                or not isinstance(board.get("shots"), list)
                or len(board["shots"]) > 100
            ):
                raise ValueError(
                    "Expected a version-1 storyboard with up to 100 shots."
                )
            for shot in board["shots"]:
                if (
                    not isinstance(shot, dict)
                    or not isinstance(shot.get("prompt"), str)
                    or not shot["prompt"].strip()
                    or type(shot.get("seconds")) not in (int, float)
                    or not 0 < shot["seconds"] <= 600
                ):
                    raise ValueError(
                        "Each shot needs a prompt and duration of 0–600 seconds."
                    )
            return board
        if action == "usage.report":
            return await self.usage(payload)
        if action == "dashboard":
            return await self.dashboard(payload)
        if action == "images.generate":
            body = dict(payload.get("body", {}))
            references = payload.get("references", [])
            if not isinstance(references, list) or len(references) > 16:
                raise ValueError("At most 16 image references are supported.")
            if (
                not isinstance(body.get("prompt"), str)
                or not body["prompt"].strip()
                or len(body["prompt"]) > 32000
                or not body.get("model")
                or type(body.get("n", 1)) is not int
                or not 1 <= body.get("n", 1) <= 10
            ):
                raise ValueError(
                    "Image generation requires a model, prompt and 1–10 outputs."
                )
            if body.get("output_format", "png") not in ("png", "jpeg", "webp") or (
                body.get("background") == "transparent"
                and body.get("output_format") == "jpeg"
            ):
                raise ValueError(
                    "Images require PNG/JPEG/WebP; transparent output cannot use JPEG."
                )
            if references:
                files, total = [], 0
                for reference in references:
                    content = base64.b64decode(reference.get("data", ""), validate=True)
                    total += len(content)
                    if (
                        not content
                        or total > 25 * 1024 * 1024
                        or reference.get("mime")
                        not in ("image/png", "image/jpeg", "image/webp")
                    ):
                        raise ValueError(
                            "Image references must be PNG/JPEG/WebP and total at most 25 MiB."
                        )
                    files.append(("image[]", ("reference", content, reference["mime"])))
                fields = {
                    key: json.dumps(val)
                    if isinstance(val, (list, dict, bool))
                    else str(val)
                    for key, val in body.items()
                }
                return await self.client.request(
                    "POST",
                    "/images/edits",
                    body=fields,
                    files=files,
                    project=payload.get("project", ""),
                )
            return await self.client.request(
                "POST",
                "/images/generations",
                body=body,
                project=payload.get("project", ""),
            )
        if action == "audio.realtime":
            return await self.client.realtime(
                payload.get("body", {}), payload.get("project", "")
            )
        if action == "audio.speech":
            if datetime.now(timezone.utc).date().isoformat() >= "2027-01-06":
                raise ValueError("Legacy Speech is retired. Use Realtime audio.")
            content, mime = await self.client.request(
                "POST",
                "/audio/speech",
                body=payload.get("body", {}),
                project=payload.get("project", ""),
                raw=True,
            )
            return {"audio": base64.b64encode(content).decode(), "mime": mime}
        spec, path, query = prepare_operation(payload)
        if action == "keys.revoke_admin":
            fresh = await self.client.request("GET", path, admin=True)
            if (
                fresh.get("id") != payload["id"]
                or fresh.get("object") != "organization.admin_api_key"
            ):
                raise ValueError(
                    "Admin key identity verification failed. Refresh the list."
                )
        result = await self.client.request(
            spec[2],
            path,
            body=payload.get("body") if spec[2] == "POST" else None,
            params=query,
            admin=spec[4],
            project="" if spec[4] else payload.get("scope", ""),
            traces=action.startswith("traces."),
        )
        if action in ("keys.issue_admin", "keys.create_account", "keys.issue_account"):
            secret = result.get("value") or result.get("api_key", {}).get("value")
            if not isinstance(secret, str) or not re.fullmatch(
                r"[!-~]{1,4096}", secret
            ):
                raise ApiError(
                    "Key issuance response did not contain a valid one-time key."
                )
            return {
                "one_time_key": secret,
                "id": result.get("id"),
                "name": result.get("name"),
            }
        if action.startswith("keys."):
            # Only documented non-secret metadata leaves the transport boundary.
            entries = (
                result.get("data") if isinstance(result.get("data"), list) else [result]
            )
            clean = []
            for entry in entries:
                record = {
                    key: entry[key]
                    for key in (
                        "id",
                        "object",
                        "name",
                        "created_at",
                        "last_used_at",
                        "expires_at",
                        "scopes",
                    )
                    if key in entry
                }
                owner = entry.get("owner", {})
                if isinstance(owner, dict):
                    owner = owner.get(owner.get("type"), owner)
                    record["owner"] = {
                        key: owner[key]
                        for key in ("id", "name", "type")
                        if isinstance(owner, dict) and key in owner
                    }
                redacted = entry.get("redacted_value", "")
                record["hint"] = (
                    "…" + redacted[-4:]
                    if isinstance(redacted, str) and redacted
                    else "—"
                )
                clean.append(record)
            return {
                "data": clean,
                "has_more": result.get("has_more", False),
                "last_id": result.get("last_id"),
            }
        return result

    async def upload(
        self, kind: str, content: bytes, filename: str, mime: str, params: dict
    ) -> dict:
        """Send explicitly selected content to Files or transcription endpoints.

        Args:
            kind: files, transcription or translation.
            content: At most 25 MiB, held only for this request.
            filename: Untrusted upload filename.
            mime: Uploaded media type.
            params: Purpose/model/project parameters.

        Returns:
            Public API result.
        """
        if not content or len(content) > 25 * 1024 * 1024:
            raise ValueError("Uploads must be non-empty and at most 25 MiB.")
        safe_name = (
            re.sub(
                r"[^A-Za-z0-9_.-]", "_", filename.replace("\\", "/").rsplit("/", 1)[-1]
            )[:128]
            or "upload.bin"
        )
        if kind == "files":
            purpose = params.get("purpose", "user_data")
            if purpose not in (
                "assistants",
                "batch",
                "fine-tune",
                "vision",
                "user_data",
                "evals",
            ):
                raise ValueError("Unsupported file purpose.")
            if purpose in ("batch", "fine-tune") and not safe_name.endswith(".jsonl"):
                raise ValueError("Batch and fine-tuning require JSONL files.")
            path, fields = "/files", {"purpose": purpose}
        elif kind in ("transcription", "translation"):
            if (
                kind == "translation"
                and datetime.now(timezone.utc).date().isoformat() >= "2027-02-26"
            ):
                raise ValueError("Legacy audio translation is retired.")
            model = params.get(
                "model", "gpt-transcribe" if kind == "transcription" else "whisper-1"
            )
            if not isinstance(model, str) or not model or len(model) > 200:
                raise ValueError("Invalid audio model.")
            path, fields = (
                (
                    "/audio/transcriptions"
                    if kind == "transcription"
                    else "/audio/translations"
                ),
                {"model": model},
            )
        else:
            raise ValueError("Unknown upload type.")
        return await self.client.request(
            "POST",
            path,
            body=fields,
            files={"file": (safe_name, content, mime)},
            project=params.get("project", ""),
        )


def dashboard_messages(report: dict) -> list[str]:
    """Format every Dashboard section as bounded message-pipeline text chunks.

    Args:
        report: A freshly refreshed Dashboard report, including partial errors.

    Returns:
        Messages of at most 3000 characters containing totals, trends and projects.
    """
    scope = report["range"]
    lines = [
        "AetherNexus 用量報告",
        f"更新時間：{report['refreshed_at']}（UTC）",
        "範圍：所有專案",
        f"用量期間：{scope['start']} 至 {scope['end']}（UTC）",
        "",
    ]
    usage, costs = report["usage"], report["costs"]
    if "error" in usage:
        lines.append(f"用量載入失敗：{usage['error']}")
    else:
        totals = usage["totals"]
        for key, label in (
            ("input_tokens", "輸入 Token（含快取）"),
            ("output_tokens", "輸出 Token"),
            ("num_model_requests", "請求數"),
            ("input_cached_tokens", "快取輸入 Token"),
        ):
            value = totals.get(key)
            lines.append(f"{label}：{value:,}" if value is not None else f"{label}：—")
        combined = (
            totals["input_tokens"] + totals["output_tokens"]
            if totals.get("input_tokens") is not None
            and totals.get("output_tokens") is not None
            else None
        )
        lines.append(
            f"總 Token：{combined:,}" if combined is not None else "總 Token：—"
        )
        ratio = usage.get("cache_percent")
        lines.append(
            f"加權快取比例：{ratio:.2f}%" if ratio is not None else "加權快取比例：—"
        )
        lines.extend(["", "每日趨勢（輸入／輸出／快取輸入／請求數）"])
        for bucket in usage["buckets"]:
            values = []
            for key in (
                "input_tokens",
                "output_tokens",
                "input_cached_tokens",
                "num_model_requests",
            ):
                entries = [row.get(key) for row in bucket["results"]]
                value = (
                    sum(entries)
                    if all(entry is not None for entry in entries)
                    else None
                )
                values.append(f"{value:,}" if value is not None else "—")
            day = datetime.fromtimestamp(bucket["start_time"], timezone.utc).strftime(
                "%Y-%m-%d"
            )
            lines.append(f"{day}：{'／'.join(values)}")
    lines.extend(["", "本月成本（USD；所有成本項目，並非帳戶餘額）"])
    if "error" in costs:
        lines.append(f"成本載入失敗：{costs['error']}")
        amount = None
    else:
        amount = costs["totals"].get("amount_usd")
        lines.append(
            f"本月累計：${amount:,.6f}" if amount is not None else "本月累計：—"
        )
        for bucket in costs["buckets"]:
            entries = [row.get("amount", {}).get("value") for row in bucket["results"]]
            value = (
                sum((Decimal(str(entry)) for entry in entries), Decimal(0))
                if all(entry is not None for entry in entries)
                else None
            )
            day = datetime.fromtimestamp(bucket["start_time"], timezone.utc).strftime(
                "%Y-%m-%d"
            )
            lines.append(f"{day}：${value:,.6f}" if value is not None else f"{day}：—")
    budget = report["settings"].get("monthly_usd_cents")
    lines.append(
        f"本機每月參考預算：${budget / 100:,.2f}"
        if budget
        else "本機每月參考預算：未設定"
    )
    if budget and amount is not None:
        lines.append(f"參考預算使用比例：{amount / (budget / 100) * 100:.2f}%")
    projects = report["projects"]
    lines.extend(["", "專案清單（含已封存專案）"])
    if "error" in projects:
        lines.append(f"專案載入失敗：{projects['error']}")
    else:
        lines.append(f"共 {len(projects['data'])} 個專案")
        for project in projects["data"]:
            name = project["name"].replace("\r", " ").replace("\n", " ") or "未命名"
            lines.append(
                f"{name} · {project['id']}"
                + ("（已封存）" if project.get("status") == "archived" else "")
            )
    lines.extend(
        ["", "— 表示資料不可用；成本及本機預算並非 OpenAI 帳戶餘額或伺服器額度。"]
    )
    messages, current = [], ""
    for line in lines:
        # Split unusually long project names as well as the overall report.
        for offset in range(0, max(1, len(line)), 2999):
            piece = line[offset : offset + 2999] + "\n"
            if len(current) + len(piece) > 3000:
                messages.append(current.rstrip())
                current = ""
            current += piece
    if current:
        messages.append(current.rstrip())
    return messages


def usage_csv(report: dict) -> bytes:
    """Encode a usage report with spreadsheet formula protection.

    Args:
        report: A validated usage report from WorkspaceService.usage.

    Returns:
        UTF-8 CSV with stable UTC timestamp columns.
    """
    rows = report["rows"]
    keys = list(dict.fromkeys(key for row in rows for key in row)) or [
        "start_time_unix_utc",
        "end_time_unix_utc",
        "category",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=keys)
    writer.writeheader()
    for row in rows:
        clean = {}
        for key, val in row.items():
            if isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
            if (
                isinstance(val, str)
                and val.lstrip().startswith(("=", "+", "-", "@"))
                and key != "amount_usd"
            ):
                val = "'" + val
            clean[key] = val
        writer.writerow(clean)
    return output.getvalue().encode("utf-8-sig")
