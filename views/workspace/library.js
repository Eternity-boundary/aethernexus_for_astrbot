/**
 * Copyright (c) 2026 Skylight Software Organization.
 * Created by EternityBoundary
 * All rights reserved.
 * SPDX-License-Identifier: GPL-3.0-only
 *
 * File: library.js
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
  confirmAction,
  toast,
} from "./ui.js";

export function libraryPage(app, migration = false) {
  const root = document.createElement("section");
  let revisions = [],
    id = "",
    version = 0;
  root.innerHTML = `<div class="page-header"><div><div class="eyebrow">BUILD / LOCAL LIBRARY</div><h1>${migration ? "Assistants migration" : "Prompts"}</h1><p>${migration ? "將既有 Assistant 匯出內容轉為本機 Prompt；不呼叫舊 Assistants API。" : "把有效的想法保存成版本，讓每一次改進都有依據。"}</p></div><div class="row">${button("new", "新增 Prompt", "plus", true)}${button("refresh", "重新整理", "refresh")}</div></div><div class="notice">本機版本庫支援每個 Prompt 100 個版本，共 100 個 Prompt。內容以明文保存於外掛資料目錄。${migration ? "僅匯入 name、model、instructions 與 input；不遷移 tools、資源或歷史對話。" : "官方可重用 Prompt 物件預定 2026-11-30 停用，本機版本庫不受影響。"}</div><div class="prompt-layout"><div class="card"><h3>Prompt library</h3><div id="list" class="prompt-list" style="margin-top:18px"></div>${field("匯入 JSON", '<input id="import" type="file" accept=".json,application/json">')}</div><div class="card stack"><div class="grid2">${field("名稱", input("name"))}${field("模型 ID", input("model", "", "自行輸入模型 ID"))}</div><div class="row"><span class="pill" id="version-label">尚未儲存</span>${select("history", [])}${button("restore", "還原此版本為草稿")}</div>${field("Developer instructions", area("instructions", "", 5))}${field("Input · 支援 {{name}}", area("input", "", 4))}<details><summary>進階 Responses 參數</summary>${area("options", "{}", 5)}</details><div class="row">${button("save", "儲存新版本", "check", true)}${button("export", "匯出 JSON", "download")}${button("delete", "刪除此 Prompt")}</div><hr style="width:100%;border:0;border-top:1px solid var(--line)"><h3>測試一次 Responses</h3><div class="grid2">${field("變數 · JSON", area("variables", "{}", 3))}${field("Project ID", input("project", "", "使用一般 Key 的預設專案"))}</div>${button("test", "執行一次測試", "play")}<small>固定 store=false。只有明確執行時才傳送內容，不自動儲存測試結果。</small><div class="output"><pre id="result">尚未執行測試</pre></div></div></div>`;
  const draft = () => ({
    id,
    version,
    name: $(root, "#name").value,
    model: $(root, "#model").value,
    instructions: $(root, "#instructions").value,
    input: $(root, "#input").value,
    options: jsonObject(root, "options"),
  });
  const fill = (r) => {
    for (const k of ["name", "model", "instructions", "input"])
      $(root, "#" + k).value = r[k] || "";
    $(root, "#options").value =
      typeof r.options === "string" ? r.options : pretty(r.options || {});
  };
  const draw = () => {
    const latest = new Map();
    revisions.forEach((r) => latest.set(r.id, r));
    $(root, "#list").innerHTML =
      [...latest.values()]
        .map(
          (r) =>
            `<button data-prompt="${escape(r.id)}" class="${r.id === id ? "active" : ""}"><strong>${escape(r.name)}</strong><small>${escape(r.model)} · v${r.version}</small></button>`,
        )
        .join("") || '<p class="muted">尚無 Prompt</p>';
    root
      .querySelectorAll("[data-prompt]")
      .forEach((b) => (b.onclick = () => open(latest.get(b.dataset.prompt))));
    const history = revisions.filter((r) => r.id === id);
    $(root, "#history").innerHTML = history
      .map(
        (r) =>
          `<option value="${r.version}">v${r.version} · ${new Date(r.modified * 1000).toLocaleDateString()}</option>`,
      )
      .join("");
    $(root, "#history").value = String(version);
    $(root, "#version-label").textContent = id
      ? `目前 v${version}`
      : "尚未儲存";
    $(root, "#delete").disabled = !id;
  };
  const open = (r) => {
    id = r.id || "";
    version = r.version || 0;
    fill(r);
    draw();
  };
  const refresh = async () => {
    revisions = (await action("prompts.list")).revisions;
    draw();
  };
  bind(root, "refresh", refresh);
  bind(root, "new", () => open({}));
  bind(root, "save", async () => {
    const res = await action("prompts.save", { body: draft() });
    revisions = res.revisions;
    open(revisions.at(-1));
    toast("新版本已儲存");
  });
  bind(root, "restore", () => {
    const old = revisions.find(
      (r) => r.id === id && r.version === Number($(root, "#history").value),
    );
    if (old) {
      fill(old);
      toast("歷史內容已放入草稿；儲存後會建立新版本");
    }
  });
  bind(root, "export", () => saveFile("prompt.json", draft()));
  bind(root, "delete", async () => {
    if (!(await confirmAction("刪除 Prompt 與所有版本", id, { id }))) return;
    revisions = (await action("prompts.delete", { id, confirm: id })).revisions;
    open({});
  });
  bind(root, "test", async () => {
    const data = await action("prompts.test", {
      body: draft(),
      variables: jsonObject(root, "variables"),
      project: $(root, "#project").value,
    });
    $(root, "#result").textContent = pretty(data);
  });
  $(root, "#import").onchange = async (event) => {
    try {
      const data = await readJson(event.target.files[0]);
      if (!data || typeof data !== "object" || Array.isArray(data))
        throw new Error("需要 Prompt 或 Assistant JSON 物件");
      id = "";
      version = 0;
      fill(data);
      draw();
      toast("已匯入為草稿，尚未儲存或執行");
    } catch (error) {
      toast(error.message, true);
    }
  };
  refresh().catch((error) => toast(error.message, true));
  return { root };
}
