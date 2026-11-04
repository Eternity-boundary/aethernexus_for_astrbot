/**
 * Copyright (c) 2026 Skylight Software Organization.
 * Created by EternityBoundary
 * All rights reserved.
 * SPDX-License-Identifier: GPL-3.0-only
 * 
 * File: settings.js
 * Project: AetherNexus for AstrBot
 */

import { action, bridge } from "./api.js";
import {
  $,
  escape,
  field,
  input,
  select,
  button,
  bind,
  confirmAction,
  toast,
} from "./ui.js";

export function settingsPage(app) {
  const root = document.createElement("section");
  root.innerHTML = `<div class="page-header"><div><div class="eyebrow">WORKSPACE / PREFERENCES</div><h1>Settings</h1><p>讓你的工作區，照自己的節奏運作。</p></div></div><div class="grid2"><div class="card stack"><h2>Appearance</h2>${field(
    "主題",
    select(
      "theme",
      [
        ["system", "跟隨 AstrBot"],
        ["light", "淺色"],
        ["dark", "深色"],
      ],
      app.status.settings.theme,
    ),
  )}${field("每月本機參考預算 · USD", '<input type="number" id="budget" min="0.01" max="1000000000" step="0.01" value="' + (app.status.settings.monthly_usd_cents ? app.status.settings.monthly_usd_cents / 100 : "") + '" placeholder="留空停用">')}<small>這是本機參考值，並非 OpenAI 伺服器預算或帳戶餘額。</small>${button("save", "儲存偏好", "check", true)}</div><div class="card stack"><h2>About AetherNexus</h2><p class="muted">從 WinUI 3 / C++ 移植至 Python 與原生 Web 技術，以 AstrBot 的驗證與視覺化視圖提供工作區。</p><div class="row"><span class="pill">v1.0.0</span><span class="pill">GPL-3.0-only</span></div><a href="https://github.com/Eternity-boundary/AetherNexus" target="_blank" rel="noopener noreferrer">原始 AetherNexus ↗</a><a href="https://docs.astrbot.app/dev/star/guides/plugin-pages.html" target="_blank" rel="noopener noreferrer">AstrBot 外掛視覺化視圖手冊 ↗</a></div></div><div class="card stack" style="margin-top:20px"><h2>Credentials</h2><div class="notice neutral">一般 Key 用於模型／BUILD，Admin Key 用於組織用量／MANAGE。可使用伺服器環境變數；在此輸入的權杖僅保留於外掛程序記憶體，重載後清除，不寫入資料庫、不回填。此儲存方式與桌面版 Windows 認證管理員不同。</div>${["api", "admin"].map((kind) => `<div class="grid2"><div class="stack">${field(kind === "api" ? "一般 API Key" : "Admin Key", `<input id="${kind}-key" type="password" autocomplete="new-password" maxlength="4096" placeholder="只輸入要取代的新權杖">`)}<small id="${kind}-status"></small></div><div class="row">${button(kind + "-save", "套用至本次執行")}${button(kind + "-clear", "清除記憶體權杖")}${button(kind + "-env", "使用環境變數")}</div></div>`).join("")}</div>`;
  const draw = () => {
    for (const kind of ["api", "admin"]) {
      const s = app.status.credentials[kind];
      $(root, "#" + kind + "-status").textContent =
        `${{ session: "已保存至記憶體，尚未驗證", environment: "已設定伺服器環境變數，尚未驗證", missing: "未設定" }[s.source]} · ${s.env}`;
    }
  };
  draw();
  bind(root, "save", async () => {
    const budget = $(root, "#budget").value;
    const cents = budget ? Number(budget) * 100 : null;
    if (cents !== null && !Number.isInteger(Math.round(cents)))
      throw new Error("預算最多兩位小數");
    if (budget && !/^\d+(\.\d{1,2})?$/.test(budget))
      throw new Error("預算最多兩位小數");
    app.status.settings = await action("settings.save", {
      body: {
        theme: $(root, "#theme").value,
        monthly_usd_cents: cents === null ? null : Math.round(cents),
      },
    });
    app.applyTheme();
    toast("偏好已儲存");
  });
  for (const kind of ["api", "admin"]) {
    bind(root, kind + "-save", async () => {
      const box = $(root, "#" + kind + "-key");
      try {
        if (!box.value) throw new Error("請輸入新權杖");
        if (
          !(await confirmAction("套用權杖至本次執行", kind, {
            kind,
            storage: "server process memory",
          }))
        )
          return;
        await bridge.apiPost("credentials", {
          kind,
          mode: "set",
          value: box.value,
        });
        app.status = await bridge.apiGet("status");
        draw();
        toast("權杖已套用；尚未驗證");
      } finally {
        box.value = "";
      }
    });
    for (const [suffix, mode] of [
      ["clear", "clear"],
      ["env", "environment"],
    ])
      bind(root, kind + "-" + suffix, async () => {
        if (
          !(await confirmAction(
            mode === "clear" ? "停用此程序的權杖" : "改用伺服器環境變數",
            kind,
            { kind, mode },
          ))
        )
          return;
        await bridge.apiPost("credentials", { kind, mode });
        app.status = await bridge.apiGet("status");
        draw();
      });
  }
  return {
    root,
    leave: () => {
      for (const kind of ["api", "admin"])
        $(root, "#" + kind + "-key").value = "";
    },
  };
}
