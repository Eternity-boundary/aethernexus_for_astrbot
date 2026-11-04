"""Load the plugin against real AstrBot public APIs without starting AstrBot.

SPDX-License-Identifier: GPL-3.0-only
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from aethernexus_for_astrbot.client import PlatformClient
from aethernexus_for_astrbot.main import PLUGIN_NAME, AetherNexusPlugin
from astrbot.api.star import Context
from astrbot.api.web import PluginRequest, bind_request_context
from astrbot.core.star.star_manager import PluginManager
from astrbot.dashboard.services.plugin_page_service import PluginPageService
from starlette.requests import Request

PLUGIN_DIR = Path(__file__).resolve().parents[1]


class TestContext:
    """Use the real namespaced route registration implementation."""

    __test__ = False
    register_web_api = Context.register_web_api

    def __init__(self):
        self.registered_web_apis = []


def request_context(
    payload=None,
    owner="tester",
    content=None,
    content_type="application/json",
    query="",
):
    """Create a real AstrBot PluginRequest around an in-memory Starlette request.

    Args:
        payload: JSON body.
        owner: Dashboard identity.
        content: Optional raw request bytes.
        content_type: Content type for multipart tests.
        query: Encoded query string.

    Returns:
        The public request binding context manager.
    """
    body = content if content is not None else json.dumps(payload or {}).encode()

    async def receive():
        """Return the synthetic request body.

        Returns:
            An ASGI receive event.
        """
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "query_string": query.encode(),
            "headers": [(b"content-type", content_type.encode())],
        },
        receive,
    )
    return bind_request_context(
        PluginRequest(request, plugin_name=PLUGIN_NAME, username=owner)
    )


@pytest.fixture
async def plugin(tmp_path, monkeypatch):
    """Create a real Star instance with isolated data and a fake transport.

    Args:
        tmp_path: Isolated data directory.
        monkeypatch: Pytest patch fixture.

    Yields:
        Initialized plugin and recorded outbound requests.
    """
    import aethernexus_for_astrbot.main as main

    monkeypatch.setattr(main, "get_astrbot_plugin_data_path", lambda: str(tmp_path))
    instance = AetherNexusPlugin(TestContext(), {})
    await instance.client.close()
    seen = []

    def respond(req):
        seen.append(req)
        if req.url.path == "/v1/responses":
            return httpx.Response(
                200,
                text='data: {"type":"response.output_text.delta","delta":"offline"}\n\ndata: {"type":"response.completed","response":{"status":"completed","id":"resp_test","output":[]}}\n\n',
            )
        return httpx.Response(
            200, json={"data": [], "id": "file_test", "has_more": False}
        )

    instance.client = PlatformClient(
        lambda kind: "synthetic-" + kind, transport=httpx.MockTransport(respond)
    )
    await instance.initialize()
    yield instance, seen
    await instance.terminate()


@pytest.mark.asyncio
async def test_real_star_lifecycle_and_routes_do_not_call_api(plugin):
    instance, seen = plugin
    assert len(instance.context.registered_web_apis) == 9
    assert all(
        route.startswith("/" + PLUGIN_NAME + "/")
        for route, *_ in instance.context.registered_web_apis
    )
    with request_context():
        response = await instance.status()
    assert response.status_code == 200 and seen == []
    assert json.loads(response.body)["credentials"]["api"]["source"] == "missing"


@pytest.mark.asyncio
async def test_bridge_action_uses_real_public_request_and_response_types(plugin):
    instance, seen = plugin
    with request_context({"action": "catalog"}):
        response = await instance.action()
    assert json.loads(response.body)["operations"] and seen == []
    with request_context({"action": "models.list"}):
        response = await instance.action()
    assert response.status_code == 200 and len(seen) == 1
    assert seen[0].headers["authorization"] == "Bearer synthetic-api"


@pytest.mark.asyncio
async def test_session_credential_never_enters_database_or_status(plugin):
    instance, _ = plugin
    with request_context({"kind": "api", "value": "synthetic-session-key"}):
        response = await instance.credentials()
    assert response.status_code == 200
    with request_context():
        response = await instance.status()
    assert b"synthetic-session-key" not in response.body
    assert b"synthetic-session-key" not in instance.service.store.path.read_bytes()
    assert instance.credential("api") == "synthetic-session-key"
    with request_context({"kind": "api", "mode": "clear"}):
        await instance.credentials()
    assert instance.credential("api") == ""


@pytest.mark.asyncio
async def test_stream_is_owned_single_subscription_and_cleans_up(plugin):
    instance, _ = plugin
    with request_context({"body": {"model": "test-model", "input": "hello"}}):
        response = await instance.start_run()
    run_id = json.loads(response.body)["run_id"]
    with request_context(owner="someone-else"):
        denied = await instance.run_events(run_id)
    assert denied.status_code == 404
    with request_context():
        response = await instance.run_events(run_id)
    with request_context():
        duplicate = await instance.run_events(run_id)
    assert duplicate.status_code == 409
    events = "".join([event async for event in response.body_iterator])
    assert "offline" in events and "completed" in events
    assert run_id not in instance.jobs


@pytest.mark.asyncio
async def test_cancel_and_terminate_release_jobs(plugin):
    instance, _ = plugin
    with request_context({"body": {"model": "test-model", "input": "hello"}}):
        response = await instance.start_run()
    run_id = json.loads(response.body)["run_id"]
    with request_context():
        response = await instance.cancel_run(run_id)
    assert response.status_code == 200 and run_id not in instance.jobs
    instance.secrets["api"] = "synthetic"
    await instance.terminate()
    assert (
        instance.jobs == {}
        and instance.secrets == {}
        and instance.client.http.is_closed
    )
    assert instance.context.registered_web_apis == []


@pytest.mark.asyncio
async def test_unloading_old_instance_preserves_replacement_routes(plugin):
    instance, _ = plugin
    replacement = AetherNexusPlugin(instance.context, {})
    try:
        await instance.terminate()
        assert len(instance.context.registered_web_apis) == 9
        assert all(
            getattr(api[1], "__self__", None) is replacement
            for api in instance.context.registered_web_apis
        )
    finally:
        await replacement.terminate()


@pytest.mark.asyncio
async def test_bridge_upload_ticket_preserves_options_and_is_single_use(plugin):
    instance, seen = plugin
    with request_context(
        {"kind": "files", "params": {"purpose": "batch", "project": "proj_test"}}
    ):
        response = await instance.prepare_upload()
    ticket = json.loads(response.body)["upload_id"]
    upload = httpx.Request(
        "POST",
        "http://localhost/upload",
        files={"file": ("test.jsonl", b'{"test":1}\n', "application/jsonl")},
    )
    content = upload.read()
    with request_context(content=content, content_type=upload.headers["content-type"]):
        response = await instance.upload(ticket)
    assert response.status_code == 200
    assert seen[0].headers["openai-project"] == "proj_test"
    assert b"batch" in seen[0].content
    with request_context(content=content, content_type=upload.headers["content-type"]):
        response = await instance.upload(ticket)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_invalid_action_and_cross_user_upload_are_rejected(plugin):
    instance, seen = plugin
    with request_context({"action": "https://evil.invalid"}):
        response = await instance.action()
    assert response.status_code == 400 and seen == []
    with request_context({"kind": "files"}):
        response = await instance.prepare_upload()
    ticket = json.loads(response.body)["upload_id"]
    with request_context(owner="someone-else"):
        response = await instance.upload(ticket)
    assert response.status_code == 400 and seen == []


@pytest.mark.asyncio
async def test_real_metadata_loader_and_view_discovery():
    root = PLUGIN_DIR
    metadata = await asyncio.to_thread(PluginManager._load_plugin_metadata, str(root))
    assert metadata.name == PLUGIN_NAME
    assert metadata.astrbot_version == ">=4.29.4,<5"
    metadata.root_dir_name = root.name
    service = PluginPageService(SimpleNamespace(plugin_store_path=str(root.parent)))
    pages = await service.discover_plugin_pages(metadata)
    assert [page.name for page in pages] == ["workspace"]
    content = await asyncio.to_thread(
        (root / "views/workspace/index.html").read_text, encoding="utf-8"
    )
    html = service.process_plugin_page_html(
        content,
        theme="dark",
        extra_query_params=None,
    )
    assert "bridge-sdk.js" in html and 'data-theme="dark"' in html
