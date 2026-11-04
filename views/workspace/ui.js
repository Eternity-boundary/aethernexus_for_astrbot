/**
 * Copyright (c) 2026 Skylight Software Organization.
 * Created by EternityBoundary
 * All rights reserved.
 * SPDX-License-Identifier: GPL-3.0-only
 * 
 * File: ui.js
 * Project: AetherNexus for AstrBot
 */

export const $ = (root, selector) => root.querySelector(selector);
export const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const pretty = (value) => JSON.stringify(value, null, 2);
export const number = (value) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        maximumFractionDigits: 2,
        notation: Math.abs(value) >= 1e6 ? "compact" : "standard",
      }).format(value);
export const paths = {
  dashboard: "M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-8H9v8H4a1 1 0 0 1-1-1Z",
  chat: "M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5a9.5 9.5 0 0 1 19 0ZM7 9h10M7 13h6",
  images:
    "M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1ZM3 17l6-6 4 4 3-3 5 5M16 7h.01",
  audio:
    "M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0ZM5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8",
  video: "M3 5h12v14H3ZM15 10l6-4v12l-6-4",
  "agent-builder": "M3 3h6v6H3ZM15 15h6v6h-6ZM15 3h6v6h-6ZM6 9v9h9M9 6h6",
  prompts: "M13 3 3 13v8h8L21 11ZM3 17l4 4M11 5l8 8",
  logs: "M5 3h14v18H5ZM8 7h8M8 11h8M8 15h5",
  traces: "M5 3v16h15M5 7h8M5 13h12M13 5v4M17 11v4",
  assistants:
    "M8 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM2 21v-3a6 6 0 0 1 12 0v3M17 3a4 4 0 0 1 0 8M17 15a5 5 0 0 1 5 5v1",
  batches: "m12 2 10 5-10 5L2 7ZM2 12l10 5 10-5M2 17l10 5 10-5",
  evaluations: "M9 12l2 2 4-4M12 2l9 4v6c0 6-9 10-9 10S3 18 3 12V6Z",
  "fine-tuning": "M4 7h16M4 17h16M8 4v6M16 14v6",
  storage: "M3 7V4h7l2 3h9v13H3ZM3 10h18",
  usage: "M4 20V10M12 20V4M20 20v-7",
  "api-keys": "M15 3a6 6 0 1 0 6 6 6 6 0 0 0-6-6ZM11 13l-8 8H1v-4l8-8M17 7h.01",
  projects: "M3 6h18v15H3ZM8 6V3h8v3M3 12h18M10 12v3h4v-3",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM9 2h6l1 3 3 1 3 4-2 3v4l-4 2-1 3H9l-1-3-3-1-3-4 2-3V7l4-2Z",
  arrow: "M5 12h14M14 7l5 5-5 5",
  refresh: "M20 8a8 8 0 1 0 0 8M20 3v5h-5",
  plus: "M12 4v16M4 12h16",
  download: "M12 3v12M7 10l5 5 5-5M4 16v5h16v-5",
  play: "m8 4 12 8-12 8Z",
  menu: "M3 6h18M3 12h18M3 18h18",
  moon: "M20 15A8 8 0 0 1 9 4a8 8 0 1 0 11 11Z",
  check: "m5 12 4 4L19 6",
  link: "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2",
};
export const icon = (name) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.logs}"/></svg>`;
export const field = (label, control, hint = "") =>
  `<label class="field"><span>${escape(label)}</span>${control}${hint ? `<small>${escape(hint)}</small>` : ""}</label>`;
export const input = (id, value = "", placeholder = "") =>
  `<input id="${id}" value="${escape(value)}" placeholder="${escape(placeholder)}">`;
export const area = (id, value = "", rows = 5) =>
  `<textarea id="${id}" rows="${rows}" spellcheck="false">${escape(value)}</textarea>`;
export const select = (id, options, value = "") =>
  `<select id="${id}">${options
    .map((o) => {
      const [v, label] = Array.isArray(o) ? o : [o, o];
      return `<option value="${escape(v)}" ${v === value ? "selected" : ""}>${escape(label)}</option>`;
    })
    .join("")}</select>`;
export const button = (id, label, symbol = "", primary = false) =>
  `<button id="${id}" class="${primary ? "primary" : ""}">${symbol ? icon(symbol) : ""}${escape(label)}</button>`;
export function jsonObject(root, id) {
  const value = JSON.parse($(root, `#${id}`).value || "{}");
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("請填寫 JSON 物件。");
  return value;
}
export function toast(message, error = false) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.className = error ? "visible error" : "visible";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (node.className = ""), 6500);
}
export function bind(root, id, callback) {
  $(root, `#${id}`).addEventListener("click", async (event) => {
    const target = event.currentTarget;
    target.disabled = true;
    try {
      await callback(event);
    } catch (error) {
      toast(error.message || "操作失敗", true);
    } finally {
      target.disabled = false;
    }
  });
}
export function saveFile(name, value, type = "application/json") {
  const blob = new Blob(
    [
      typeof value === "string" || value instanceof Uint8Array
        ? value
        : pretty(value),
    ],
    { type },
  );
  const url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
export async function readJson(file) {
  if (!file || file.size > 8 * 1024 * 1024)
    throw new Error("請選擇小於 8 MiB 的 JSON 檔。");
  return JSON.parse(await file.text());
}
export async function readBase64(file) {
  if (file.size > 25 * 1024 * 1024) throw new Error("單一附件上限為 25 MiB。");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("讀取失敗"));
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.readAsDataURL(file);
  });
}
export function confirmAction(title, target, data) {
  const dialog = document.getElementById("modal");
  dialog.innerHTML = `<h2 id="modal-title" class="text-h3 pa-4 pb-0 pl-6">${escape(title)}</h2><div class="dialog-body"><p>請核對操作內容，並輸入 <strong>${escape(target)}</strong> 確認。寫入不會自動重送。</p><pre>${escape(pretty(data))}</pre><input id="confirm-value" autocomplete="off" aria-label="確認目標 ID"></div><div class="dialog-actions"><button id="cancel-modal" class="text" autofocus>取消</button><button id="accept-modal" class="tonal" disabled>確認操作</button></div>`;
  dialog.showModal();
  return new Promise((resolve) => {
    const finish = (result) => {
      dialog.close();
      dialog.innerHTML = "";
      dialog.oncancel = null;
      resolve(result);
    };
    $(dialog, "#confirm-value").oninput = (event) =>
      ($(dialog, "#accept-modal").disabled = event.target.value !== target);
    $(dialog, "#cancel-modal").onclick = () => finish(false);
    $(dialog, "#accept-modal").onclick = () => finish(true);
    dialog.oncancel = (event) => {
      event.preventDefault();
      finish(false);
    };
  });
}
export function showSecret(secret) {
  const dialog = document.getElementById("modal");
  dialog.innerHTML =
    '<h2 id="modal-title" class="text-h3 pa-4 pb-0 pl-6">權杖已簽發</h2><div class="dialog-body"><p>只顯示這一次。請自行保存；關閉後不保留於頁面狀態或匯出內容。</p><textarea id="issued-key" readonly rows="4" aria-label="一次性權杖"></textarea></div><div class="dialog-actions"><button id="close-secret" class="tonal">已保存，關閉</button></div>';
  $(dialog, "#issued-key").value = secret;
  secret = "";
  const clear = () => {
    $(dialog, "#issued-key").value = "";
    dialog.close();
    dialog.innerHTML = "";
    dialog.oncancel = null;
  };
  $(dialog, "#close-secret").onclick = clear;
  dialog.oncancel = (e) => {
    e.preventDefault();
    clear();
  };
  dialog.showModal();
}
export function utcRange(days = 7) {
  const end = new Date(),
    start = new Date(end);
  start.setUTCDate(start.getUTCDate() - days + 1);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}
