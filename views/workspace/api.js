/**
 * Copyright (c) 2026 Skylight Software Organization.
 * Created by EternityBoundary
 * All rights reserved.
 * SPDX-License-Identifier: GPL-3.0-only
 * 
 * File: api.js
 * Project: AetherNexus for AstrBot
 */
export const bridge = window.AstrBotPluginView;
export const action = (name, data = {}) =>
  bridge.apiPost("action", { action: name, ...data });
export async function upload(kind, file, params = {}) {
  if (!file || file.size > 25 * 1024 * 1024)
    throw new Error("請選擇不超過 25 MiB 的檔案。");
  const plan = await bridge.apiPost("uploads", { kind, params });
  return bridge.upload(`upload/${plan.upload_id}`, file);
}
