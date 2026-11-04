/**
 * Copyright (c) 2026 Skylight Software Organization.
 * Created by EternityBoundary
 * All rights reserved.
 * SPDX-License-Identifier: GPL-3.0-only
 *
 * File: migration.js
 * Project: AetherNexus for AstrBot
 */

import { escape, icon } from "./ui.js";

// Ported from AetherNexus/Views/MigrationGuide.h and its zh-TW resources.
const docs = "https://developers.openai.com/api/docs/";
const modelGuide = {
  status: "部分舊模型即將停用 · 頁面本身保留",
  impact: "停用時間依模型而異，請以目前使用的完整模型 ID 核對官方清單。",
  url: docs + "deprecations",
  steps: [
    "匯出目前工作階段，保存模型 ID、輸入與進階參數。",
    "在模型清單選擇可用的替代模型，逐一核對其支援的參數與輸入格式。",
    "以代表性案例比較輸出與成本，再更新設定；不要只更換模型名稱而保留不支援的參數。",
  ],
};
export const migrationGuides = {
  prompts: {
    title: "Prompts 遷移指南",
    status: "2026-11-30 · 雲端 Prompt 物件停用",
    impact:
      "本機 Prompt 版本庫可繼續使用；需要搬移的是官方可重用 Prompt 物件。",
    url: docs + "guides/prompting/migrate-from-prompt-object",
    steps: [
      "在停用前保存雲端 Prompt 的 instructions、輸入範本與變數定義。",
      "在本頁建立本機 Prompt，填入模型 ID 與範本；以 {{name}} 保留變數並儲存版本。",
      "用代表性輸入執行 Responses 測試；確認結果後，將應用程式的 prompt ID 呼叫改為直接傳入 instructions 與 input。",
    ],
  },
  evaluations: {
    title: "Evaluations 遷移指南",
    status: "目前唯讀 · 2026-11-30 停用",
    impact: "既有評估需在停用前保存；本機 JSON 檢視與匯出仍可使用。",
    url: "https://developers.openai.com/cookbook/examples/evaluation/moving-from-openai-evals-to-promptfoo",
    steps: [
      "逐頁載入並匯出需要的 eval、runs 與 output items。匯出清單只包含已載入的資料。",
      "另外保存資料集、評分規則、模型參數與比較基準；單一結果 JSON 不等同完整評估專案。",
      "依官方指南將測試案例及評分規則轉為 Promptfoo 設定，在自己的環境重跑並比較結果；本程式不會自動安裝或執行外部工具。",
    ],
  },
  "fine-tuning": {
    title: "Fine-tuning 遷移指南",
    status: "2027-01-06 · 停止建立新工作",
    impact:
      "既有微調模型的推論不會在此日期一併停止，仍受其基礎模型生命週期影響。",
    url: docs + "deprecations",
    steps: [
      "保存訓練與驗證資料、工作參數、結果檔案及模型 ID。",
      "以本機 Prompt、檢索增強或其他符合需求的方案建立比較版本；沒有保證等價的直接替代訓練 API。",
      "用固定測試集比較品質、延遲與成本，再更新應用程式模型設定；持續追蹤既有模型所依附的基礎模型停用時間。",
    ],
  },
  assistants: {
    title: "Assistants 遷移指南",
    status: "已於 2026-08-26 停用",
    impact: "此頁是本機遷移工作台，不會呼叫舊 Assistants API。",
    url: docs + "assistants/migration",
    steps: [
      "準備先前匯出的 Assistant 設定；匯入本頁可帶入名稱、模型與 instructions。",
      "另行保存並重建工具、檔案資源與對話狀態；這些內容不會隨 Prompt 匯入而自動轉換。",
      "以 Responses API 重建生成邏輯，需要持久對話時依官方指南使用 Conversations API；驗證工具權限與結果後再切換。",
    ],
  },
  "agent-builder": {
    title: "Agent Builder 遷移指南",
    status: "2026-11-30 · 官方 Agent Builder 停用",
    impact:
      "本頁的本機工作流程仍可編輯與匯出，與官方託管的 Agent Builder 分開。",
    url: docs + "guides/agent-builder/migrate-from-agent-builder",
    steps: [
      "先匯出本頁工作流程 JSON／Python；官方工作流程需另依官方介面匯出。兩者格式不保證相容。",
      "依指南選擇 Agents SDK 或 ChatGPT Workspace Agents，逐一重建節點、分支、工具與狀態。",
      "以原有測試輸入核對路由及工具行為，另行設定執行環境與權杖；本機匯出的 Python 不代表已完成部署。",
    ],
  },
  video: {
    title: "Video 遷移指南",
    status: "已於 2026-09-24 停用",
    impact:
      "官方 Videos API 沒有列出直接替代 API；本頁僅保留本機分鏡及既有影片預覽。",
    url: docs + "deprecations",
    steps: [
      "保存既有影片與分鏡資料，使用本頁匯出分鏡 JSON。",
      "若需要新的影片生成，另行評估可用服務的授權、資料處理及介面。",
      "保留服務獨立的分鏡描述，再依選定服務重新實作生成與下載流程；不要繼續重試已停用端點。",
    ],
  },
  audio: {
    title: "Audio 相容模式遷移指南",
    status: "部分舊音訊 API／模型將停用",
    impact: "Audio 頁面會保留；請依官方時程逐一核對舊 Speech、翻譯與轉錄模式。",
    url: docs + "deprecations",
    steps: [
      "匯出需要保留的音訊與工作階段，記下目前模型、語言、取樣率及輸出格式。",
      "語音互動改用本頁的 Realtime 模式；檔案轉錄選擇受支援的轉錄模型。舊端點的參數不能直接套用到新端點。",
      "依官方遷移文件重建翻譯等工作流程，再以相同音訊核對語言、文字內容與播放格式。",
    ],
  },
  images: { ...modelGuide, title: "Images 模型遷移指南" },
  chat: { ...modelGuide, title: "Chat 模型遷移指南" },
};

/**
 * Attach the native guide below a supported page's title without calling APIs.
 *
 * Args:
 *   root: The page element owned by the workspace cache.
 *   mode: The original WinUI page identifier.
 */
export function attachMigrationGuide(root, mode) {
  const guide = migrationGuides[mode];
  if (!guide || root.querySelector("[data-migration-page]")) return;
  const callout = document.createElement("div");
  callout.className = "migration-callout";
  callout.dataset.migrationPage = mode;
  callout.innerHTML = `<button type="button" class="tonal migration-button" aria-haspopup="dialog" aria-controls="migration-guide">${icon("link")}<span>遷移指南 · ${escape(guide.status)}</span></button><p>${escape(guide.impact)}</p>`;
  root.querySelector(".page-header").after(callout);
  callout.querySelector("button").onclick = () => {
    if (document.getElementById("migration-guide")) return;
    const dialog = document.createElement("dialog");
    dialog.id = "migration-guide";
    dialog.setAttribute("aria-labelledby", "migration-title");
    dialog.innerHTML = `<h2 id="migration-title" class="text-h3 pa-4 pb-0 pl-6">${escape(guide.title)}</h2><div class="dialog-body"><p class="migration-status">${escape(guide.status)}</p><p>${escape(guide.impact)}</p><ol class="migration-steps">${guide.steps.map((step) => `<li>${escape(step)}</li>`).join("")}</ol><p class="muted migration-footnote">文件核對：2026-11-05。開啟指南不會傳送資料或變更設定；執行模型測試須另外確認，可能產生費用。</p><a href="${escape(guide.url)}" target="_blank" rel="noopener noreferrer">開啟官方遷移文件 ↗</a></div><div class="dialog-actions"><button type="button" class="tonal" autofocus>關閉</button></div>`;
    dialog.querySelector("button").onclick = () => dialog.close();
    dialog.onclose = () => dialog.remove();
    document.body.append(dialog);
    dialog.showModal();
  };
  if (mode === "audio") {
    const notice = document.createElement("div");
    notice.className = "notice warning";
    notice.id = "audio-compatibility-notice";
    notice.setAttribute("role", "status");
    callout.after(notice);
    const picker = root.querySelector("#mode");
    const updateNotice = () => {
      const text = {
        translation:
          "相容模式使用 audio/translations，預定於 2027-02-26 停用；輸出為英文。一般轉錄請使用 gpt-transcribe。",
        speech:
          "相容模式使用 audio/speech，相關模型預定於 2027-01-06 停用。新工作流程請選 Realtime 語音。",
      }[picker.value];
      notice.textContent = text || "";
      notice.hidden = !text;
    };
    picker.addEventListener("change", updateNotice);
    updateNotice();
  }
}
