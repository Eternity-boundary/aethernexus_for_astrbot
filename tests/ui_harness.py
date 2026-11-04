"""Explicitly offline UI host using the real AstrBot bridge and fake transports.

Run from the plugin directory: python tests/ui_harness.py
This test-only server binds loopback and never uses real credentials.
SPDX-License-Identifier: GPL-3.0-only
"""

import asyncio
import json
import os
import re
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

PLUGIN_DIR = Path(__file__).resolve().parents[1]
ASTRBOT_DIR = PLUGIN_DIR.parents[2]
sys.path.insert(0, str(PLUGIN_DIR.parent))
sys.path.insert(0, str(ASTRBOT_DIR))
os.environ["ASTRBOT_ROOT"] = tempfile.mkdtemp(prefix="aethernexus-ui-")

from aethernexus_for_astrbot.client import PlatformClient  # noqa: E402
from aethernexus_for_astrbot.main import AetherNexusPlugin  # noqa: E402
from astrbot.api.star import Context  # noqa: E402
from astrbot.api.web import PluginRequest, bind_request_context  # noqa: E402


class SlowSSE(httpx.AsyncByteStream):
    """Simulate delayed model output for streaming and stop interactions."""

    async def __aiter__(self):
        for delta in ("這是", "虛擬 API", " 的回應。", "所有驗證均在本機完成。"):
            await asyncio.sleep(0.05)
            yield (
                "data: "
                + json.dumps({"type": "response.output_text.delta", "delta": delta})
                + "\n\n"
            ).encode()
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_offline",
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "這是虛擬 API 的回應。所有驗證均在本機完成。",
                                    }
                                ],
                            }
                        ],
                    },
                }
            )
            + "\n\n"
        ).encode()


def fake_api(req):
    """Return only synthetic public-API-shaped data.

    Args:
        req: Request intercepted before network transport.

    Returns:
        Synthetic HTTP response.
    """
    path = req.url.path
    if "/usage/" in path or path.endswith("/costs"):
        start, end = int(req.url.params["start_time"]), int(req.url.params["end_time"])
        buckets = []
        for i, timestamp in enumerate(range(start, end, 86400)):
            row = (
                {"amount": {"value": str(round(0.5 + i * 0.27, 3)), "currency": "usd"}}
                if path.endswith("/costs")
                else {
                    "input_tokens": [13400, 22100, 18600, 30900, 26700, 35800, 29400][
                        i % 7
                    ],
                    "output_tokens": [4200, 6600, 5100, 8100, 7600, 10200, 8800][i % 7],
                    "input_cached_tokens": [
                        5500,
                        11000,
                        7800,
                        18500,
                        14000,
                        22000,
                        17200,
                    ][i % 7],
                    "num_model_requests": 70 + i * 7,
                }
            )
            buckets.append(
                {
                    "start_time": timestamp,
                    "end_time": min(timestamp + 86400, end),
                    "results": [row],
                }
            )
        return httpx.Response(200, json={"data": buckets, "has_more": False})
    if path == "/v1/responses":
        return (
            httpx.Response(200, stream=SlowSSE())
            if json.loads(req.content).get("stream")
            else httpx.Response(
                200,
                json={
                    "id": "resp_offline",
                    "status": "completed",
                    "output": [
                        {
                            "content": [
                                {"type": "output_text", "text": "Offline response"}
                            ]
                        }
                    ],
                },
            )
        )
    if path == "/v1/models":
        return httpx.Response(
            200,
            json={
                "data": [{"id": "offline-text-model"}, {"id": "offline-image-model"}]
            },
        )
    if path.endswith("/traces"):
        spans = [
            {
                "spanId": "span_root",
                "name": "Offline agent",
                "startTimeUnixNano": "1000000000",
                "endTimeUnixNano": "1005000000",
                "status": {"code": 1},
            },
            {
                "spanId": "span_child",
                "parentSpanId": "span_root",
                "name": "Offline model",
                "startTimeUnixNano": "1001000000",
                "endTimeUnixNano": "1004000000",
                "status": {"code": 1},
            },
        ]
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "trace_offline",
                        "otlp": {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]},
                    }
                ],
                "has_more": False,
            },
        )
    if path == "/v1/organization/projects":
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "proj_offline",
                        "name": "Offline workspace",
                        "status": "active",
                    }
                ],
                "has_more": False,
            },
        )
    if path.startswith("/v1/images/"):
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        return httpx.Response(200, json={"data": [{"b64_json": png}]})
    if path.endswith("/content"):
        return httpx.Response(
            200,
            content=b"offline-file",
            headers={"content-type": "application/octet-stream"},
        )
    if "/audio/transcriptions" in path:
        return httpx.Response(200, json={"text": "Offline transcription"})
    return httpx.Response(
        200,
        json={
            "data": [
                {
                    "id": "offline_1",
                    "name": "Synthetic record",
                    "status": "completed",
                    "object": "offline.fixture",
                }
            ],
            "has_more": False,
        },
    )


@asynccontextmanager
async def lifespan(app):
    """Initialize real plugin handlers with fake network transport.

    Args:
        app: Test-only FastAPI host.

    Yields:
        Running test host lifetime.
    """
    context = SimpleNamespace(registered_web_apis=[])
    context.register_web_api = lambda *args: Context.register_web_api(context, *args)
    plugin = AetherNexusPlugin(context, {})
    await plugin.client.close()
    plugin.client = PlatformClient(
        lambda kind: "synthetic-offline-" + kind,
        transport=httpx.MockTransport(fake_api),
    )
    await plugin.initialize()
    app.state.plugin = plugin
    yield
    await plugin.terminate()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/", response_class=HTMLResponse)
async def host():
    """Serve an explicit test-only parent with the production iframe sandbox.

    Returns:
        Harness HTML implementing the bridge parent protocol.
    """
    return """<!doctype html><html><body style="margin:0"><iframe id="view" title="Offline test workspace" sandbox="allow-scripts allow-forms allow-downloads" src="/view/" style="border:0;width:100%;height:100vh"></iframe><script>
const frame=document.getElementById('view'),streams=new Map();
const send=m=>frame.contentWindow.postMessage({channel:'astrbot-plugin-page',...m},'*');
window.addEventListener('message',async e=>{
 if(e.source!==frame.contentWindow||e.data?.channel!=='astrbot-plugin-page')return;
 const m=e.data;
 if(m.kind==='ready'){send({kind:'context',context:{pluginName:'astrbot_plugin_aethernexus_for_astrbot',pageName:'workspace',locale:'zh-TW',isDark:false,i18n:{}}});return;}
 if(m.kind!=='request')return;
 try{
 let data;
 if(m.action==='sse:unsubscribe'){streams.get(m.subscriptionId)?.abort();streams.delete(m.subscriptionId);data={};}
 else if(m.action==='sse:subscribe'){
 const controller=new AbortController();streams.set(m.subscriptionId,controller);
 const response=await fetch('/api/'+m.endpoint,{signal:controller.signal});if(!response.ok)throw new Error('SSE failed');
 send({kind:'response',requestId:m.requestId,ok:true,data:{}});send({kind:'sse_state',subscriptionId:m.subscriptionId,state:'open'});
 (async()=>{try{const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let end;while((end=buffer.indexOf('\\n\\n'))>=0){const raw=buffer.slice(0,end);buffer=buffer.slice(end+2);if(raw.startsWith('data: '))send({kind:'sse_message',subscriptionId:m.subscriptionId,data:raw.slice(6)});}}send({kind:'sse_state',subscriptionId:m.subscriptionId,state:'closed'});}catch(error){if(!controller.signal.aborted)send({kind:'sse_state',subscriptionId:m.subscriptionId,state:'error'});}})();return;
 }else{
 let response;
 if(m.action==='files:upload'){const form=new FormData();form.append('file',new Blob([m.fileBuffer],{type:m.fileType}),m.fileName);response=await fetch('/api/'+m.endpoint,{method:'POST',body:form});}
 else if(m.action==='files:download'){response=await fetch('/api/'+m.endpoint+'?'+new URLSearchParams(m.params||{}));if(!response.ok)throw new Error('Download failed');const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=m.filename||'download';a.click();data={filename:a.download};setTimeout(()=>URL.revokeObjectURL(url),1000);}
 else response=await fetch('/api/'+m.endpoint+(m.action==='api:get'?'?'+new URLSearchParams(m.params||{}):''),{method:m.action==='api:get'?'GET':'POST',headers:{'content-type':'application/json'},...(m.action==='api:get'?{}:{body:JSON.stringify(m.body||{})})});
 if(data===undefined){data=await response.json();if(!response.ok||data.status==='error')throw new Error(data.message||'Request failed');}
 }
 send({kind:'response',requestId:m.requestId,ok:true,data});
 }catch(error){send({kind:'response',requestId:m.requestId,ok:false,error:error.message});}
});
</script></body></html>"""


@app.get("/view/", response_class=HTMLResponse)
async def index():
    """Inject the real bridge SDK just as AstrBot does.

    Returns:
        Production view HTML with a test-local SDK path.
    """
    html = (PLUGIN_DIR / "views" / "workspace" / "index.html").read_text(
        encoding="utf-8"
    )
    return html.replace("<head>", '<head><script src="/bridge.js"></script>')


@app.get("/bridge.js")
async def bridge():
    """Return AstrBot's unmodified bridge SDK.

    Returns:
        JavaScript content from the current AstrBot checkout.
    """
    return Response(
        (ASTRBOT_DIR / "astrbot" / "dashboard" / "plugin_page_bridge.js").read_text(
            encoding="utf-8"
        ),
        media_type="application/javascript",
    )


@app.api_route("/api/{endpoint:path}", methods=["GET", "POST"])
async def dispatch(endpoint: str, request: Request):
    """Bind the real public request context around an actual plugin handler.

    Args:
        endpoint: Relative bridge endpoint.
        request: Local test request.

    Returns:
        The plugin handler response.
    """
    for route, handler, methods, _ in app.state.plugin.context.registered_web_apis:
        pattern = route.split("/", 2)[2]
        pattern = re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern)
        match = re.fullmatch(pattern, endpoint)
        if match and request.method in methods:
            with bind_request_context(
                PluginRequest(request, username="offline-tester")
            ):
                return await handler(**match.groupdict())
    return Response("Not found", status_code=404)


app.mount(
    "/view", StaticFiles(directory=PLUGIN_DIR / "views" / "workspace"), name="view"
)
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
