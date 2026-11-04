"""Exercise the usage command with real message types and socket-free APIs.

 Copyright (c) 2026 Skylight Software Organization.
 Created by EternityBoundary
 All rights reserved.
 SPDX-License-Identifier: GPL-3.0-only
 
 File: test_usage_command.py
 Project: AetherNexus for AstrBot
"""

import json
import sqlite3

import httpx
import pytest
from aethernexus_for_astrbot.client import PlatformClient
from aethernexus_for_astrbot.main import AetherNexusPlugin
from aethernexus_for_astrbot.service import dashboard_messages
from aethernexus_for_astrbot.storage import LocalStore
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.star_handler import star_handlers_registry
from test_plugin import request_context

pytest_plugins = ("test_plugin",)


@pytest.fixture
def event():
    """Create a genuine event after AstrBot's wake-prefix processing.

    Returns:
        Offline conversation event containing the registered command name.
    """
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "offline_bot"
    message.message_id = "offline_message"
    message.sender = MessageMember("offline_sender", "Tester")
    message.message = [Plain("用量")]
    return AstrMessageEvent(
        "用量",
        message,
        PlatformMetadata("offline", "Offline tests", "offline"),
        "offline_session",
    )


def test_usage_command_is_registered_with_official_filter(event):
    handlers = star_handlers_registry.get_handlers_by_module_name(
        AetherNexusPlugin.__module__
    )
    handler = next(h for h in handlers if h.handler_name == "usage_command")
    command = next(f for f in handler.event_filters if isinstance(f, CommandFilter))
    assert command.command_name == "用量"
    event.is_at_or_wake_command = True
    assert command.filter(event, {})
    event.message_str = "其他指令"
    assert not command.filter(event, {})


def test_usage_switch_defaults_and_legacy_settings_are_preserved(tmp_path):
    store = LocalStore(tmp_path)
    assert store.settings()["usage_command_enabled"] is False
    with sqlite3.connect(store.path) as db:
        db.execute(
            "INSERT INTO settings VALUES (1, ?)",
            (json.dumps({"theme": "dark", "monthly_usd_cents": 12000}),),
        )
    assert store.settings()["usage_command_enabled"] is False
    saved = store.settings({"usage_command_enabled": True})
    assert saved == {
        "theme": "dark",
        "monthly_usd_cents": 12000,
        "usage_command_enabled": True,
    }
    assert LocalStore(tmp_path).settings()["usage_command_enabled"] is True
    assert store.settings({"theme": "light"})["usage_command_enabled"] is True
    with pytest.raises(ValueError, match="boolean"):
        store.settings({"usage_command_enabled": "false"})
    assert store.settings()["usage_command_enabled"] is True


@pytest.mark.asyncio
async def test_disabled_command_does_not_read_credentials_or_call_api(
    plugin, event, monkeypatch
):
    instance, seen = plugin

    def reject_credential_read(kind):
        raise AssertionError("Disabled command must not read credentials.")

    monkeypatch.setattr(instance, "credential", reject_credential_read)
    results = [r async for r in instance.usage_command(event)]
    assert all(isinstance(result, MessageEventResult) for result in results)
    assert "尚未開啟" in results[0].chain[0].text
    assert seen == [] and instance.service.latest_command_dashboard is None


@pytest.mark.asyncio
async def test_missing_admin_key_sends_setup_hint_instead_of_querying(plugin, event):
    instance, seen = plugin
    instance.service.store.settings({"usage_command_enabled": True})
    instance.secrets["api"] = "synthetic-general-only"
    results = [r async for r in instance.usage_command(event)]
    text = results[0].chain[0].text
    assert "Admin Key" in text and "Settings → Credentials" in text
    assert "synthetic-general-only" not in text and seen == []


@pytest.mark.asyncio
async def test_usage_refreshes_every_section_every_time_and_yields_pipeline_results(
    plugin, event
):
    instance, _ = plugin
    instance.service.store.settings(
        {"usage_command_enabled": True, "monthly_usd_cents": 10000}
    )
    instance.secrets["admin"] = "synthetic-admin"
    seen = []

    def respond(req):
        seen.append(req)
        if "/organization/projects" in req.url.path:
            after = req.url.params.get("after")
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "proj_two" if after else "proj_one",
                            "name": "Archived project" if after else "Current project",
                            "status": "archived" if after else "active",
                            "value": "never-share-this",
                        }
                    ],
                    "has_more": not after,
                    "last_id": "proj_one",
                },
            )
        start = int(req.url.params["start_time"])
        row = (
            {"amount": {"value": "1.25", "currency": "usd"}}
            if req.url.path.endswith("/costs")
            else {
                "input_tokens": 100,
                "output_tokens": 30,
                "input_cached_tokens": 40,
                "num_model_requests": 2,
            }
        )
        return httpx.Response(
            200,
            json={"data": [{"start_time": start, "results": [row]}], "has_more": False},
        )

    await instance.client.close()
    instance.client = PlatformClient(
        instance.credential, transport=httpx.MockTransport(respond)
    )
    instance.service.client = instance.client
    for _ in range(2):
        before = len(seen)
        results = [r async for r in instance.usage_command(event)]
        assert len(seen) - before == 4
        assert all(
            isinstance(result, MessageEventResult)
            and len(result.chain) == 1
            and isinstance(result.chain[0], Plain)
            for result in results
        )
        text = "\n".join(result.chain[0].text for result in results)
        for expected in (
            "輸入 Token（含快取）：100",
            "總 Token：130",
            "40.00%",
            "$1.250000",
            "每日趨勢",
            "本機每月參考預算：$100.00",
            "Current project",
            "Archived project",
            "已封存",
        ):
            assert expected in text
        assert "synthetic-admin" not in text and "never-share-this" not in text
        assert all(len(result.chain[0].text) <= 3000 for result in results)
    assert all(req.headers["authorization"] == "Bearer synthetic-admin" for req in seen)
    assert all(
        req.url.params["include_archived"] == "true"
        for req in seen
        if "projects" in req.url.path
    )
    with request_context({"action": "dashboard.latest"}):
        response = await instance.action()
    report = json.loads(response.body)["report"]
    assert (
        report["range"]["project"] == ""
        and report["projects"]["data"][1]["id"] == "proj_two"
    )


@pytest.mark.asyncio
async def test_partial_errors_are_sent_without_fabricating_zero_costs(plugin, event):
    instance, _ = plugin
    instance.service.store.settings({"usage_command_enabled": True})
    instance.secrets["admin"] = "synthetic-admin"
    await instance.client.close()
    instance.client = PlatformClient(
        instance.credential,
        transport=httpx.MockTransport(
            lambda req: (
                httpx.Response(403, text="secret-error-body")
                if req.url.path.endswith("/costs")
                else httpx.Response(200, json={"data": [], "has_more": False})
            )
        ),
    )
    instance.service.client = instance.client
    results = [result async for result in instance.usage_command(event)]
    text = "\n".join(result.chain[0].text for result in results)
    assert "輸入 Token（含快取）：0" in text and "成本載入失敗" in text
    assert "本月累計：$0" not in text and "secret-error-body" not in text


def test_long_dashboard_reports_split_without_losing_project_data():
    report = {
        "range": {"start": "2026-11-01", "end": "2026-11-07"},
        "refreshed_at": "2026-11-07T00:00:00+00:00",
        "usage": {"error": "unavailable"},
        "costs": {"error": "unavailable"},
        "settings": {},
        "projects": {
            "data": [
                {"id": f"proj_{i}", "name": "Project " + "x" * 100, "status": "active"}
                for i in range(100)
            ]
        },
    }
    messages = dashboard_messages(report)
    assert len(messages) > 1 and all(len(message) <= 3000 for message in messages)
    combined = "\n".join(messages)
    for i in range(100):
        assert f"proj_{i}" in combined
