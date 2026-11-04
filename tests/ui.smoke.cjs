// Run with an offline ui_harness.py host and Playwright installed for development.
// SPDX-License-Identifier: GPL-3.0-only
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.AETHERNEXUS_BROWSER
      ? { executablePath: process.env.AETHERNEXUS_BROWSER }
      : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1080 },
  });
  const errors = [];
  const apiRequests = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/"))
      apiRequests.push(request.url());
  });
  await page.route("**/*", (route) =>
    new URL(route.request().url()).hostname === "127.0.0.1"
      ? route.continue()
      : route.abort(),
  );
  const output = path.resolve("test-results");
  await fs.mkdir(output, { recursive: true });
  try {
    await page.request.post("http://127.0.0.1:8765/api/credentials", {
      data: { kind: "admin", mode: "clear" },
    });
    await page.request.post("http://127.0.0.1:8765/api/action", {
      data: {
        action: "settings.save",
        body: {
          theme: "light",
          monthly_usd_cents: null,
          usage_command_enabled: false,
        },
      },
    });
    await page.goto("http://127.0.0.1:8765");
    const frame = page.frameLocator("#view");
    await frame.locator('[data-nav="dashboard"]').waitFor();
    await frame.locator("#load").click();
    await frame.locator("#scope-note").filter({ hasText: "已載入" }).waitFor();
    assert.notEqual(
      await frame.locator(".metric-value").first().textContent(),
      "—",
    );
    await page.screenshot({
      path: path.join(output, "dashboard-light.png"),
      fullPage: true,
    });
    const nav = [
      "agent-builder",
      "chat",
      "images",
      "audio",
      "video",
      "prompts",
      "logs",
      "traces",
      "assistants",
      "batches",
      "evaluations",
      "fine-tuning",
      "storage",
      "usage",
      "api-keys",
      "projects",
      "settings",
    ];
    for (const id of nav) {
      await frame.locator(`[data-nav="${id}"]`).click();
      assert.ok(await frame.locator("#content h1").textContent(), id);
    }
    assert.equal(
      await frame.locator("#usage-command-enabled").isChecked(),
      false,
    );
    await frame.locator("#usage-command-enabled").check();
    await frame.locator("#usage-command-save").click();
    await frame.locator("#usage-command-save:not([disabled])").waitFor();
    const beforeMissingKey = await (
      await page.request.post("http://127.0.0.1:8765/api/action", {
        data: { action: "dashboard.latest" },
      })
    ).json();
    const missingKey = await (
      await page.request.post("http://127.0.0.1:8765/offline/usage")
    ).json();
    assert.ok(missingKey.messages.join("\n").includes("Admin Key"));
    assert.deepEqual(missingKey.report, beforeMissingKey.report);
    await page.request.post("http://127.0.0.1:8765/api/credentials", {
      data: { kind: "admin", mode: "set", value: "synthetic-browser-admin" },
    });
    const firstCommand = await (
      await page.request.post("http://127.0.0.1:8765/offline/usage")
    ).json();
    assert.ok(firstCommand.messages.join("\n").includes("本月成本"));
    assert.ok(firstCommand.messages.join("\n").includes("Offline workspace"));
    await page.screenshot({
      path: path.join(output, "usage-command-settings.png"),
      fullPage: true,
    });
    await frame.locator('[data-nav="dashboard"]').click();
    await frame
      .locator("#scope-note")
      .filter({ hasText: firstCommand.report.refreshed_at })
      .waitFor();
    const secondCommand = await (
      await page.request.post("http://127.0.0.1:8765/offline/usage")
    ).json();
    await frame
      .locator("#scope-note")
      .filter({ hasText: secondCommand.report.refreshed_at })
      .waitFor({ timeout: 8000 });
    const originalStart = await frame.locator("#start").inputValue();
    await frame.locator("#start").fill("2026-10-01");
    await frame.locator("#start").dispatchEvent("change");
    await page.request.post("http://127.0.0.1:8765/offline/usage");
    await frame
      .locator("#scope-note")
      .filter({ hasText: "目前篩選範圍不同" })
      .waitFor({ timeout: 8000 });
    assert.equal(await frame.locator("#start").inputValue(), "2026-10-01");
    await frame.locator("#start").fill(originalStart);
    await frame.locator("#start").dispatchEvent("change");
    await frame.locator('[data-nav="settings"]').click();
    await frame.locator("#usage-command-enabled").uncheck();
    await frame.locator("#usage-command-save").click();
    await frame.locator("#usage-command-save:not([disabled])").waitFor();
    const disabledCommand = await (
      await page.request.post("http://127.0.0.1:8765/offline/usage")
    ).json();
    assert.ok(disabledCommand.messages.join("\n").includes("尚未開啟"));
    const migrationPages = [
      [
        "prompts",
        "Prompts 遷移指南",
        "2026-11-30",
        "https://developers.openai.com/api/docs/guides/prompting/migrate-from-prompt-object",
      ],
      [
        "assistants",
        "Assistants 遷移指南",
        "2026-08-26",
        "https://developers.openai.com/api/docs/assistants/migration",
      ],
      [
        "evaluations",
        "Evaluations 遷移指南",
        "2026-11-30",
        "https://developers.openai.com/cookbook/examples/evaluation/moving-from-openai-evals-to-promptfoo",
      ],
      [
        "fine-tuning",
        "Fine-tuning 遷移指南",
        "2027-01-06",
        "https://developers.openai.com/api/docs/deprecations",
      ],
      [
        "agent-builder",
        "Agent Builder 遷移指南",
        "2026-11-30",
        "https://developers.openai.com/api/docs/guides/agent-builder/migrate-from-agent-builder",
      ],
      [
        "audio",
        "Audio 相容模式遷移指南",
        "部分舊音訊",
        "https://developers.openai.com/api/docs/deprecations",
      ],
      [
        "video",
        "Video 遷移指南",
        "2026-09-24",
        "https://developers.openai.com/api/docs/deprecations",
      ],
      [
        "images",
        "Images 模型遷移指南",
        "部分舊模型",
        "https://developers.openai.com/api/docs/deprecations",
      ],
      [
        "chat",
        "Chat 模型遷移指南",
        "部分舊模型",
        "https://developers.openai.com/api/docs/deprecations",
      ],
    ];
    for (const [id, title, status, url] of migrationPages) {
      await frame.locator(`[data-nav="${id}"]`).click();
      const guideButton = frame.locator(
        `.page-header + [data-migration-page="${id}"] button`,
      );
      assert.ok((await guideButton.textContent()).includes(status));
      if (id === "chat") await frame.locator("#message").fill("未送出的草稿");
      const stateBefore = await frame
        .locator("#content")
        .evaluate((root) =>
          [...root.querySelectorAll("input, textarea, select")].map(
            (el) => el.value,
          ),
        );
      const requestsBefore = apiRequests.length;
      await guideButton.click();
      const dialog = frame.locator("#migration-guide");
      await dialog.waitFor();
      assert.equal(await dialog.locator("h2").textContent(), title);
      assert.equal(await dialog.locator("ol li").count(), 3);
      assert.ok((await dialog.textContent()).includes("2026-11-05"));
      assert.ok(
        (await dialog.textContent()).includes("開啟指南不會傳送資料或變更設定"),
      );
      assert.equal(await dialog.locator("a").getAttribute("href"), url);
      if (id === "agent-builder")
        await page.screenshot({
          path: path.join(output, "agent-builder-migration-light.png"),
          animations: "disabled",
        });
      if (id === "chat") await dialog.press("Escape");
      else
        await dialog.getByRole("button", { name: "關閉", exact: true }).click();
      await dialog.waitFor({ state: "detached" });
      assert.equal(
        apiRequests.length,
        requestsBefore,
        `${id}: opening and closing a guide must not call backend APIs`,
      );
      const stateAfter = await frame
        .locator("#content")
        .evaluate((root) =>
          [...root.querySelectorAll("input, textarea, select")].map(
            (el) => el.value,
          ),
        );
      assert.deepEqual(
        stateAfter,
        stateBefore,
        `${id}: guide must preserve the current draft`,
      );
    }
    await frame.locator('[data-nav="audio"]').click();
    await frame.locator("#mode").selectOption("speech");
    assert.ok(
      (
        await frame.locator("#audio-compatibility-notice").textContent()
      ).includes("2027-01-06"),
    );
    await frame.locator("#mode").selectOption("translation");
    assert.ok(
      (
        await frame.locator("#audio-compatibility-notice").textContent()
      ).includes("2027-02-26"),
    );
    assert.ok(
      (
        await frame.locator("#audio-compatibility-notice").textContent()
      ).includes("輸出為英文"),
    );
    await frame.locator("#mode").selectOption("realtime");
    assert.equal(
      await frame.locator("#audio-compatibility-notice").isVisible(),
      false,
    );
    await frame.locator('[data-nav="traces"]').click();
    await frame.locator('[data-action="traces.session"]').click();
    await frame.locator("#id").fill("session_offline");
    await frame.locator("#execute").click();
    await frame.locator('[data-record="0"]').click();
    await frame
      .locator("#span-tree")
      .filter({ hasText: "Offline model" })
      .waitFor();
    await frame.locator('[data-nav="settings"]').click();
    await frame.locator("#theme").selectOption("dark");
    await frame.locator("#save").click();
    await frame.locator('html[data-theme="dark"]').waitFor();
    await frame.locator('[data-nav="audio"]').click();
    await frame.locator('[data-migration-page="audio"] button').click();
    await page.screenshot({
      path: path.join(output, "audio-migration-dark.png"),
      animations: "disabled",
    });
    await frame
      .locator("#migration-guide")
      .getByRole("button", { name: "關閉", exact: true })
      .click();
    await frame.locator('[data-nav="dashboard"]').click();
    await page.screenshot({
      path: path.join(output, "dashboard-dark.png"),
      fullPage: true,
    });
    await frame.locator('[data-nav="chat"]').click();
    await frame.locator("#model").fill("offline-model");
    await frame.locator("#message").fill("你好，這是離線 UI 測試");
    await frame.locator("#send").click();
    await frame
      .locator(".message")
      .filter({ hasText: "所有驗證均在本機完成。" })
      .waitFor();
    await frame.locator("#send:not([disabled])").waitFor();
    await frame.locator("#message").fill("停止等待測試");
    await frame.locator("#send").click();
    await frame.locator("#stop:not([disabled])").waitFor();
    await frame.locator("#stop").click();
    await frame.locator("#send:not([disabled])").waitFor({ timeout: 3000 });
    await frame.locator('[data-nav="prompts"]').click();
    await frame.locator("#name").fill("Offline prompt");
    await frame.locator("#model").fill("offline-model");
    await frame.locator("#instructions").fill("Hello {{name}}");
    await frame.locator("#save").click();
    await frame.locator("#version-label").filter({ hasText: "v1" }).waitFor();
    await frame.locator("#instructions").fill("Updated");
    await frame.locator("#save").click();
    await frame.locator("#version-label").filter({ hasText: "v2" }).waitFor();
    await frame.locator('[data-nav="agent-builder"]').click();
    await frame.locator("#input").fill("offline workflow");
    await frame.locator("#run").click();
    await frame
      .locator("#trace")
      .filter({ hasText: "offline workflow" })
      .waitFor();
    const node = frame.locator('[data-node="start"]');
    await node.focus();
    await node.press("ArrowRight");
    assert.ok((await frame.locator("#raw").inputValue()).includes("41"));
    await frame.locator('[data-nav="images"]').click();
    await frame.locator("#model").fill("offline-image");
    await frame.locator("#prompt").fill("offline test");
    await frame.locator("#generate").click();
    await frame.locator("#images img").waitFor();
    await frame.locator('[data-nav="storage"]').click();
    await frame.locator("#file").setInputFiles({
      name: "test.jsonl",
      mimeType: "application/jsonl",
      buffer: Buffer.from('{"test":1}\n'),
    });
    await frame.locator("#purpose").selectOption("batch");
    await frame.locator("#upload").click();
    await frame.locator("#details").filter({ hasText: "offline" }).waitFor();
    await frame.locator('[data-nav="projects"]').click();
    await frame.locator('[data-action="projects.create"]').click();
    await frame.locator("#execute").click();
    await frame.locator("#confirm-value").fill("projects.create");
    await frame.locator("#accept-modal").click();
    await frame
      .locator("#result-status")
      .filter({ hasText: "已載入" })
      .waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    await frame.locator("#mobile-menu").click();
    await frame.locator('[data-nav="dashboard"]').click();
    await frame.locator(".shell:not(.nav-open)").waitFor();
    await frame.locator("#toast").evaluate((el) => (el.className = ""));
    assert.equal(
      await frame.locator('[data-nav="dashboard"]').getAttribute("class"),
      "nav-item active",
    );
    await page.screenshot({
      path: path.join(output, "dashboard-mobile.png"),
      fullPage: true,
      animations: "disabled",
    });
    const overflow = await frame
      .locator("html")
      .evaluate((el) => el.scrollWidth > el.clientWidth + 1);
    assert.equal(overflow, false, "Mobile view must not overflow horizontally");
    await frame.locator("#mobile-menu").click();
    await frame.locator('[data-nav="chat"]').click();
    await frame.locator('[data-migration-page="chat"] button').click();
    await page.screenshot({
      path: path.join(output, "chat-migration-mobile.png"),
      animations: "disabled",
    });
    const dialogBounds = await frame.locator("#migration-guide").boundingBox();
    assert.ok(
      dialogBounds.x >= 0 && dialogBounds.x + dialogBounds.width <= 390,
    );
    await frame
      .locator("#migration-guide")
      .getByRole("button", { name: "關閉", exact: true })
      .click();
    assert.deepEqual(errors, [], "Browser must not produce page errors");
    console.log(
      "Passed: usage command switch/missing key/fresh report/live Dashboard sync/filter preservation, 17 workspace routes, 9 local migration guides, audio notices, light/dark/mobile dialogs, real bridge, streaming, revisions, workflow, images and uploads.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
