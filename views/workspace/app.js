/**
 * Copyright (c) 2026 Skylight Software Organization.
 * Created by EternityBoundary
 * All rights reserved.
 * SPDX-License-Identifier: GPL-3.0-only
 *
 * File: app.js
 * Project: AetherNexus for AstrBot
 */

import { action, bridge } from "./api.js";
import { $, escape, icon, toast } from "./ui.js";
import { dashboardPage, usagePage } from "./dashboard.js";
import { chatPage, imagesPage, audioPage } from "./playground.js";
import { libraryPage } from "./library.js";
import { resourcePage } from "./resources.js";
import { workflowPage, videoPage } from "./builders.js";
import { settingsPage } from "./settings.js";
import { attachMigrationGuide } from "./migration.js";

const groups = [
  ["", ["dashboard"]],
  ["PLAYGROUND", ["agent-builder", "chat", "images", "audio", "video"]],
  [
    "BUILD",
    [
      "prompts",
      "logs",
      "traces",
      "assistants",
      "batches",
      "evaluations",
      "fine-tuning",
      "storage",
    ],
  ],
  ["MANAGE", ["usage", "api-keys", "projects"]],
];
const titles = {
  dashboard: "Dashboard",
  "agent-builder": "Agent Builder",
  chat: "Chat",
  images: "Images",
  audio: "Audio",
  video: "Video",
  prompts: "Prompts",
  logs: "Logs",
  traces: "Traces",
  assistants: "Assistants",
  batches: "Batches",
  evaluations: "Evaluations",
  "fine-tuning": "Fine-tuning",
  storage: "Storage",
  usage: "Usage",
  "api-keys": "API keys",
  projects: "Projects",
  settings: "Settings",
};
const descriptions = {
  logs: "已儲存的 Chat Completions 與已知 ID 的 Responses；並非所有 API 請求的日誌。",
  traces: "透過公開 Agent sessions API 檢視 traces；需要組織匯出及權限。",
  batches: "建立、查詢與取消 24 小時完成視窗的批次工作。",
  evaluations: "唯讀檢視既有評估，匯出結果並保留資料。",
  "fine-tuning": "檢視訓練工作、事件與 checkpoints，管理模型微調。",
  storage: "管理 Files 與向量庫，讓知識有適當的位置。",
  "api-keys": "依專案管理金鑰，或簽發 Admin／服務帳戶權杖。",
  projects: "管理專案、組織既有成員與模型速率限制。",
};
const cache = new Map();
let current, context, off;
const app = {
  titles,
  descriptions,
  status: null,
  catalog: null,
  navigate,
  applyTheme() {
    document.documentElement.dataset.theme =
      app.status.settings.theme === "system"
        ? context.isDark
          ? "dark"
          : "light"
        : app.status.settings.theme;
  },
};

function navigate(id) {
  if (!titles[id]) id = "dashboard";
  current?.leave?.();
  if (!cache.has(id)) {
    const factories = {
      dashboard: () => dashboardPage(app),
      usage: usagePage,
      chat: chatPage,
      images: imagesPage,
      audio: audioPage,
      prompts: () => libraryPage(app),
      assistants: () => libraryPage(app, true),
      "agent-builder": workflowPage,
      video: videoPage,
      settings: () => settingsPage(app),
    };
    cache.set(id, factories[id] ? factories[id]() : resourcePage(app, id));
    attachMigrationGuide(cache.get(id).root, id);
  }
  current = cache.get(id);
  document.getElementById("content").replaceChildren(current.root);
  document
    .querySelectorAll("[data-nav]")
    .forEach((el) => el.classList.toggle("active", el.dataset.nav === id));
  document.getElementById("breadcrumb").textContent = titles[id];
  document.querySelector(".shell").classList.remove("nav-open");
  if (location.hash !== `#${id}`) location.hash = id;
  document.title = titles[id] + " · AetherNexus";
}

try {
  if (!bridge)
    throw new Error("請從 AstrBot WebUI 的外掛可視化視圖開啟 AetherNexus。");
  context = await bridge.ready();
  [app.status, app.catalog] = await Promise.all([
    bridge.apiGet("status"),
    action("catalog"),
  ]);
  document.getElementById("app").innerHTML =
    `<div class="shell"><aside class="sidebar" aria-label="工作區導覽"><div class="brand"><span class="brand-mark">A</span>AetherNexus</div><div class="workspace-label">OPENAI PLATFORM<strong>Personal workspace</strong><small>Powered by AstrBot</small></div><nav>${groups.map(([label, items]) => (label ? `<div class="nav-group">${label}</div>` : "") + items.map((id) => `<button class="nav-item" data-nav="${id}">${icon(id)}<span>${titles[id]}</span></button>`).join("")).join("")}</nav><div class="sidebar-footer"><button class="nav-item" data-nav="settings">${icon("settings")}<span>Settings</span></button><small>AetherNexus for AstrBot · 1.0.0</small></div></aside><main class="main"><header class="topbar"><div class="breadcrumbs"><button id="mobile-menu" aria-label="開啟導覽">${icon("menu")}</button><span>Workspace</span><span>/</span><b id="breadcrumb">Dashboard</b></div><div class="host-badge"><span class="dot"></span>AstrBot connected</div></header><div id="content"></div></main></div>`;
  document
    .querySelectorAll("[data-nav]")
    .forEach((el) => (el.onclick = () => navigate(el.dataset.nav)));
  document.getElementById("mobile-menu").onclick = () =>
    document.querySelector(".shell").classList.toggle("nav-open");
  app.applyTheme();
  off = bridge.onContext((next) => {
    context = next;
    app.applyTheme();
  });
  navigate(location.hash.slice(1) || "dashboard");
  window.addEventListener("hashchange", () => {
    if (current !== cache.get(location.hash.slice(1)))
      navigate(location.hash.slice(1));
  });
} catch (error) {
  document.getElementById("app").innerHTML =
    `<div class="boot"><span class="brand-mark">A</span><h1>AetherNexus</h1><p>${escape(error.message)}</p></div>`;
}
window.addEventListener("beforeunload", () => {
  current?.leave?.();
  off?.();
  for (const page of cache.values()) page.dispose?.();
});
