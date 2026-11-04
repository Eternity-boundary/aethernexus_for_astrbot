/**
 * Copyright (c) 2026 Skylight Software Organization.
 * Created by EternityBoundary
 * All rights reserved.
 * SPDX-License-Identifier: GPL-3.0-only
 * 
 * File: builders.js
 * Project: AetherNexus for AstrBot
 */

import { action } from "./api.js";
import {
  $,
  escape,
  field,
  input,
  area,
  select,
  button,
  bind,
  pretty,
  jsonObject,
  saveFile,
  readJson,
  toast,
} from "./ui.js";

export function workflowPage() {
  const root = document.createElement("section");
  let flow = {
      version: 1,
      entry: "start",
      nodes: [
        {
          id: "start",
          kind: "start",
          name: "Start",
          next: "transform",
          x: 40,
          y: 90,
        },
        {
          id: "transform",
          kind: "transform",
          name: "Transform",
          instructions: "{{input}}",
          next: "end",
          x: 280,
          y: 90,
        },
        { id: "end", kind: "end", name: "End", x: 520, y: 90 },
      ],
    },
    selected = "start";
  root.innerHTML = `<div class="page-header"><div><div class="eyebrow">PLAYGROUND / LOCAL WORKFLOWS</div><h1>Agent Builder</h1><p>用清楚的節點，連接每一步思考。</p></div><div class="row">${button("export-json", "匯出 JSON", "download")}${button("export-python", "Agents SDK Python", "download")}</div></div><div class="notice neutral">本機工作流程不依賴官方託管 Agent Builder。條件採文字包含判斷，Transform 僅代入 {{input}}；最多執行 64 步，不執行自訂程式碼。</div><div class="split"><div class="stack"><div class="card"><div class="toolbar">${select("add-kind", ["agent", "condition", "transform", "start", "end"])}${button("add", "新增節點", "plus")}${field("匯入工作流程", '<input id="import" type="file" accept=".json">')}</div><div class="flow-board"><div class="flow-canvas" id="canvas"></div></div><small>拖曳或以方向鍵移動節點（Shift 為 10 px）。連線由右側 next／otherwise 指定。</small></div><div class="card stack"><h3>執行預覽</h3>${field("Input", area("input", "", 3))}${field("Project ID", input("project"))}${button("run", "執行工作流程", "play", true)}<pre class="output" id="trace">尚未執行</pre></div><details class="card"><summary>原始 JSON</summary>${area("raw", "", 14)}${button("apply-json", "驗證並套用 JSON")}</details></div><aside class="card params"><h3>Node properties</h3>${field("ID", input("node-id"))}${field("名稱", input("node-name"))}${field("類型", select("node-kind", ["start", "agent", "condition", "transform", "end"]))}${field("模型 ID（Agent）", input("node-model"))}${field("Instructions / Transform", area("node-instructions", "", 5))}${field("包含文字（Condition）", input("node-match"))}${field("Next", select("node-next", []))}${field("Otherwise", select("node-otherwise", []))}${button("save-node", "套用節點", "check", true)}${button("delete-node", "移除節點")}</aside></div>`;
  const loadNode = () => {
    const n = flow.nodes.find((n) => n.id === selected);
    if (!n) return;
    for (const k of ["id", "name", "kind", "model", "instructions", "match"])
      $(root, "#node-" + k).value = n[k] || "";
    for (const k of ["next", "otherwise"]) {
      $(root, "#node-" + k).innerHTML =
        '<option value="">—</option>' +
        flow.nodes
          .map(
            (x) =>
              `<option value="${escape(x.id)}">${escape(x.name || x.id)} · ${escape(x.id)}</option>`,
          )
          .join("");
      $(root, "#node-" + k).value = n[k] || "";
    }
  };
  const draw = () => {
    const lines = flow.nodes
      .flatMap((n) =>
        ["next", "otherwise"]
          .filter((k) => n[k])
          .map((k) => {
            const dest = flow.nodes.find((x) => x.id === n[k]);
            return dest
              ? `<path d="M${(n.x || 0) + 166},${(n.y || 0) + 35} C${(n.x || 0) + 205},${(n.y || 0) + 35} ${(dest.x || 0) - 35},${(dest.y || 0) + 35} ${dest.x || 0},${(dest.y || 0) + 35}" fill="none" stroke="${k === "otherwise" ? "var(--orange)" : "var(--accent)"}" stroke-width="1.6" ${k === "otherwise" ? 'stroke-dasharray="5 4"' : ""}/>`
              : "";
          }),
      )
      .join("");
    $(root, "#canvas").innerHTML =
      `<svg class="flow-lines">${lines}</svg>` +
      flow.nodes
        .map(
          (n) =>
            `<div class="flow-node ${n.id === selected ? "selected" : ""}" data-node="${escape(n.id)}" data-kind="${escape(n.kind)}" tabindex="0" role="button" aria-label="${escape(n.name || n.id)}，可拖曳或使用方向鍵移動" style="left:${Number(n.x) || 0}px;top:${Number(n.y) || 0}px"><strong>${escape(n.name || n.id)}</strong><small>${escape(n.kind)} · ${escape(n.id)}</small></div>`,
        )
        .join("");
    $(root, "#raw").value = pretty(flow);
    root.querySelectorAll("[data-node]").forEach((el) => {
      el.onclick = () => {
        selected = el.dataset.node;
        root
          .querySelectorAll("[data-node]")
          .forEach((x) => x.classList.toggle("selected", x === el));
        loadNode();
      };
      el.onkeydown = (e) => {
        if (
          !["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key)
        )
          return;
        e.preventDefault();
        const n = flow.nodes.find((n) => n.id === el.dataset.node),
          step = e.shiftKey ? 10 : 1;
        n.x = Math.max(
          0,
          Math.min(
            9800,
            (n.x || 0) +
              (e.key === "ArrowRight"
                ? step
                : e.key === "ArrowLeft"
                  ? -step
                  : 0),
          ),
        );
        n.y = Math.max(
          0,
          Math.min(
            9800,
            (n.y || 0) +
              (e.key === "ArrowDown" ? step : e.key === "ArrowUp" ? -step : 0),
          ),
        );
        selected = n.id;
        draw();
        root.querySelector(`[data-node="${CSS.escape(n.id)}"]`).focus();
      };
      el.onpointerdown = (e) => {
        if (e.button !== 0) return;
        const n = flow.nodes.find((n) => n.id === el.dataset.node),
          sx = e.clientX,
          sy = e.clientY,
          nx = n.x || 0,
          ny = n.y || 0;
        el.setPointerCapture(e.pointerId);
        selected = n.id;
        loadNode();
        el.onpointermove = (event) => {
          n.x = Math.max(0, Math.min(9800, nx + event.clientX - sx));
          n.y = Math.max(0, Math.min(9800, ny + event.clientY - sy));
          el.style.left = n.x + "px";
          el.style.top = n.y + "px";
        };
        el.onpointerup = () => {
          el.onpointermove = null;
          draw();
        };
      };
    });
  };
  draw();
  loadNode();
  bind(root, "add", () => {
    if (flow.nodes.length >= 100) throw new Error("最多 100 個節點");
    const kind = $(root, "#add-kind").value,
      id = "node_" + crypto.randomUUID().slice(0, 8);
    flow.nodes.push({
      id,
      kind,
      name: kind,
      model: "",
      instructions: kind === "transform" ? "{{input}}" : "",
      next: flow.nodes.find((n) => n.kind === "end")?.id || "",
      otherwise: flow.nodes.find((n) => n.kind === "end")?.id || "",
      x: 80 + (flow.nodes.length % 3) * 200,
      y: 190 + Math.floor(flow.nodes.length / 3) * 90,
    });
    selected = id;
    draw();
    loadNode();
  });
  bind(root, "save-node", () => {
    const n = flow.nodes.find((n) => n.id === selected),
      old = n.id,
      newId = $(root, "#node-id").value.trim();
    if (
      !/^[A-Za-z0-9_-]{1,128}$/.test(newId) ||
      flow.nodes.some((x) => x !== n && x.id === newId)
    )
      throw new Error("ID 需要唯一英數字、_ 或 -");
    for (const k of [
      "id",
      "name",
      "kind",
      "model",
      "instructions",
      "match",
      "next",
      "otherwise",
    ])
      n[k] = $(root, "#node-" + k).value;
    if (old !== newId) {
      for (const node of flow.nodes)
        for (const k of ["next", "otherwise"])
          if (node[k] === old) node[k] = newId;
      if (flow.entry === old) flow.entry = newId;
    }
    selected = newId;
    draw();
    loadNode();
    toast("節點已更新，執行前會驗證完整圖形");
  });
  bind(root, "delete-node", () => {
    flow.nodes = flow.nodes.filter((n) => n.id !== selected);
    selected = flow.nodes[0]?.id || "";
    draw();
    loadNode();
  });
  bind(root, "export-json", async () => {
    await action("workflow.export", { body: flow });
    saveFile("workflow.json", flow);
  });
  bind(root, "export-python", async () => {
    const result = await action("workflow.export", { body: flow });
    saveFile("workflow.py", result.code, "text/x-python");
  });
  bind(root, "apply-json", async () => {
    const next = jsonObject(root, "raw");
    await action("workflow.export", { body: next });
    flow = next;
    selected = flow.entry;
    draw();
    loadNode();
  });
  bind(root, "run", async () => {
    $(root, "#trace").textContent = pretty(
      await action("workflow.run", {
        body: flow,
        input: $(root, "#input").value,
        project: $(root, "#project").value,
      }),
    );
  });
  $(root, "#import").onchange = async (e) => {
    try {
      const next = await readJson(e.target.files[0]);
      await action("workflow.export", { body: next });
      flow = next;
      selected = flow.entry;
      draw();
      loadNode();
      toast("工作流程已匯入，尚未執行");
    } catch (error) {
      toast(error.message, true);
    }
  };
  return { root };
}

export function videoPage() {
  const root = document.createElement("section");
  let videoUrl = "";
  root.innerHTML = `<div class="page-header"><div><div class="eyebrow">PLAYGROUND / STORYBOARD</div><h1>Video</h1><p>保留你的分鏡，繼續下一段創作。</p></div>${button("export", "匯出分鏡", "download")}</div><div class="notice warning">Videos API 已停用。本頁只提供本機分鏡與既有影片預覽，不發起影片生成。 <a href="https://developers.openai.com/api/docs/deprecations" target="_blank" rel="noopener noreferrer">遷移指南 ↗</a></div><div class="grid2"><div class="card stack"><h2>Storyboard</h2>${field("分鏡 JSON", area("board", pretty({ version: 1, shots: [{ prompt: "", seconds: 5 }] }), 14))}${button("add", "加入分鏡", "plus")}${field("匯入分鏡", '<input id="import" type="file" accept=".json">')}</div><div class="card stack"><h2>本機影片預覽</h2>${field("選擇既有影片", '<input id="video" type="file" accept="video/*">')}<video id="player" controls></video><small>影片只在瀏覽器預覽，不會上傳到伺服器。</small></div></div>`;
  bind(root, "add", () => {
    const board = jsonObject(root, "board");
    if (!Array.isArray(board.shots)) throw new Error("需要 shots 陣列");
    board.shots.push({ prompt: "", seconds: 5 });
    $(root, "#board").value = pretty(board);
  });
  bind(root, "export", async () => {
    const board = await action("storyboard.validate", {
      body: jsonObject(root, "board"),
    });
    saveFile("storyboard.json", board);
  });
  $(root, "#import").onchange = async (e) => {
    try {
      const data = await readJson(e.target.files[0]);
      await action("storyboard.validate", { body: data });
      $(root, "#board").value = pretty(data);
    } catch (error) {
      toast(error.message, true);
    }
  };
  $(root, "#video").onchange = (e) => {
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    const file = e.target.files[0];
    videoUrl = file ? URL.createObjectURL(file) : "";
    $(root, "#player").src = videoUrl;
  };
  return {
    root,
    leave: () => $(root, "#player").pause(),
    dispose: () => {
      if (videoUrl) URL.revokeObjectURL(videoUrl);
    },
  };
}
