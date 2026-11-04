/**
 * Copyright (c) 2026 Skylight Software Organization.
 * Created by EternityBoundary
 * All rights reserved.
 * SPDX-License-Identifier: GPL-3.0-only
 * 
 * File: resources.js
 * Project: AetherNexus for AstrBot
 */

import { action, bridge, upload } from "./api.js";
import {
  $,
  escape,
  icon,
  field,
  input,
  area,
  button,
  select,
  bind,
  pretty,
  jsonObject,
  saveFile,
  confirmAction,
  showSecret,
  toast,
  readJson,
} from "./ui.js";

export function resourcePage(app, group) {
  const root = document.createElement("section"),
    operations = app.catalog.operations.filter((o) => o.group === group);
  let selected = operations[0],
    result = null,
    records = [],
    chosen = null,
    cursor = "",
    revision = 0;
  root.innerHTML = `<div class="page-header"><div><div class="eyebrow">${["projects", "api-keys"].includes(group) ? "MANAGE" : "BUILD"} / WORKSPACE</div><h1>${escape(app.titles[group])}</h1><p>${escape(app.descriptions[group])}</p></div>${button("export", "匯出 JSON", "download")}</div>${["evaluations", "fine-tuning"].includes(group) ? `<div class="notice warning">${group === "evaluations" ? "Evals 為唯讀，2026-11-30 起停止遠端查詢；仍可開啟本機 JSON 匯出。" : "2027-01-06 起停止建立新訓練工作；目前建立資格與模型支援由伺服器判定。"} <a href="https://developers.openai.com/api/docs/deprecations" target="_blank" rel="noopener noreferrer">遷移指南 ↗</a></div>` : ""}<div class="resource-layout"><div class="card"><h3 style="margin-bottom:14px">操作</h3><div class="operation-list">${operations.map((o) => `<button data-action="${o.action}">${escape(o.label)}</button>`).join("")}</div></div><div class="stack"><div class="card"><div class="card-heading"><h2 id="operation-title"></h2><span class="pill" id="key-type"></span></div><div class="grid2" id="ids"></div><div id="body-wrap" style="margin-top:16px">${field("請求內容 · JSON", area("body", "{}", 5))}</div><details style="margin-top:16px"><summary class="muted">分頁與篩選參數</summary><div class="grid2" style="margin-top:14px">${field("一般 Key 專案範圍", input("scope", "", "留空使用金鑰預設專案"))}${field("Query · JSON", area("query", '{"limit": 20}', 3))}</div></details><div class="row" style="margin-top:18px">${button("execute", "執行查詢", "play", true)}${button("more", "載入更多", "plus")}<small id="result-status">尚未載入資料</small></div></div><div class="card"><div class="card-heading"><h2>結果</h2>${input("search", "", "搜尋已載入的項目")}</div><div id="table" class="table-wrap"><div class="empty">${icon(group)}<p>選擇操作後明確執行。不會自動查詢或更改帳戶。</p></div></div><details style="margin-top:18px" open><summary class="muted">選定項目／完整回應 JSON</summary><div class="output"><pre id="details">—</pre></div></details></div>${group === "storage" ? `<div class="card"><h3>上傳至 Files</h3><div class="toolbar" style="margin-top:16px">${field("檔案 · 最大 25 MiB", '<input id="file" type="file">')}${field("用途", select("purpose", ["user_data", "batch", "fine-tune", "assistants", "vision", "evals"]))}${button("upload", "上傳選定檔案", "plus", true)}</div></div>` : ""}${["storage", "batches", "fine-tuning"].includes(group) ? `<div class="card"><div class="toolbar">${field("下載 Files 內容", input("download-id", "", "輸入 file ID，例如 output_file_id"))}${button("download", "下載", "download")}</div><small>本移植版單次下載上限為 40 MiB。只接受 Files ID。</small></div>` : ""}${group === "evaluations" ? `<div class="card">${field("開啟既有本機 JSON", '<input type="file" id="local-eval" accept=".json,application/json">')}</div>` : ""}</div></div>`;
  if (group === "traces")
    $(root, "#details").parentElement.insertAdjacentHTML(
      "beforebegin",
      '<div id="span-tree" class="table-wrap"></div>',
    );
  const invalidate = () => {
    revision += 1;
    result = null;
    records = [];
    chosen = null;
    cursor = "";
    $(root, "#more").disabled = true;
    $(root, "#export").disabled = true;
    $(root, "#details").textContent = "資料範圍已變更，請執行查詢。";
    $(root, "#table").innerHTML = "";
    if (group === "traces") $(root, "#span-tree").innerHTML = "";
    $(root, "#result-status").textContent = "尚未套用";
  };
  const drawTable = () => {
    const search = $(root, "#search").value.toLowerCase(),
      filtered = records.filter((r) =>
        pretty(r).toLowerCase().includes(search),
      );
    const keys = [
      "id",
      "name",
      "model",
      "status",
      "object",
      "role",
      "hint",
      "created_at",
      "filename",
    ]
      .filter((k) => filtered.some((r) => r[k] != null))
      .slice(0, 6);
    $(root, "#table").innerHTML = filtered.length
      ? `<table><thead><tr>${keys.map((k) => `<th>${k}</th>`).join("")}</tr></thead><tbody>${filtered.map((r, i) => `<tr data-record="${i}" tabindex="0">${keys.map((k) => `<td>${escape(typeof r[k] === "object" ? pretty(r[k]) : (r[k] ?? "—"))}</td>`).join("")}</tr>`).join("")}</tbody></table>`
      : '<div class="empty"><p>沒有符合的項目</p></div>';
    root.querySelectorAll("[data-record]").forEach((row) => {
      const choose = () => {
        chosen = filtered[Number(row.dataset.record)];
        $(root, "#details").textContent = pretty(chosen);
        if (group === "traces") {
          const spans = (chosen.otlp?.resourceSpans || [])
            .flatMap((r) => (r.scopeSpans || []).flatMap((s) => s.spans || []))
            .slice(0, 1000);
          const byId = new Map(spans.map((s) => [s.spanId, s]));
          $(root, "#span-tree").innerHTML = spans.length
            ? `<table><thead><tr><th>Span hierarchy</th><th>Duration</th><th>Status</th></tr></thead><tbody>${spans
                .map((s, i) => {
                  let depth = 0,
                    parent = s.parentSpanId;
                  const seen = new Set([s.spanId]);
                  while (byId.has(parent) && !seen.has(parent) && depth < 32) {
                    seen.add(parent);
                    depth++;
                    parent = byId.get(parent).parentSpanId;
                  }
                  let duration = "—";
                  if (
                    /^\d+$/.test(s.startTimeUnixNano) &&
                    /^\d+$/.test(s.endTimeUnixNano)
                  ) {
                    const ns =
                      BigInt(s.endTimeUnixNano) - BigInt(s.startTimeUnixNano);
                    if (ns >= 0)
                      duration = (Number(ns) / 1e6).toFixed(2) + " ms";
                  }
                  return `<tr data-span="${i}" tabindex="0"><td style="padding-left:${12 + depth * 16}px">${escape(s.name || s.spanId)}</td><td>${duration}</td><td>${escape(s.status?.message || s.status?.code || "—")}</td></tr>`;
                })
                .join("")}</tbody></table>`
            : '<p class="muted">此項目沒有 OTLP spans。</p>';
          root.querySelectorAll("[data-span]").forEach((el) => {
            const inspect = () =>
              ($(root, "#details").textContent = pretty(
                spans[Number(el.dataset.span)],
              ));
            el.onclick = inspect;
            el.onkeydown = (e) => {
              if (e.key === "Enter") inspect();
            };
          });
        }
        const id = $(root, "#id");
        if (id && chosen.id) id.value = chosen.id;
      };
      row.onclick = choose;
      row.onkeydown = (e) => {
        if (e.key === "Enter") choose();
      };
    });
  };
  const chooseOperation = (o) => {
    selected = o;
    invalidate();
    $(root, "#operation-title").textContent = o.label;
    $(root, "#key-type").textContent = o.admin ? "Admin Key" : "一般 API Key";
    root
      .querySelectorAll("[data-action]")
      .forEach((b) =>
        b.classList.toggle("active", b.dataset.action === o.action),
      );
    $(root, "#ids").innerHTML = o.fields
      .map((k) =>
        field(
          k === "project"
            ? "管理目標 Project ID"
            : k === "parent"
              ? "上層 ID（Eval／向量庫）"
              : "目標 ID",
          input(k),
        ),
      )
      .join("");
    $(root, "#body-wrap").hidden = o.method !== "POST";
    $(root, "#body").value = pretty(o.example);
    $(root, "#query").value =
      o.method === "GET" && !o.action.endsWith(".get") ? '{"limit": 20}' : "{}";
    if (o.action === "traces.session") $(root, "#query").value = '{"limit": 5}';
    $(root, "#execute").innerHTML =
      icon(o.method === "GET" ? "refresh" : "play") +
      (o.method === "GET" ? "執行查詢" : "核對並執行");
    root
      .querySelectorAll("#ids input")
      .forEach((i) => (i.onchange = invalidate));
  };
  root
    .querySelectorAll("[data-action]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          chooseOperation(
            operations.find((o) => o.action === b.dataset.action),
          )),
    );
  chooseOperation(selected);
  const execute = async (more = false) => {
    const operation = selected;
    const requestRevision = revision;
    const payload = {
      scope: $(root, "#scope").value,
      query: jsonObject(root, "query"),
      body: operation.method === "POST" ? jsonObject(root, "body") : {},
    };
    for (const k of operation.fields)
      payload[k] = $(root, "#" + k).value.trim();
    if (more && cursor) payload.query.after = cursor;
    if (operation.method !== "GET") {
      const target = payload.id || payload.project || operation.action;
      if (!(await confirmAction(operation.label, target, payload))) return;
      payload.confirm = target;
    }
    if (requestRevision !== revision) return;
    const data = await action(operation.action, payload);
    if (data.one_time_key) {
      const secret = data.one_time_key;
      delete data.one_time_key;
      showSecret(secret);
      result = null;
      chosen = null;
      $(root, "#details").textContent =
        "權杖已簽發。完整值只顯示於一次性視窗。";
      return;
    }
    if (requestRevision !== revision) return;
    result = data;
    chosen = null;
    records = more
      ? [...records, ...(data.data || [])]
      : Array.isArray(data.data)
        ? data.data
        : [];
    cursor = data.has_more
      ? data.last_id || data.next_page || data.data?.at(-1)?.id || ""
      : "";
    $(root, "#more").disabled = !cursor || operation.method !== "GET";
    $(root, "#export").disabled = false;
    $(root, "#details").textContent = pretty(data);
    $(root, "#result-status").textContent = records.length
      ? `已載入 ${records.length} 筆`
      : "操作完成";
    drawTable();
  };
  bind(root, "execute", () => execute(false));
  bind(root, "more", () => execute(true));
  $(root, "#search").oninput = drawTable;
  $(root, "#scope").onchange = invalidate;
  $(root, "#query").onchange = invalidate;
  bind(root, "export", () => {
    if (result)
      saveFile(
        `${group}.json`,
        chosen || { ...result, ...(records.length ? { data: records } : {}) },
      );
  });
  if (group === "storage")
    bind(root, "upload", async () => {
      const data = await upload("files", $(root, "#file").files[0], {
        purpose: $(root, "#purpose").value,
        project: $(root, "#scope").value,
      });
      $(root, "#details").textContent = pretty(data);
      toast("檔案已上傳，請重新整理 Files");
    });
  if (["storage", "batches", "fine-tuning"].includes(group))
    bind(root, "download", () =>
      bridge.download(
        "download",
        {
          id: $(root, "#download-id").value.trim(),
          project: $(root, "#scope").value,
        },
        "file.bin",
      ),
    );
  if (group === "evaluations")
    $(root, "#local-eval").onchange = async (e) => {
      try {
        result = await readJson(e.target.files[0]);
        records = Array.isArray(result.data) ? result.data : [];
        chosen = null;
        $(root, "#details").textContent = pretty(result);
        $(root, "#export").disabled = false;
        drawTable();
      } catch (error) {
        toast(error.message, true);
      }
    };
  return { root };
}
