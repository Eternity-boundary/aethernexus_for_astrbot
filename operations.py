"""Allowlisted BUILD/MANAGE operations matching the native client contracts.

 Copyright (c) 2026 Skylight Software Organization.
 Created by EternityBoundary
 All rights reserved.
 SPDX-License-Identifier: GPL-3.0-only
 
 File: operations.py
 Project: AetherNexus for AstrBot
"""

import json
import re
from datetime import datetime, timezone

# Each descriptor is also sent to the WebUI, keeping forms and request paths aligned.
# No user-controlled URL, HTTP method, or credential selector is accepted.
OPERATIONS = {
    "models.list": ("models", "模型清單", "GET", "/models", False, ""),
    "logs.list": (
        "logs",
        "已儲存 Chat Completions",
        "GET",
        "/chat/completions",
        False,
        "",
    ),
    "logs.messages": (
        "logs",
        "Chat 訊息",
        "GET",
        "/chat/completions/{id}/messages",
        False,
        "id",
    ),
    "logs.delete": (
        "logs",
        "刪除 Chat",
        "DELETE",
        "/chat/completions/{id}",
        False,
        "id",
    ),
    "responses.get": (
        "logs",
        "依 ID 查詢 Response",
        "GET",
        "/responses/{id}",
        False,
        "id",
    ),
    "responses.inputs": (
        "logs",
        "Response 輸入",
        "GET",
        "/responses/{id}/input_items",
        False,
        "id",
    ),
    "responses.delete": (
        "logs",
        "刪除 Response",
        "DELETE",
        "/responses/{id}",
        False,
        "id",
    ),
    "traces.list": ("traces", "Agent sessions", "GET", "/agents/sessions", False, ""),
    "traces.session": (
        "traces",
        "Session traces",
        "GET",
        "/agents/sessions/{id}/traces",
        False,
        "id",
    ),
    "batches.list": ("batches", "批次清單", "GET", "/batches", False, ""),
    "batches.get": ("batches", "批次狀態", "GET", "/batches/{id}", False, "id"),
    "batches.create": ("batches", "建立批次", "POST", "/batches", False, ""),
    "batches.cancel": (
        "batches",
        "取消批次",
        "POST",
        "/batches/{id}/cancel",
        False,
        "id",
    ),
    "evals.list": ("evaluations", "既有評估（唯讀）", "GET", "/evals", False, ""),
    "evals.runs": ("evaluations", "評估 runs", "GET", "/evals/{id}/runs", False, "id"),
    "evals.outputs": (
        "evaluations",
        "Run output items",
        "GET",
        "/evals/{parent}/runs/{id}/output_items",
        False,
        "parent,id",
    ),
    "finetuning.list": (
        "fine-tuning",
        "訓練工作",
        "GET",
        "/fine_tuning/jobs",
        False,
        "",
    ),
    "finetuning.get": (
        "fine-tuning",
        "訓練工作狀態",
        "GET",
        "/fine_tuning/jobs/{id}",
        False,
        "id",
    ),
    "finetuning.events": (
        "fine-tuning",
        "訓練事件",
        "GET",
        "/fine_tuning/jobs/{id}/events",
        False,
        "id",
    ),
    "finetuning.checkpoints": (
        "fine-tuning",
        "Checkpoints",
        "GET",
        "/fine_tuning/jobs/{id}/checkpoints",
        False,
        "id",
    ),
    "finetuning.create": (
        "fine-tuning",
        "建立訓練工作",
        "POST",
        "/fine_tuning/jobs",
        False,
        "",
    ),
    "finetuning.cancel": (
        "fine-tuning",
        "取消訓練工作",
        "POST",
        "/fine_tuning/jobs/{id}/cancel",
        False,
        "id",
    ),
    "files.list": ("storage", "Files", "GET", "/files", False, ""),
    "files.get": ("storage", "檔案資訊", "GET", "/files/{id}", False, "id"),
    "files.delete": ("storage", "刪除檔案", "DELETE", "/files/{id}", False, "id"),
    "vectors.list": ("storage", "向量庫", "GET", "/vector_stores", False, ""),
    "vectors.create": ("storage", "建立向量庫", "POST", "/vector_stores", False, ""),
    "vectors.delete": (
        "storage",
        "刪除向量庫",
        "DELETE",
        "/vector_stores/{id}",
        False,
        "id",
    ),
    "vectors.files": (
        "storage",
        "向量庫檔案",
        "GET",
        "/vector_stores/{id}/files",
        False,
        "id",
    ),
    "vectors.attach": (
        "storage",
        "附加檔案",
        "POST",
        "/vector_stores/{id}/files",
        False,
        "id",
    ),
    "vectors.detach": (
        "storage",
        "移除檔案關聯",
        "DELETE",
        "/vector_stores/{parent}/files/{id}",
        False,
        "parent,id",
    ),
    "vectors.search": (
        "storage",
        "搜尋向量庫",
        "POST",
        "/vector_stores/{id}/search",
        False,
        "id",
    ),
    "projects.list": (
        "projects",
        "專案清單（含已封存）",
        "GET",
        "/organization/projects",
        True,
        "",
    ),
    "projects.get": (
        "projects",
        "專案資訊",
        "GET",
        "/organization/projects/{project}",
        True,
        "project",
    ),
    "projects.create": (
        "projects",
        "建立專案",
        "POST",
        "/organization/projects",
        True,
        "",
    ),
    "projects.update": (
        "projects",
        "重新命名專案",
        "POST",
        "/organization/projects/{project}",
        True,
        "project",
    ),
    "projects.archive": (
        "projects",
        "封存專案",
        "POST",
        "/organization/projects/{project}/archive",
        True,
        "project",
    ),
    "users.list": (
        "projects",
        "專案成員",
        "GET",
        "/organization/projects/{project}/users",
        True,
        "project",
    ),
    "users.add": (
        "projects",
        "新增組織既有成員",
        "POST",
        "/organization/projects/{project}/users",
        True,
        "project",
    ),
    "users.update": (
        "projects",
        "修改成員角色",
        "POST",
        "/organization/projects/{project}/users/{id}",
        True,
        "project,id",
    ),
    "users.remove": (
        "projects",
        "移除成員",
        "DELETE",
        "/organization/projects/{project}/users/{id}",
        True,
        "project,id",
    ),
    "limits.list": (
        "projects",
        "模型速率限制",
        "GET",
        "/organization/projects/{project}/rate_limits",
        True,
        "project",
    ),
    "limits.update": (
        "projects",
        "修改速率限制",
        "POST",
        "/organization/projects/{project}/rate_limits/{id}",
        True,
        "project,id",
    ),
    "keys.admin": (
        "api-keys",
        "組織 Admin keys",
        "GET",
        "/organization/admin_api_keys",
        True,
        "",
    ),
    "keys.project": (
        "api-keys",
        "專案 API keys",
        "GET",
        "/organization/projects/{project}/api_keys",
        True,
        "project",
    ),
    "keys.update": (
        "api-keys",
        "修改專案 key scopes",
        "POST",
        "/organization/projects/{project}/api_keys/{id}",
        True,
        "project,id",
    ),
    "keys.revoke": (
        "api-keys",
        "撤銷專案 key",
        "DELETE",
        "/organization/projects/{project}/api_keys/{id}",
        True,
        "project,id",
    ),
    "keys.revoke_admin": (
        "api-keys",
        "撤銷 Admin key",
        "DELETE",
        "/organization/admin_api_keys/{id}",
        True,
        "id",
    ),
    "keys.issue_admin": (
        "api-keys",
        "簽發 Admin key（僅顯示一次）",
        "POST",
        "/organization/admin_api_keys",
        True,
        "",
    ),
    "keys.create_account": (
        "api-keys",
        "建立服務帳戶與 key",
        "POST",
        "/organization/projects/{project}/service_accounts",
        True,
        "project",
    ),
    "keys.issue_account": (
        "api-keys",
        "簽發既有服務帳戶 key",
        "POST",
        "/organization/projects/{project}/service_accounts/{id}/api_keys",
        True,
        "project,id",
    ),
}

BODY_EXAMPLES = {
    "batches.create": {
        "input_file_id": "file_…",
        "endpoint": "/v1/responses",
        "completion_window": "24h",
    },
    "finetuning.create": {
        "model": "",
        "training_file": "file_…",
        "method": {"type": "supervised"},
    },
    "vectors.create": {
        "name": "Knowledge",
        "expires_after": {"anchor": "last_active_at", "days": 30},
    },
    "vectors.attach": {"file_id": "file_…"},
    "vectors.search": {"query": "", "max_num_results": 10},
    "projects.create": {"name": "New project"},
    "projects.update": {"name": "Renamed project"},
    "users.add": {"user_id": "user_…", "role": "member"},
    "users.update": {"role": "member"},
    "limits.update": {"max_requests_per_1_minute": 100},
    "keys.update": {"scopes": ["api.all.read"]},
    "keys.issue_admin": {"name": "AetherNexus", "expires_in_seconds": 2592000},
    "keys.create_account": {"name": "AetherNexus service"},
    "keys.issue_account": {
        "name": "AetherNexus service key",
        "expires_in_seconds": 2592000,
    },
}


def describe_operations() -> list[dict]:
    """Return the public operation catalog used by the WebUI.

    Returns:
        JSON-safe descriptors without headers or credentials.
    """
    return [
        {
            "action": action,
            "group": s[0],
            "label": s[1],
            "method": s[2],
            "fields": s[5].split(",") if s[5] else [],
            "example": BODY_EXAMPLES.get(action, {}),
            "admin": s[4],
        }
        for action, s in OPERATIONS.items()
    ]


def prepare_operation(payload: dict, now: datetime | None = None) -> tuple:
    """Validate one declared operation and apply current lifecycle restrictions.

    Args:
        payload: Action, IDs, body, query and explicit mutation confirmation.
        now: Injectable UTC time for boundary tests.

    Returns:
        Descriptor, expanded path and validated query parameters.

    Raises:
        ValueError: Operation, scope, body, confirmation or policy is invalid.
    """
    action = payload.get("action")
    if action not in OPERATIONS:
        raise ValueError("Unknown API operation.")
    spec = OPERATIONS[action]
    path = spec[3]
    for field in spec[5].split(",") if spec[5] else []:
        val = payload.get(field, "")
        if not isinstance(val, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", val):
            raise ValueError(f"Invalid {field} ID.")
        path = path.replace("{" + field + "}", val)
    body, query = payload.get("body", {}), payload.get("query", {})
    if (
        not isinstance(body, dict)
        or not isinstance(query, dict)
        or len(json.dumps(body, allow_nan=False)) > 256 * 1024
    ):
        raise ValueError("Body and query must be bounded JSON objects.")
    allowed_query = {
        "after",
        "before",
        "limit",
        "order",
        "purpose",
        "model",
        "name",
        "include_archived",
    }
    if set(query) - allowed_query or any(
        not isinstance(v, (str, int, bool)) for v in query.values()
    ):
        raise ValueError("Unsupported query parameter.")
    if "limit" in query and (
        type(query["limit"]) is not int
        or not 1 <= query["limit"] <= (5 if action == "traces.session" else 100)
    ):
        raise ValueError("Invalid page limit.")
    if spec[2] != "GET":
        target = payload.get("id") or payload.get("project") or action
        if payload.get("confirm") != target:
            raise ValueError(
                "Confirm the exact target ID or action before this operation."
            )
    now = now or datetime.now(timezone.utc)
    if action.startswith("evals.") and now.date().isoformat() >= "2026-11-30":
        raise ValueError("The Evals API is retired. Open a local JSON export instead.")
    if action == "finetuning.create":
        if now.date().isoformat() >= "2027-01-06":
            raise ValueError("Creating new fine-tuning jobs is retired.")
        if (
            not body.get("model")
            or not body.get("training_file")
            or body.get("training_file") == body.get("validation_file")
        ):
            raise ValueError(
                "A model and distinct training/validation files are required."
            )
        if body.get("method", {}).get("type", "supervised") not in (
            "supervised",
            "dpo",
        ):
            raise ValueError("Only supervised and DPO creation are supported.")
    if action == "batches.create" and (
        body.get("completion_window") != "24h"
        or body.get("endpoint")
        not in (
            "/v1/responses",
            "/v1/chat/completions",
            "/v1/embeddings",
            "/v1/moderations",
            "/v1/images/generations",
            "/v1/images/edits",
        )
        or not body.get("input_file_id")
    ):
        raise ValueError(
            "Batch requires an input file, a supported endpoint, and completion_window=24h."
        )
    if action in ("users.add", "users.update") and body.get("role") not in (
        "owner",
        "member",
    ):
        raise ValueError("Role must be owner or member.")
    if action == "vectors.create" and "expires_after" in body:
        expires = body["expires_after"]
        if (
            not isinstance(expires, dict)
            or expires.get("anchor") != "last_active_at"
            or type(expires.get("days")) is not int
            or not 1 <= expires["days"] <= 365
        ):
            raise ValueError(
                "Vector store expiry must be 1–365 days after last activity."
            )
    if action == "projects.list":
        query = {**query, "include_archived": "true"}
    return spec, path, query
