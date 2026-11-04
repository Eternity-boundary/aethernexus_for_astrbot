/**
 * Copyright (c) 2026 Skylight Software Organization.
 * Created by EternityBoundary
 * All rights reserved.
 * SPDX-License-Identifier: GPL-3.0-only
 * 
 * File: playground.js
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
  select,
  button,
  bind,
  pretty,
  jsonObject,
  saveFile,
  readJson,
  readBase64,
  toast,
} from "./ui.js";

const outputText = (response) =>
  (response?.output || [])
    .flatMap((o) => o.content || [])
    .filter((c) => c.type === "output_text")
    .map((c) => c.text)
    .join("");
export function chatPage() {
  const root = document.createElement("section");
  let history = [],
    runId = "",
    subscription = null,
    response = null,
    leaving = false,
    generation = 0,
    finishRun = null;
  root.innerHTML = `<div class="page-header"><div><div class="eyebrow">PLAYGROUND / TEXT</div><h1>Chat</h1><p>留一個空間，與你的下一個想法對話。</p></div><div class="row">${button("clear", "清空對話")}${button("export", "匯出工作階段", "download")}</div></div><div class="split"><div class="card"><div class="tabs"><button class="active" data-tab="conversation">對話</button><button data-tab="json">Response JSON</button><button data-tab="code">Python</button><button data-tab="history">訊息編輯</button></div><div id="conversation-panel"><div class="conversation" id="conversation"><div class="empty">${icon("chat")}<h3>從一句話開始</h3><p>填寫模型 ID 和訊息後執行。對話留在此頁記憶體，預設 store=false。</p></div></div><div class="composer">${area("message", "", 3)}<div class="row"><small id="attachment-note">圖片／PDF 附件 · 總量上限 25 MiB</small><div class="row">${button("stop", "停止")}${button("send", "執行", "arrow", true)}</div></div></div><input type="file" id="attachments" multiple accept="image/png,image/jpeg,image/webp,application/pdf" style="margin-top:12px"></div><pre id="json-panel" class="output" hidden>尚未取得回應</pre><pre id="code-panel" class="output" hidden></pre><div id="history-panel" hidden>${field("多輪訊息 JSON · role / content", area("history", "[]", 16))}${button("apply-history", "套用訊息")}</div></div><aside class="card params"><h3>Parameters</h3>${field("模型 ID", input("model", "", "輸入或選擇模型"))}${button("models", "取得模型清單", "refresh")}<datalist id="models-list"></datalist>${field("Developer instructions", area("instructions", "", 4))}${field("Max output tokens", '<input id="tokens" type="number" min="1" placeholder="由模型決定">')}${field("Reasoning effort", select("reasoning", ["", "none", "minimal", "low", "medium", "high", "xhigh"]))}${field("Temperature", '<input id="temperature" type="number" step="0.1" min="0" max="2" placeholder="使用模型預設">')}${field("Project ID", input("project", "", "金鑰預設專案"))}<label class="row"><input id="web" type="checkbox">Web search</label>${field("進階 Responses JSON", area("advanced", "{}", 6))}${field("匯入工作階段", '<input type="file" id="import" accept=".json,application/json">')}</aside></div>`;
  $(root, "#model").setAttribute("list", "models-list");
  $(root, "#stop").disabled = true;
  const draw = () => {
    $(root, "#conversation").innerHTML = history
      .map(
        (m) =>
          `<div class="message ${m.role === "user" ? "user" : ""}"><span class="message-role">${escape(m.role)}</span>${escape(typeof m.content === "string" ? m.content : pretty(m.content))}</div>`,
      )
      .join("");
    $(root, "#conversation").scrollTop = $(root, "#conversation").scrollHeight;
    $(root, "#history").value = pretty(history);
  };
  const makeBody = () => {
    const advanced = jsonObject(root, "advanced");
    const body = {
      store: false,
      ...advanced,
      model: $(root, "#model").value.trim(),
      instructions: $(root, "#instructions").value,
      input: history,
    };
    const tokens = $(root, "#tokens").value,
      temp = $(root, "#temperature").value,
      reasoning = $(root, "#reasoning").value;
    if (tokens) body.max_output_tokens = Number(tokens);
    if (temp) body.temperature = Number(temp);
    if (reasoning) body.reasoning = { effort: reasoning };
    if ($(root, "#web").checked)
      body.tools = [...(body.tools || []), { type: "web_search" }];
    return body;
  };
  const stop = async () => {
    generation += 1;
    finishRun?.();
    finishRun = null;
    if (runId) {
      const id = runId;
      runId = "";
      await bridge.apiPost(`runs/${id}/cancel`, {}).catch(() => {});
    }
    if (subscription !== null) {
      await bridge.unsubscribeSSE(subscription).catch(() => {});
      subscription = null;
    }
    $(root, "#stop").disabled = true;
    $(root, "#send").disabled = false;
  };
  root.querySelectorAll("[data-tab]").forEach(
    (b) =>
      (b.onclick = () => {
        for (const tab of ["conversation", "json", "code", "history"])
          $(root, "#" + tab + "-panel").hidden = tab !== b.dataset.tab;
        root
          .querySelectorAll("[data-tab]")
          .forEach((x) => x.classList.toggle("active", x === b));
        if (b.dataset.tab === "history")
          $(root, "#history").value = pretty(history);
        if (b.dataset.tab === "code") {
          const encoded = btoa(
            unescape(encodeURIComponent(pretty(makeBody()))),
          );
          $(root, "#code-panel").textContent =
            `# pip install openai\nimport base64, json\nfrom openai import OpenAI\nclient = OpenAI()\nbody = json.loads(base64.b64decode("${encoded}"))\nresponse = client.responses.create(**body)\nprint(response.output_text)\n`;
        }
      }),
  );
  bind(root, "models", async () => {
    const res = await action("models.list");
    $(root, "#models-list").innerHTML = (res.data || [])
      .map((m) => `<option value="${escape(m.id)}"></option>`)
      .join("");
    toast(`取得 ${res.data?.length || 0} 個模型`);
  });
  bind(root, "send", async () => {
    if (runId) throw new Error("請先停止目前的回應");
    leaving = false;
    const ticket = ++generation;
    const text = $(root, "#message").value.trim(),
      files = [...$(root, "#attachments").files];
    if (!text && !files.length) throw new Error("請先輸入訊息");
    if (!$(root, "#model").value.trim()) throw new Error("請填寫模型 ID");
    if (files.reduce((n, f) => n + f.size, 0) > 25 * 1024 * 1024)
      throw new Error("附件總量不得超過 25 MiB");
    const content = [{ type: "input_text", text }];
    for (const file of files) {
      if (
        !["image/png", "image/jpeg", "image/webp", "application/pdf"].includes(
          file.type,
        )
      )
        throw new Error("只支援 PNG/JPEG/WebP/PDF");
      const data = await readBase64(file);
      content.push(
        file.type === "application/pdf"
          ? {
              type: "input_file",
              filename: file.name,
              file_data: `data:application/pdf;base64,${data}`,
            }
          : {
              type: "input_image",
              image_url: `data:${file.type};base64,${data}`,
            },
      );
    }
    history.push({ role: "user", content: files.length ? content : text });
    const body = makeBody();
    const job = await bridge.apiPost("runs", {
      body,
      project: $(root, "#project").value,
    });
    if (ticket !== generation || leaving) {
      await bridge.apiPost(`runs/${job.run_id}/cancel`, {}).catch(() => {});
      return;
    }
    runId = job.run_id;
    draw();
    $(root, "#message").value = "";
    $(root, "#attachments").value = "";
    $(root, "#stop").disabled = false;
    let partial = "";
    const responseNode = document.createElement("div");
    responseNode.className = "message";
    responseNode.textContent = "正在等待回應…";
    $(root, "#conversation").append(responseNode);
    try {
      await new Promise((resolve, reject) => {
        finishRun = () => {
          responseNode.textContent = partial + "\n[已停止等待；內容不完整]";
          resolve();
        };
        bridge
          .subscribeSSE(`runs/${runId}/events`, {
            onMessage(event) {
              if (ticket !== generation) return;
              const data = event.parsed;
              if (data.type === "delta") {
                partial += data.text;
                responseNode.textContent = partial;
                responseNode.parentElement.scrollTop =
                  responseNode.parentElement.scrollHeight;
              } else if (data.type === "completed") {
                response = data.response;
                const answer = outputText(response) || partial;
                history.push({ role: "assistant", content: answer });
                $(root, "#json-panel").textContent = pretty(response);
                draw();
                resolve();
              } else if (data.type === "error") {
                reject(new Error(data.message));
              } else if (data.type === "cancelled") {
                responseNode.textContent =
                  partial + "\n[已停止等待；內容不完整]";
                resolve();
              }
            },
            onError() {
              reject(new Error("串流已中斷；請勿將部分內容視為完整回應。"));
            },
            onClose() {
              if (runId && ticket === generation)
                reject(new Error("串流結束但未收到完成事件。"));
            },
          })
          .then((id) => {
            if (leaving || ticket !== generation) {
              bridge.unsubscribeSSE(id).catch(() => {});
              resolve();
            } else subscription = id;
          })
          .catch(reject);
      });
    } finally {
      finishRun = null;
      runId = "";
      if (subscription !== null) {
        await bridge.unsubscribeSSE(subscription).catch(() => {});
        subscription = null;
      }
      $(root, "#stop").disabled = true;
    }
  });
  bind(root, "stop", stop);
  bind(root, "clear", async () => {
    await stop();
    history = [];
    response = null;
    draw();
    $(root, "#json-panel").textContent = "尚未取得回應";
  });
  bind(root, "apply-history", () => {
    const data = JSON.parse($(root, "#history").value);
    if (
      !Array.isArray(data) ||
      data.length > 200 ||
      data.some(
        (m) =>
          !["user", "assistant", "system", "developer"].includes(m.role) ||
          !(typeof m.content === "string" || Array.isArray(m.content)),
      )
    )
      throw new Error("訊息 JSON 格式不正確，最多 200 則");
    history = data;
    draw();
    toast("訊息已套用");
  });
  bind(root, "export", () =>
    saveFile("chat-session.json", {
      version: 1,
      model: $(root, "#model").value,
      instructions: $(root, "#instructions").value,
      messages: history,
      response,
    }),
  );
  $(root, "#import").onchange = async (e) => {
    try {
      await stop();
      const data = await readJson(e.target.files[0]);
      if (!Array.isArray(data.messages) || data.messages.length > 200)
        throw new Error("工作階段需要 messages 陣列");
      $(root, "#history").value = pretty(data.messages);
      $(root, "#apply-history").click();
      $(root, "#model").value =
        typeof data.model === "string" ? data.model : "";
      $(root, "#instructions").value =
        typeof data.instructions === "string" ? data.instructions : "";
    } catch (error) {
      toast(error.message, true);
    }
  };
  return {
    root,
    leave: () => {
      leaving = true;
      stop();
    },
  };
}

export function imagesPage() {
  const root = document.createElement("section");
  let result = null;
  root.innerHTML = `<div class="page-header"><div><div class="eyebrow">PLAYGROUND / VISUAL</div><h1>Images</h1><p>把畫面中的想像，變成看得見的作品。</p></div>${button("export", "匯出工作階段", "download")}</div><div class="split"><div class="stack"><div class="card stack">${field("Prompt", area("prompt", "", 5))}${field("參考圖片 · 最多 16 張／總量 25 MiB", '<input type="file" id="references" multiple accept="image/png,image/jpeg,image/webp">')}<div class="row">${button("generate", "生成／編輯圖片", "play", true)}<small>有參考圖片時使用 Images Edits，否則使用 Generations。</small></div></div><div class="card"><div id="images" class="media-grid"></div><div id="empty" class="empty">${icon("images")}<h3>下一張作品，從這裡開始</h3><p>輸出保留原始格式，可逐張下載。</p></div><details><summary>完整回應 JSON</summary><pre id="result" class="output">尚未執行</pre></details></div></div><aside class="card params"><h3>Image settings</h3>${field("模型 ID", input("model", "", "例如 gpt-image-2"))}${field("Size", input("size", "1024x1024"))}${field("Quality", select("quality", ["auto", "low", "medium", "high"]))}${field("Background", select("background", ["auto", "opaque", "transparent"]))}${field("Output format", select("format", ["png", "jpeg", "webp"]))}${field("張數", '<input id="count" type="number" min="1" max="10" value="1">')}${field("Project ID", input("project"))}${field("進階 API JSON", area("advanced", "{}", 5))}${field("匯入工作階段", '<input type="file" id="import" accept=".json">')}</aside></div>`;
  bind(root, "generate", async () => {
    const files = [...$(root, "#references").files];
    if (
      files.length > 16 ||
      files.reduce((n, f) => n + f.size, 0) > 25 * 1024 * 1024
    )
      throw new Error("參考圖最多 16 張且總量不超過 25 MiB");
    const references = await Promise.all(
      files.map(async (f) => ({ data: await readBase64(f), mime: f.type })),
    );
    const body = {
      ...jsonObject(root, "advanced"),
      model: $(root, "#model").value,
      prompt: $(root, "#prompt").value,
      size: $(root, "#size").value,
      quality: $(root, "#quality").value,
      background: $(root, "#background").value,
      output_format: $(root, "#format").value,
      n: Number($(root, "#count").value),
    };
    result = await action("images.generate", {
      body,
      references,
      project: $(root, "#project").value,
    });
    $(root, "#result").textContent = pretty(result);
    $(root, "#images").innerHTML = "";
    $(root, "#empty").hidden = Boolean(result.data?.length);
    for (const [index, item] of (result.data || []).entries()) {
      const div = document.createElement("div");
      if (item.b64_json) {
        const format = body.output_format,
          mime = "image/" + format;
        const image = document.createElement("img");
        image.src = `data:${mime};base64,${item.b64_json}`;
        image.alt = `生成圖片 ${index + 1}`;
        div.append(image);
        const download = document.createElement("button");
        download.textContent = "下載原圖";
        download.onclick = () =>
          saveFile(
            `image-${index + 1}.${format}`,
            Uint8Array.from(atob(item.b64_json), (c) => c.charCodeAt(0)),
            mime,
          );
        div.append(download);
      } else if (item.url) {
        const p = document.createElement("p");
        p.textContent = "API 回傳遠端圖片 URL。";
        const url = new URL(item.url);
        if (url.protocol === "https:") {
          const a = document.createElement("a");
          a.href = url.href;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = "開啟原始圖片 ↗";
          div.append(p, a);
        }
      }
      $(root, "#images").append(div);
    }
  });
  bind(root, "export", () =>
    saveFile("image-session.json", {
      version: 1,
      prompt: $(root, "#prompt").value,
      model: $(root, "#model").value,
      options: jsonObject(root, "advanced"),
      response: result,
    }),
  );
  $(root, "#import").onchange = async (e) => {
    try {
      const data = await readJson(e.target.files[0]);
      $(root, "#prompt").value = data.prompt || "";
      $(root, "#model").value = data.model || "";
      $(root, "#advanced").value = pretty(data.options || {});
      toast("已匯入提示詞與參數，尚未發起生成");
    } catch (error) {
      toast(error.message, true);
    }
  };
  return { root };
}

export function audioPage() {
  const root = document.createElement("section");
  let history = [],
    last = null;
  root.innerHTML = `<div class="page-header"><div><div class="eyebrow">PLAYGROUND / AUDIO</div><h1>Audio</h1><p>文字、語音與逐字稿，在同一個工作區。</p></div></div><div class="notice neutral">Realtime 採逐次送出、完成後播放，並非連續收音或即時播放。AstrBot 的受限視圖不開放麥克風權限，請上傳本機音檔。</div><div class="split"><div class="card stack">${field(
    "模式",
    select("mode", [
      ["realtime", "Realtime · 語音回覆"],
      ["transcription", "音檔轉錄"],
      ["translation", "英文翻譯 · 相容模式"],
      ["speech", "Speech · 相容模式"],
    ]),
  )}${field("文字輸入", area("text", "", 5))}${field("音檔（選填；轉錄模式必填）", '<input type="file" id="audio-file" accept="audio/*">')}<small>Realtime 音檔須為 24 kHz、單聲道、16-bit PCM WAV，最長 3 分鐘。其他上傳上限 25 MiB。</small><div class="row">${button("execute", "送出一次", "play", true)}${button("clear", "清除多輪上下文")}${button("download", "儲存音訊", "download")}</div><div id="player"></div><div class="output"><pre id="result">尚未執行</pre></div><a href="https://developers.openai.com/api/docs/deprecations" target="_blank" rel="noopener noreferrer">遷移指南：Speech 預定 2027-01-06 停用；舊翻譯預定 2027-02-26 停用 ↗</a></div><aside class="card params"><h3>Audio settings</h3>${field("模型 ID", input("model", "", "輸入符合目前模式的模型 ID"))}${field("聲線", select("voice", ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]))}${field("Instructions", area("instructions", "", 5))}${field("Project ID", input("project"))}<small>Realtime、轉錄與 Speech 使用不同模型與端點，請依帳戶可用模型填寫。</small></aside></div>`;
  $(root, "#download").disabled = true;
  bind(root, "execute", async () => {
    const mode = $(root, "#mode").value,
      model = $(root, "#model").value.trim(),
      project = $(root, "#project").value,
      file = $(root, "#audio-file").files[0];
    if (!model) throw new Error("請填寫此模式的模型 ID");
    if (["transcription", "translation"].includes(mode)) {
      last = await upload(mode, file, { model, project });
    } else {
      const body = {
        model,
        input: $(root, "#text").value,
        instructions: $(root, "#instructions").value,
        voice: $(root, "#voice").value,
      };
      if (mode === "realtime") {
        body.history = history;
        if (file) body.audio = await readBase64(file);
        last = await action("audio.realtime", { body, project });
        if (!file) history.push({ role: "user", content: body.input });
        if (last.text) history.push({ role: "assistant", content: last.text });
        history = history.slice(-40);
      } else
        last = await action("audio.speech", {
          body: {
            model,
            input: body.input,
            voice: body.voice,
            response_format: "wav",
          },
          project,
        });
    }
    $(root, "#result").textContent = pretty({
      ...last,
      ...(last.audio ? { audio: "[二進位音訊，請使用播放器]" } : {}),
    });
    $(root, "#player").innerHTML = "";
    if (last.audio) {
      const player = document.createElement("audio");
      player.controls = true;
      player.src = `data:${last.mime};base64,${last.audio}`;
      $(root, "#player").append(player);
    }
    $(root, "#download").disabled = !last.audio;
  });
  bind(root, "download", () => {
    if (last?.audio)
      saveFile(
        "audio.wav",
        Uint8Array.from(atob(last.audio), (c) => c.charCodeAt(0)),
        last.mime,
      );
  });
  bind(root, "clear", () => {
    history = [];
    toast("多輪上下文已清除");
  });
  return {
    root,
    leave: () => root.querySelectorAll("audio").forEach((a) => a.pause()),
  };
}
