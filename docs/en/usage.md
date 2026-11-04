# AetherNexus workspace

Requires AstrBot 4.29.4+ (4.x) with `astrbot.api.web` and plugin views. Open **AstrBot WebUI → Plugins → AetherNexus → Visual views → AetherNexus workspace**. On narrow screens, use the top-left navigation button. The workspace currently uses Traditional Chinese and the original English feature names.

| Original WinUI entry | Plugin entry |
| --- | --- |
| Dashboard | Dashboard: apply UTC dates and an optional project; month-to-date costs use a separate date range. |
| Playground → Chat | Chat: Responses streaming, message editing, parameters, image/PDF attachments, stop, session import/export and Python example. |
| Playground → Images | Images: generation/edits, reference images, preview and original base64 output download. |
| Playground → Audio | Audio: one-turn Realtime, transcription, legacy translation/Speech, playback and WAV download. Upload audio instead of using native recording. |
| Playground → Agent Builder | Agent Builder: local version-1 graph, pointer/keyboard movement, connections, bounded execution, trace and Agents SDK export. |
| Playground → Video | Video: local storyboard and existing video preview. No retired generation API calls. |
| BUILD → Prompts / Assistants | Prompts / Assistants: shared local revision library and legacy Assistant JSON import. Restore history into a draft and save a new revision. |
| BUILD → Logs / Traces | Logs / Traces: choose a public API operation, supply IDs, then query. Select a trace to inspect its OTLP span hierarchy and JSON. |
| BUILD → Batches / Evaluations / Fine-tuning / Storage | Corresponding entry: choose an operation and supply its IDs and JSON body. Child resources are queried explicitly. |
| MANAGE → Usage / API keys / Projects | Corresponding entry: usage reports/CSV, key metadata/issuance/revocation, project membership and model rate limits. |
| Settings | Theme, local USD reference budget, and separate general/admin credential slots. |

The original Windows Credential Manager is replaced by server environment variables or process-memory credentials. Set `OPENAI_API_KEY` and `OPENAI_ADMIN_KEY` on the AstrBot server, or enter session-only credentials in Settings. Plugin configuration fields select **environment variable names**, never key values. Keys are not returned by status, persisted in the local database, or included in exports. The Dashboard administrators share this workspace and credentials; it is not a tenant isolation boundary.

Non-secret preferences and prompt revisions live in `data/plugin_data/astrbot_plugin_aethernexus_for_astrbot/workspace.sqlite3`. Dialogs require the exact target ID/action for mutations. POST/DELETE requests are never automatically retried; stopping local waiting does not prove the remote operation stopped.

Runtime assets need no frontend build, CDN or Windows runtime. All authenticated requests use `AstrBotPluginView`, including upload/download and SSE. Uploads use owned, single-use, two-minute tickets to preserve multipart options without bypassing the bridge. Requests go to fixed official HTTPS/WSS endpoints with TLS validation and no redirects/environment proxies. Defaults do not automatically issue model, usage or management requests.

Differences from the desktop version: the restricted iframe does not permit microphone capture; upload audio instead. Realtime playback starts after completion, and uploaded-audio history retains available text only. Uploads/attachments are limited to 25 MiB; responses/downloads to 40 MiB. Management uses inspectable forms and JSON rather than duplicating every native dialog. API retirement gates match the source application; see the [official deprecation page](https://developers.openai.com/api/docs/deprecations).

## Per-page migration guides

The original WinUI guides are preserved on nine pages: Prompts, Assistants, Evaluations, Fine-tuning, Agent Builder, Audio, Video, Images and Chat. Below each page title, a visible migration button shows its status/date and impact. The local dialog contains the original three steps, the documentation review date (2026-11-05), and the page-specific official migration link. Closing it or pressing Escape returns to the current draft. Opening/closing the guide does not read credentials, call backend APIs, upload data or change settings.

Prompts links to migration from prompt objects; Evaluations to Evals → Promptfoo; Agent Builder and Assistants to their dedicated migration documents. Other guides link to the deprecation page. Audio also preserves the mode-specific Speech (2027-01-06) and English translation (2027-02-26) notices. Existing backend retirement gates continue to apply.

## Screenshots and testing

These screenshots use synthetic data from the isolated test host, not real account usage.

![Light Dashboard](../assets/dashboard-light.png)

![Dark Dashboard](../assets/dashboard-dark.png)

![Mobile Dashboard](../assets/dashboard-mobile.png)

![Agent Builder migration guide, light](../assets/agent-builder-migration-light.png)

![Audio migration guide, dark](../assets/audio-migration-dark.png)

![Chat migration guide, mobile](../assets/chat-migration-mobile.png)

From the plugin directory, install `requirements-dev.txt` into an AstrBot development environment and run `python -m pytest -q`, `python -m ruff format .`, and `python -m ruff check .`. Tests block external connections and inject HTTP/WebSocket substitutes. They also instantiate the plugin using actual AstrBot public types and exercise request binding, lifecycle, uploads and SSE ownership.

For browser checks, run `python tests/ui_harness.py` in one terminal; run `pnpm install`, `pnpm exec playwright install chromium --only-shell`, and `pnpm test:ui` in another. The loopback-only harness uses the **unmodified AstrBot bridge SDK** inside the production-equivalent restricted iframe. Checks include all nine migration dialogs, their three steps and official links, close/Escape behavior, unchanged drafts, no backend calls, audio notices, and light/dark/mobile layouts. No real keys or paid requests are needed. Real account access and a full production AstrBot reload were not validated.

Build an installable archive with `python scripts/package_plugin.py`. See the [README](../../README.md) for feature coverage and [LICENSE](../../LICENSE) for GPL-3.0-only terms and original attribution.
