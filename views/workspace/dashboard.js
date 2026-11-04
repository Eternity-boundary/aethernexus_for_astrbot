/**
 * Copyright (c) 2026 Skylight Software Organization.
 * Created by EternityBoundary
 * All rights reserved.
 * SPDX-License-Identifier: GPL-3.0-only
 *
 * File: dashboard.js
 * Project: AetherNexus for AstrBot
 */

import { action, bridge } from "./api.js";
import {
  $,
  escape,
  icon,
  field,
  input,
  select,
  button,
  bind,
  number,
  pretty,
  utcRange,
  toast,
} from "./ui.js";

export function chart(buckets, metrics, mini = false) {
  const w = 660,
    h = mini ? 70 : 220,
    pad = mini ? 0 : 24;
  const series = metrics.map(([key, color]) => ({
    key,
    color,
    points: buckets.map((bucket) => {
      const values = bucket.results.map((r) =>
        key === "amount_usd" ? r.amount?.value : r[key],
      );
      return {
        time: bucket.start_time,
        value:
          values.length &&
          values.every((v) => v != null && Number.isFinite(Number(v)))
            ? values.reduce((a, b) => a + Number(b), 0)
            : bucket.results.length === 0
              ? 0
              : null,
      };
    }),
  }));
  const values = series.flatMap((s) =>
    s.points.map((p) => p.value).filter((v) => v !== null),
  );
  const lo = Math.min(0, ...values),
    hi = Math.max(1, ...values),
    y = (v) => h - pad - ((v - lo) / (hi - lo)) * (h - pad * 2);
  const xs = [...new Set(buckets.map((b) => b.start_time))].sort(
      (a, b) => a - b,
    ),
    x = (t) =>
      pad +
      (xs.length > 1 ? (t - xs[0]) / (xs.at(-1) - xs[0]) : 0.5) * (w - 2 * pad);
  const grid = mini
    ? ""
    : [0, 0.5, 1]
        .map(
          (f) =>
            `<line x1="${pad}" x2="${w - pad}" y1="${pad + f * (h - 2 * pad)}" y2="${pad + f * (h - 2 * pad)}" stroke="var(--line)" stroke-dasharray="3 5"/><text x="${pad}" y="${pad + f * (h - 2 * pad) - 6}">${number(hi - f * (hi - lo))}</text>`,
        )
        .join("");
  const lines = series
    .map((s) => {
      const segments = [];
      let active = [];
      for (const point of s.points) {
        if (point.value === null) {
          if (active.length) segments.push(active);
          active = [];
        } else active.push(point);
      }
      if (active.length) segments.push(active);
      return segments
        .map(
          (points) =>
            `<polyline fill="none" stroke="${s.color}" stroke-width="${mini ? 2 : 2.5}" stroke-linecap="round" stroke-linejoin="round" points="${points.map((p) => `${x(p.time)},${y(p.value)}`).join(" ")}"/>${points.length === 1 ? `<circle cx="${x(points[0].time)}" cy="${y(points[0].value)}" r="3" fill="${s.color}"/>` : ""}`,
        )
        .join("");
    })
    .join("");
  const labels =
    mini || !xs.length
      ? ""
      : [xs[0], xs[Math.floor(xs.length / 2)], xs.at(-1)]
          .map(
            (t, i) =>
              `<text x="${x(t)}" y="${h - 3}" text-anchor="${i === 0 ? "start" : i === 2 ? "end" : "middle"}">${new Date(t * 1000).toISOString().slice(5, 10)}</text>`,
          )
          .join("");
  return `<svg class="${mini ? "spark" : "chart"}" role="img" aria-label="UTC 每日趨勢圖" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${grid}${lines}${labels}</svg>`;
}

export function dashboardPage(app) {
  let revision = 0;
  let syncTimer = null,
    syncing = false,
    commandRefresh = "",
    displayedAt = "";
  const root = document.createElement("section"),
    range = utcRange();
  root.innerHTML = `<div class="page-header"><div><div class="eyebrow">YOUR WORKSPACE AT A GLANCE</div><h1>Dashboard</h1><p>每一份用量，都有跡可循。</p></div><span class="pill">UTC 時區</span></div>
    <div class="toolbar">${field("開始日期", '<input type="date" id="start" value="' + range.start + '">')}${field("結束日期", '<input type="date" id="end" value="' + range.end + '">')}${field("專案範圍", select("project", [["", "所有專案"]]))}${button("projects-load", "取得專案", "projects")}${button("load", "載入用量", "refresh", true)}</div>
    <div class="notice neutral" id="scope-note">使用 Admin Key 讀取組織用量。尚未發起遠端查詢；成本為本月累計，與 Token 日期範圍獨立。</div>
    <div class="metric-grid" id="metrics"></div><div class="grid2"><div class="card"><div class="card-heading"><h2>Token usage</h2><small id="chart-range">每日用量 · UTC</small></div><div class="legend"><span><i style="background:var(--orange)"></i>Input</span><span><i style="background:var(--pink)"></i>Output</span><span><i style="background:var(--accent)"></i>Cached input</span></div><div class="chart-wrap" id="token-chart"></div></div><div class="card"><div class="card-heading"><h2>Cost overview</h2><small>本月累計 · USD</small></div><div id="cost-chart" class="chart-wrap"></div><p class="muted" id="budget-note" style="font-size:11px">成本取自 Costs API，並非帳戶餘額。</p></div></div>
    <div class="card-heading" style="margin:28px 0 0"><h2>繼續探索</h2><small>從想法到實作</small></div><div class="quick-grid">${[
      ["chat", "Playground", "測試模型，讓想法成形"],
      ["prompts", "Prompt library", "建立可重用的提示詞版本"],
      ["agent-builder", "Agent Builder", "以節點串起你的工作流程"],
    ]
      .map(
        ([id, title, subtitle]) =>
          `<button class="quick" data-go="${id}">${icon(id)}<span><strong>${title}</strong><small>${subtitle}</small></span>${icon("arrow")}</button>`,
      )
      .join("")}</div>`;
  $(root, "#token-chart").insertAdjacentHTML(
    "afterend",
    '<p class="muted" id="activity-summary" style="font-size:11px"></p>',
  );
  const render = (result) => {
    if (result?.refreshed_at) displayedAt = result.refreshed_at;
    const usage = result?.usage,
      costs = result?.costs,
      t = usage?.totals || {},
      c = costs?.totals || {};
    const tiles = [
      [
        "Input tokens",
        t.input_tokens,
        "含快取，不重複相加",
        "prompts",
        "var(--orange)",
        "input_tokens",
      ],
      [
        "Output tokens",
        t.output_tokens,
        "Completions 用量",
        "chat",
        "var(--pink)",
        "output_tokens",
      ],
      [
        "Cached input",
        usage?.cache_percent == null
          ? null
          : `${usage.cache_percent.toFixed(1)}%`,
        "依輸入 Token 加權",
        "batches",
        "var(--accent)",
        "input_cached_tokens",
      ],
      [
        "Monthly cost",
        c.amount_usd == null ? null : `$${number(c.amount_usd)}`,
        "所選專案的本月全部成本",
        "usage",
        "var(--teal)",
        "amount_usd",
      ],
    ];
    $(root, "#metrics").innerHTML = tiles
      .map(
        ([label, value, hint, symbol, color, metric]) =>
          `<div class="card metric-card"><div class="metric-label">${label}<span class="metric-symbol" style="color:${color}">${icon(symbol)}</span></div><div class="metric-value">${typeof value === "string" ? value : number(value)}</div><div class="metric-sub">${hint}</div>${chart((metric === "amount_usd" ? costs : usage)?.buckets || [], [[metric, color]], true)}</div>`,
      )
      .join("");
    $(root, "#token-chart").innerHTML = usage?.buckets?.length
      ? chart(usage.buckets, [
          ["input_tokens", "var(--orange)"],
          ["output_tokens", "var(--pink)"],
          ["input_cached_tokens", "var(--accent)"],
        ])
      : `<div class="empty">${icon("usage")}<p>${escape(usage?.error || (usage ? "此範圍沒有用量" : "載入用量後顯示每日趨勢"))}</p></div>`;
    $(root, "#cost-chart").innerHTML = costs?.buckets?.length
      ? chart(costs.buckets, [["amount_usd", "var(--teal)"]])
      : `<div class="empty">${icon("projects")}<p>${escape(costs?.error || (costs ? "本月沒有成本項目" : "本月成本尚未載入"))}</p></div>`;
    const total =
      t.input_tokens == null || t.output_tokens == null
        ? null
        : t.input_tokens + t.output_tokens;
    $(root, "#activity-summary").textContent =
      `Requests ${number(t.num_model_requests)} · Total tokens ${number(total)}`;
    const budget = result?.settings?.monthly_usd_cents;
    $(root, "#budget-note").textContent = budget
      ? `本機參考預算 $${number(budget / 100)} · ${c.amount_usd == null ? "成本未取得" : "已使用 " + ((c.amount_usd / (budget / 100)) * 100).toFixed(1) + "%"}。此值不會更改 OpenAI 額度。`
      : "成本取自 Costs API，並非帳戶餘額。";
    if (Array.isArray(result?.projects?.data)) {
      const selected = $(root, "#project").value;
      const projects = result.projects.data;
      $(root, "#project").innerHTML =
        '<option value="">所有專案</option>' +
        projects
          .map(
            (p) =>
              `<option value="${escape(p.id)}">${escape(p.name || p.id)}${p.status === "archived" ? "（已封存）" : ""}</option>`,
          )
          .join("");
      if (selected && !projects.some((p) => p.id === selected))
        $(root, "#project").insertAdjacentHTML(
          "beforeend",
          `<option value="${escape(selected)}">${escape(selected)}（未列出）</option>`,
        );
      $(root, "#project").value = selected;
    }
  };
  render();
  bind(root, "projects-load", async () => {
    let after = "";
    const projects = [];
    const seen = new Set();
    do {
      const res = await action("projects.list", {
        query: { limit: 100, ...(after ? { after } : {}) },
      });
      projects.push(...res.data);
      after = res.has_more ? res.last_id || res.data.at(-1)?.id : "";
      if (seen.has(after)) throw new Error("專案游標重複");
      seen.add(after);
      if (seen.size > 1000) throw new Error("專案分頁超過限制");
    } while (after);
    const selected = $(root, "#project").value;
    $(root, "#project").innerHTML =
      `<option value="">所有專案</option>` +
      projects
        .map(
          (p) =>
            `<option value="${escape(p.id)}">${escape(p.name || p.id)}${p.status === "archived" ? "（已封存）" : ""}</option>`,
        )
        .join("");
    if (selected && !projects.some((p) => p.id === selected))
      $(root, "#project").insertAdjacentHTML(
        "beforeend",
        `<option value="${escape(selected)}">${escape(selected)}（未列出）</option>`,
      );
    $(root, "#project").value = selected;
  });
  bind(root, "load", async () => {
    const requestRevision = revision;
    const result = await action("dashboard", {
      start: $(root, "#start").value,
      end: $(root, "#end").value,
      project: $(root, "#project").value,
    });
    if (requestRevision !== revision) return;
    render(result);
    $(root, "#scope-note").textContent =
      `已載入 ${$(root, "#project").selectedOptions[0]?.textContent} · ${$(root, "#start").value} 至 ${$(root, "#end").value}（UTC）。成本為本月累計。${result.projects?.error ? " 專案清單載入失敗：" + result.projects.error : ""}`;
  });
  root
    .querySelectorAll("[data-go]")
    .forEach((el) => (el.onclick = () => app.navigate(el.dataset.go)));
  for (const name of ["start", "end", "project"])
    $(root, "#" + name).onchange = () => {
      revision += 1;
      render();
      $(root, "#scope-note").textContent = "範圍已變更，請按「載入用量」套用。";
    };
  const syncCommand = async () => {
    if (syncing || !root.isConnected) return;
    syncing = true;
    const requestRevision = revision;
    try {
      // This reads an existing in-memory report; it never refreshes remote APIs.
      const { report } = await action("dashboard.latest");
      if (
        !root.isConnected ||
        requestRevision !== revision ||
        !report ||
        report.refreshed_at === commandRefresh
      )
        return;
      commandRefresh = report.refreshed_at;
      if (report.refreshed_at <= displayedAt) return;
      const query = report.range;
      if (
        query.start !== $(root, "#start").value ||
        query.end !== $(root, "#end").value ||
        query.project !== $(root, "#project").value
      ) {
        $(root, "#scope-note").textContent =
          "/用量 已重新整理所有專案近 7 天的資料；目前篩選範圍不同，請按「載入用量」取得目前範圍。";
        return;
      }
      render(report);
      $(root, "#scope-note").textContent =
        `已載入 /用量 最新報告 · ${query.start} 至 ${query.end}（UTC）· ${report.refreshed_at}${report.projects?.error ? " 專案清單載入失敗：" + report.projects.error : ""}`;
    } catch {
      // A view reload can temporarily disconnect the local bridge.
    } finally {
      syncing = false;
    }
  };
  return {
    root,
    enter() {
      syncCommand();
      syncTimer ??= setInterval(syncCommand, 5000);
    },
    leave() {
      clearInterval(syncTimer);
      syncTimer = null;
    },
  };
}

export function usagePage() {
  const root = document.createElement("section"),
    dates = utcRange(30);
  let report, applied;
  let revision = 0;
  root.innerHTML = `<div class="page-header"><div><div class="eyebrow">MANAGE / ANALYTICS</div><h1>Usage</h1><p>公開 Usage API 的完整分頁與分類檢視。</p></div></div><div class="toolbar">${field("開始 · UTC", '<input id="start" type="date" value="' + dates.start + '">')}${field("結束 · UTC", '<input id="end" type="date" value="' + dates.end + '">')}${field("Project ID", input("project", "", "留空為所有專案"))}${field("分類", select("category", ["completions", "costs", "embeddings", "images", "audio_speeches", "audio_transcriptions", "moderations", "vector_stores", "code_interpreter_sessions", "file_search_calls", "web_search_calls"]))}${field("分組", select("group", ["", "project_id", "model", "api_key_id", "user_id"]))}${button("load", "套用／重新整理", "refresh", true)}</div><div class="notice neutral">UTC 每日桶，範圍最多 366 日。vector_stores 的每日儲存量不跨日相加。資料缺失顯示「—」。</div><div class="card"><div class="card-heading"><h2>用量報告</h2><div class="row">${select("metric", [])}${button("csv", "匯出 CSV", "download")}</div></div><div id="chart" class="chart-wrap"><div class="empty">載入報告後顯示趨勢</div></div><div id="totals" class="muted"></div><div class="output"><pre id="report">尚未載入資料</pre></div></div>`;
  $(root, "#report").parentElement.insertAdjacentHTML(
    "afterbegin",
    input("search-report", "", "搜尋已載入的報告明細"),
  );
  $(root, "#search-report").oninput = () => {
    if (!report) return;
    const term = $(root, "#search-report").value.toLowerCase();
    $(root, "#report").textContent = pretty(
      report.rows.filter((row) => pretty(row).toLowerCase().includes(term)),
    );
  };
  const params = () =>
    Object.fromEntries(
      ["start", "end", "project", "category", "group"].map((k) => [
        k,
        $(root, "#" + k).value,
      ]),
    );
  const invalidate = () => {
    revision += 1;
    report = null;
    $(root, "#csv").disabled = true;
    $(root, "#report").textContent = "範圍已變更，請重新整理。";
    $(root, "#chart").innerHTML = "";
    $(root, "#totals").textContent = "";
  };
  invalidate();
  ["start", "end", "project", "category", "group"].forEach((k) =>
    $(root, "#" + k).addEventListener("change", invalidate),
  );
  $(root, "#category").addEventListener("change", () => {
    const c = $(root, "#category").value;
    const groups =
      c === "costs"
        ? ["", "project_id", "line_item", "api_key_id", "api_source"]
        : ["vector_stores", "code_interpreter_sessions"].includes(c)
          ? ["", "project_id"]
          : c === "file_search_calls"
            ? ["", "project_id", "api_key_id", "user_id", "vector_store_id"]
            : ["", "project_id", "model", "api_key_id", "user_id"];
    $(root, "#group").innerHTML = groups
      .map((g) => `<option>${g}</option>`)
      .join("");
  });
  const draw = () => {
    if (!report) return;
    const metric = $(root, "#metric").value;
    $(root, "#chart").innerHTML = chart(report.buckets, [
      [metric, "var(--accent)"],
    ]);
    $(root, "#totals").textContent =
      `${metric} · 期間合計 ${number(report.totals[metric])}`;
  };
  bind(root, "load", async () => {
    const requestRevision = revision;
    const query = params();
    const loaded = await action("usage.report", query);
    if (requestRevision !== revision) return;
    report = loaded;
    applied = query;
    $(root, "#search-report").value = "";
    $(root, "#metric").innerHTML = Object.keys(report.totals)
      .map((k) => `<option>${escape(k)}</option>`)
      .join("");
    $(root, "#report").textContent = pretty(report.rows);
    $(root, "#csv").disabled = false;
    draw();
    toast("報告已完整載入");
  });
  $(root, "#metric").onchange = draw;
  bind(root, "csv", async () => {
    if (!report) throw new Error("請先載入報告");
    await bridge.download(
      "download",
      { kind: "usage", ...applied },
      "aethernexus-usage.csv",
    );
  });
  return { root };
}
