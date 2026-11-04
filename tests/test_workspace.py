"""Behavioral contracts ported from the native isolated test suites.

SPDX-License-Identifier: GPL-3.0-only
"""

import ast
import base64
import copy
import io
import json
import wave
from datetime import datetime, timezone

import httpx
import pytest
from aethernexus_for_astrbot.client import ApiError, PlatformClient
from aethernexus_for_astrbot.operations import OPERATIONS, prepare_operation
from aethernexus_for_astrbot.service import WorkspaceService, usage_csv
from aethernexus_for_astrbot.storage import LocalStore, render_variables
from aethernexus_for_astrbot.workflow import (
    export_python,
    run_workflow,
    validate_workflow,
)

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
FLOW = {
    "version": 1,
    "entry": "start",
    "nodes": [
        {"id": "start", "kind": "start", "next": "transform"},
        {
            "id": "transform",
            "kind": "transform",
            "instructions": "Hello {{input}}",
            "next": "condition",
        },
        {
            "id": "condition",
            "kind": "condition",
            "match": "world",
            "next": "end",
            "otherwise": "alternate",
        },
        {
            "id": "alternate",
            "kind": "transform",
            "instructions": "alternate",
            "next": "end",
        },
        {"id": "end", "kind": "end"},
    ],
}


def client(handler):
    """Build a client with synthetic keys and a socket-free HTTP transport.

    Args:
        handler: Mock HTTP response handler.

    Returns:
        An isolated PlatformClient.
    """
    return PlatformClient(
        lambda kind: "synthetic-" + kind, transport=httpx.MockTransport(handler)
    )


@pytest.mark.parametrize(
    "text,variables,expected",
    [
        ("Hello {{name}}", {"name": "world"}, "Hello world"),
        ("{{a}} {{b}}", {"a": "{{b}}", "b": "世界"}, "{{b}} 世界"),
        ("plain", {}, "plain"),
    ],
)
def test_variables_are_single_pass(text, variables, expected):
    assert render_variables(text, variables) == expected


@pytest.mark.parametrize(
    "text,variables",
    [("{{missing}}", {}), ("{{broken", {}), ("{{x}}", {"x": 1}), ("x" * 65537, {})],
)
def test_variables_reject_invalid_input(text, variables):
    with pytest.raises(ValueError):
        render_variables(text, variables)


def test_prompt_revisions_conflicts_restore_and_secret_exclusion(tmp_path):
    store = LocalStore(tmp_path)
    first = store.prompts(
        {
            "name": "Prompt",
            "model": "test-model",
            "instructions": "first",
            "value": "never-persist-this",
        }
    )[-1]
    assert first["version"] == 1
    assert "value" not in first
    second = store.prompts({**first, "instructions": "second"})[-1]
    assert second["version"] == 2
    with pytest.raises(ValueError, match="another editor"):
        store.prompts(first)
    restored = store.prompts({**first, "version": second["version"]})[-1]
    assert restored["version"] == 3 and restored["instructions"] == "first"
    assert b"never-persist-this" not in store.path.read_bytes()
    assert LocalStore(tmp_path).prompts() == store.prompts()
    assert store.prompts(remove=first["id"]) == []


@pytest.mark.parametrize(
    "settings",
    [
        {"theme": "invalid"},
        {"monthly_usd_cents": 0},
        {"monthly_usd_cents": True},
        {"monthly_usd_cents": 1.5},
    ],
)
def test_invalid_preferences_do_not_replace_previous_settings(tmp_path, settings):
    store = LocalStore(tmp_path)
    before = store.settings({"theme": "dark", "monthly_usd_cents": 12345})
    with pytest.raises(ValueError):
        store.settings(settings)
    assert store.settings() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,expected", [("world", "Hello world"), ("other", "alternate")]
)
async def test_workflow_transform_condition_and_trace(text, expected):
    result = await run_workflow(FLOW, text, None)
    assert result["text"] == expected
    assert result["steps"][0]["node"] == "start"


@pytest.mark.asyncio
async def test_workflow_cycles_are_bounded():
    flow = copy.deepcopy(FLOW)
    flow["nodes"][0]["next"] = "start"
    with pytest.raises(ValueError, match="64 steps"):
        await run_workflow(flow, "hello", None)


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "missing-next", "bad-entry", "unknown-kind", "nan-position"],
)
def test_workflow_structure(mutation):
    flow = copy.deepcopy(FLOW)
    if mutation == "duplicate":
        flow["nodes"].append(flow["nodes"][0])
    if mutation == "missing-next":
        flow["nodes"][0]["next"] = "missing"
    if mutation == "bad-entry":
        flow["entry"] = "end"
    if mutation == "unknown-kind":
        flow["nodes"][0]["kind"] = "shell"
    if mutation == "nan-position":
        flow["nodes"][0]["x"] = float("nan")
    with pytest.raises(ValueError):
        validate_workflow(flow)


def test_export_treats_user_content_as_data():
    flow = copy.deepcopy(FLOW)
    flow["nodes"][1]["instructions"] = '"\n__import__("os").system("unsafe")\n{{input}}'
    code = export_python(flow)
    ast.parse(code)
    assert '.system("unsafe")' not in code
    assert "OPENAI_API_KEY" in code


@pytest.mark.parametrize("action,spec", list(OPERATIONS.items()))
def test_all_operations_have_a_bound_path_and_required_confirmation(action, spec):
    payload = {
        "action": action,
        "id": "id_test",
        "parent": "parent_test",
        "project": "proj_test",
        "body": {},
        "confirm": "id_test",
    }
    if action == "batches.create":
        payload["body"] = {
            "input_file_id": "file_test",
            "endpoint": "/v1/responses",
            "completion_window": "24h",
        }
    if action == "finetuning.create":
        payload["body"] = {"model": "test-model", "training_file": "file_train"}
    if action in ("users.add", "users.update"):
        payload["body"] = {"role": "member"}
    prepared, path, _ = prepare_operation(payload, NOW)
    assert prepared == spec and "{" not in path and path.startswith("/")
    if spec[2] != "GET":
        with pytest.raises(ValueError, match="Confirm"):
            prepare_operation({**payload, "confirm": "wrong"}, NOW)


@pytest.mark.parametrize(
    "bad_id",
    ["../outside", "https://evil.invalid", "proj/a", "a?query=1", "a\r\nX-Header: bad"],
)
def test_remote_paths_reject_untrusted_ids(bad_id):
    with pytest.raises(ValueError):
        prepare_operation({"action": "files.get", "id": bad_id}, NOW)


@pytest.mark.parametrize(
    "action,date", [("evals.list", "2026-11-30"), ("finetuning.create", "2027-01-06")]
)
def test_retirement_dates_are_enforced(action, date):
    with pytest.raises(ValueError, match="retired"):
        prepare_operation(
            {"action": action, "confirm": action},
            datetime.fromisoformat(date).replace(tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_transport_separates_credentials_and_never_retries_or_redirects():
    requests = []

    def respond(req):
        requests.append(req)
        return httpx.Response(
            302,
            headers={"location": "https://evil.invalid"},
            text="private-secret-body",
        )

    api = client(respond)
    for admin in (False, True):
        with pytest.raises(ApiError) as error:
            await api.request(
                "POST", "/responses", body={"input": "private"}, admin=admin
            )
        assert "private" not in str(error.value)
    assert len(requests) == 2
    assert requests[0].headers["authorization"] == "Bearer synthetic-api"
    assert requests[1].headers["authorization"] == "Bearer synthetic-admin"
    assert all(r.url.host == "api.openai.com" for r in requests)
    await api.close()


class FragmentedStream(httpx.AsyncByteStream):
    """Split a synthetic SSE stream at every byte, including UTF-8 boundaries."""

    def __init__(self, content):
        self.content = content

    async def __aiter__(self):
        for byte in self.content:
            yield bytes([byte])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal",
    ["response.completed", "response.failed", "response.incomplete", "truncated"],
)
async def test_sse_unicode_fragmentation_and_terminal_contract(terminal):
    data = 'data: {"type":"response.output_text.delta","delta":"你好"}\r\n\r\n'
    if terminal != "truncated":
        data += f"data: {json.dumps({'type': terminal, 'response': {'id': 'resp_test'}})}\r\n\r\n"
    api = client(
        lambda req: httpx.Response(200, stream=FragmentedStream(data.encode()))
    )
    events = []
    if terminal == "response.completed":
        events = [
            e async for e in api.stream_chat({"model": "test-model", "input": "test"})
        ]
        assert events[-1]["type"] == "completed" and events[0]["text"] == "你好"
    else:
        with pytest.raises(ApiError):
            async for event in api.stream_chat(
                {"model": "test-model", "input": "test"}
            ):
                events.append(event)
        assert events[0]["text"] == "你好"
    await api.close()


@pytest.mark.asyncio
async def test_usage_pagination_weighted_cache_and_project_scope(tmp_path):
    seen = []

    def respond(req):
        seen.append(req)
        page = req.url.params.get("page")
        row = {
            "input_tokens": 900 if page else 100,
            "output_tokens": 2000,
            "input_cached_tokens": 0 if page else 100,
            "num_model_requests": 1,
        }
        return httpx.Response(
            200,
            json={
                "data": [
                    {"start_time": 1793491200, "end_time": 1793577600, "results": [row]}
                ],
                "has_more": not page,
                "next_page": "next" if not page else None,
            },
        )

    api = client(respond)
    service = WorkspaceService(api, LocalStore(tmp_path))
    report = await service.usage(
        {"start": "2026-11-01", "end": "2026-11-02", "project": "proj_test"}
    )
    assert report["totals"]["input_tokens"] == 1000 and report["cache_percent"] == 10
    assert report["totals"]["output_tokens"] == 4000
    assert len(report["buckets"]) == 2
    assert len(report["buckets"][0]["results"]) == 2
    assert all(req.url.params["project_ids"] == "proj_test" for req in seen)
    assert all(req.headers["authorization"] == "Bearer synthetic-admin" for req in seen)
    await api.close()


@pytest.mark.asyncio
async def test_missing_cache_does_not_turn_into_zero_and_storage_does_not_sum(tmp_path):
    row = {
        "input_tokens": 100,
        "output_tokens": 50,
        "num_model_requests": 1,
        "usage_bytes": 123,
    }
    api = client(
        lambda req: httpx.Response(
            200,
            json={
                "data": [{"start_time": 1793491200, "results": [row]}],
                "has_more": False,
            },
        )
    )
    service = WorkspaceService(api, LocalStore(tmp_path))
    report = await service.usage({"start": "2026-11-01", "end": "2026-11-02"})
    assert report["cache_percent"] is None and report["totals"]["usage_bytes"] is None
    await api.close()


@pytest.mark.asyncio
async def test_costs_allow_negative_credits_and_csv_rejects_formulas(tmp_path):
    api = client(
        lambda req: httpx.Response(
            200,
            json={
                "data": [
                    {
                        "start_time": 1793491200,
                        "results": [
                            {
                                "amount": {"value": "-0.25", "currency": "usd"},
                                "project_id": "=HYPERLINK(1)",
                            }
                        ],
                    }
                ],
                "has_more": False,
            },
        )
    )
    report = await WorkspaceService(api, LocalStore(tmp_path)).usage(
        {"start": "2026-11-01", "end": "2026-11-02", "category": "costs"}
    )
    assert report["totals"]["amount_usd"] == -0.25
    csv = usage_csv(report).decode("utf-8-sig")
    assert "'=HYPERLINK" in csv and "-0.25" in csv
    await api.close()


@pytest.mark.asyncio
async def test_dashboard_preserves_successful_report_on_partial_failure(tmp_path):
    api = client(
        lambda req: (
            httpx.Response(403, text="private")
            if req.url.path.endswith("/costs")
            else httpx.Response(200, json={"data": [], "has_more": False})
        )
    )
    result = await WorkspaceService(api, LocalStore(tmp_path)).dashboard(
        {"start": "2026-11-01", "end": "2026-11-02"}
    )
    assert result["usage"]["totals"]["input_tokens"] == 0 and "error" in result["costs"]
    await api.close()


@pytest.mark.asyncio
async def test_key_metadata_is_scrubbed_and_issuance_is_one_time(tmp_path):
    def respond(req):
        if req.method == "POST":
            return httpx.Response(
                200, json={"id": "key_1", "value": "synthetic-issued-key"}
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "key_1",
                        "value": "must-never-leak",
                        "redacted_value": "redactedabcd",
                        "owner": {"name": "owner", "value": "also-private"},
                    }
                ]
            },
        )

    api = client(respond)
    service = WorkspaceService(api, LocalStore(tmp_path))
    result = await service.action({"action": "keys.admin"})
    assert "must-never-leak" not in json.dumps(
        result
    ) and "also-private" not in json.dumps(result)
    assert result["data"][0]["hint"] == "…abcd"
    issued = await service.action(
        {"action": "keys.issue_admin", "confirm": "keys.issue_admin"}
    )
    assert issued["one_time_key"] == "synthetic-issued-key"
    assert service.store.prompts() == []
    await api.close()


@pytest.mark.asyncio
async def test_multipart_transcription_and_image_edit_use_general_key(tmp_path):
    seen = []

    def respond(req):
        seen.append(req)
        return httpx.Response(200, json={"text": "test", "data": []})

    api = client(respond)
    service = WorkspaceService(api, LocalStore(tmp_path))
    await service.upload(
        "transcription",
        b"fake-audio",
        "../audio.wav",
        "audio/wav",
        {"model": "test-transcribe"},
    )
    await service.action(
        {
            "action": "images.generate",
            "body": {"model": "test-image", "prompt": "edit"},
            "references": [
                {"data": base64.b64encode(b"fake-png").decode(), "mime": "image/png"}
            ],
        }
    )
    assert (
        seen[0].url.path == "/v1/audio/transcriptions"
        and seen[1].url.path == "/v1/images/edits"
    )
    assert all(
        r.headers["content-type"].startswith("multipart/form-data") for r in seen
    )
    assert all(r.headers["authorization"] == "Bearer synthetic-api" for r in seen)
    assert b"../audio" not in seen[0].content
    await api.close()


class FakeRealtime:
    """Socket-free GA Realtime protocol peer."""

    def __init__(self):
        self.sent = []
        self.events = iter(
            [
                {"type": "session.created"},
                {"type": "session.updated"},
                {"type": "response.output_audio_transcript.delta", "delta": "hello"},
                {
                    "type": "response.output_audio.delta",
                    "delta": base64.b64encode(b"\x00\x01" * 50).decode(),
                },
                {
                    "type": "response.done",
                    "response": {"status": "completed", "id": "resp_test"},
                },
            ]
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return json.dumps(next(self.events))
        except StopIteration:
            raise StopAsyncIteration from None

    async def send(self, message):
        self.sent.append(json.loads(message))


@pytest.mark.asyncio
async def test_realtime_protocol_and_wav_output():
    peer = FakeRealtime()
    api = PlatformClient(lambda kind: "synthetic-api", websocket=lambda *a, **k: peer)
    result = await api.realtime({"model": "test-realtime", "input": "hello"})
    assert result["text"] == "hello"
    with wave.open(io.BytesIO(base64.b64decode(result["audio"])), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (
            24000,
            1,
            2,
        )
    assert [e["type"] for e in peer.sent] == [
        "session.update",
        "conversation.item.create",
        "response.create",
    ]
    assert peer.sent[0]["session"]["audio"]["input"]["turn_detection"] is None
    await api.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category,metric",
    [
        ("images", "images"),
        ("audio_speeches", "characters"),
        ("audio_transcriptions", "seconds"),
        ("vector_stores", "usage_bytes"),
        ("costs", "amount_usd"),
    ],
)
async def test_empty_usage_keeps_category_units(tmp_path, category, metric):
    api = client(lambda req: httpx.Response(200, json={"data": [], "has_more": False}))
    report = await WorkspaceService(api, LocalStore(tmp_path)).usage(
        {"start": "2026-11-01", "end": "2026-11-02", "category": category}
    )
    assert report["totals"][metric] == (None if metric == "usage_bytes" else 0)
    assert len(report["buckets"]) == 2
    await api.close()


@pytest.mark.asyncio
async def test_invalid_cache_and_pagination_cannot_produce_success(tmp_path):
    api = client(
        lambda req: httpx.Response(
            200,
            json={
                "data": [
                    {
                        "start_time": 1793491200,
                        "results": [{"input_tokens": 10, "input_cached_tokens": 20}],
                    }
                ],
                "has_more": False,
            },
        )
    )
    with pytest.raises(ApiError, match="exceed"):
        await WorkspaceService(api, LocalStore(tmp_path)).usage(
            {"start": "2026-11-01", "end": "2026-11-02"}
        )
    await api.close()
    api = client(
        lambda req: httpx.Response(
            200, json={"data": [], "has_more": True, "next_page": "repeated"}
        )
    )
    with pytest.raises(ApiError, match="repeated"):
        await WorkspaceService(api, LocalStore(tmp_path)).usage(
            {"start": "2026-11-01", "end": "2026-11-02"}
        )
    await api.close()


def test_python_sources_accept_python_310_syntax():
    from pathlib import Path

    for source in Path(__file__).resolve().parents[1].glob("*.py"):
        ast.parse(source.read_text(encoding="utf-8-sig"), feature_version=(3, 10))
