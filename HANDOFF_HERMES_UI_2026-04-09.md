# Hermes-First Open WebUI Handoff

## Source Of Truth

Use these in this order:

1. `/Users/martin/open-webui/AGENTS.md`
2. `/Users/martin/Downloads/open-webui-hermes-ux-spec (1).md`

Important:

- This project is **not** a redesign of Open WebUI.
- This project **is** an adaptation of Open WebUI into a Hermes-first interface.
- Preserve the Open WebUI shell, visual identity, spacing rhythm, calm topbar/sidebar feel, and restrained styling.
- Use 21st.dev only for point patterns/micro-surfaces, not for shell/page replacement.

## Current Overall Status

This is no longer at the "just started" stage. The Hermes-first adaptation already has a substantial UI foundation in place.

Already implemented and visible in the live app:

- Inline transcript approval surface
- Grouped operational transcript block for non-final assistant activity
- Compact tool activity rows
- Strengthened sidebar session row treatment
- Right-side first-class panels inside the existing controls/panel system
- Workspace tab exists as a first-class panel tab
- Navbar quick-entry mini-cluster for opening existing panels faster

This is still **not done**. The project is in the "middle-plus / approaching final implementation waves" stage, not polish-only yet.

## Live Runtime

### App URL

- `http://127.0.0.1:8080`

### QA Chat URL

- `http://127.0.0.1:8080/c/b62bb0d2-70e9-44ee-aee9-d3537c5d9713`

### Local QA Credentials

- Email: `<redacted-email>`
- Password: `<redacted-password>`

### Notes

- The QA chat contains seeded assistant activity for testing transcript slices.
- There is also a local QA user and local seeded chat data in the dev DB.
- Do not do cleanup yet unless explicitly asked.

## 21st.dev Status

21st.dev MCP is now working.

The user explicitly asked to:

- finish the remaining Hermes-first surfaces first
- postpone the replacement/polish wave with 21st.dev-derived micro-surfaces until after the functional/coverage work is done

I added TODO comments in local Hermes components where future 21st.dev replacement is intended.

## Critical Build/Serve Quirk

This is the most important practical note for the next agent.

### The backend-served app does not reliably reflect local source changes unless you do all of the following:

1. Build frontend assets.
2. Reinstall the editable Python package.
3. Restart the backend app on `:8080`.

Commands that worked:

```bash
./node_modules/.bin/vite build
uv pip install --python "/Users/martin/open-webui/.venv/bin/python" -e "/Users/martin/open-webui"
pkill -f "uvicorn open_webui.main:app"
"/Users/martin/open-webui/.venv/bin/python" -m uvicorn open_webui.main:app --host 127.0.0.1 --port 8080 --forwarded-allow-ips "*"
```

Notes:

- `npm run build` also works, but it is slower because it redoes the heavy pyodide setup path.
- Using `vite build` directly is much faster for repeated frontend iterations.
- Backend serves the packaged frontend, so `vite build` alone is often not enough; `uv pip install -e .` matters.

## What Is Already Implemented

### Transcript

Implemented:

- Inline Hermes approval card attached to assistant turns
- Approval card now embedded into a calmer operational block instead of floating separately
- Status/tool/approval grouped under one operational area
- Compact tool activity rows
- Compact progress/status row treatment

Important files:

- `src/lib/components/chat/Chat.svelte`
- `src/lib/components/chat/Messages.svelte`
- `src/lib/components/chat/Messages/Message.svelte`
- `src/lib/components/chat/Messages/MultiResponseMessages.svelte`
- `src/lib/components/chat/Messages/ResponseMessage.svelte`
- `src/lib/components/chat/Messages/CodeExecutions.svelte`
- `src/lib/components/chat/Messages/ResponseMessage/StatusHistory.svelte`
- `src/lib/components/chat/Messages/ResponseMessage/StatusHistory/StatusItem.svelte`
- `src/lib/components/hermes/transcript/HermesApprovalCard.svelte`
- `src/lib/components/hermes/transcript/HermesOperationalBlock.svelte`
- `src/lib/components/hermes/transcript/HermesToolActivityRow.svelte`

Current live behavior:

- Works in the QA chat on `:8080`
- Approval buttons are present
- Operational block is visually secondary to assistant content

### Sidebar Session Rows

Implemented:

- Additional calm metadata line in chat/session rows
- Running/current chat states still keep native Open WebUI selected/hover behavior
- Session rows now surface lightweight Hermes-relevant metadata without becoming dashboard cards

Important files:

- `src/lib/components/layout/Sidebar.svelte`
- `src/lib/components/layout/Sidebar/ChatItem.svelte`
- `src/lib/components/layout/Sidebar/RecursiveFolder.svelte`

Current live behavior:

- Works in the live app
- Metadata line appears for relevant rows

### Right-Side First-Class Panels

Implemented inside the existing `ChatControls` panel system:

- `Session`
- `Profile`
- `Skills`
- `Memory`
- `Tasks`
- `Todos` / checklist
- `Workspace`

Important files:

- `src/lib/components/chat/ChatControls.svelte`
- `src/lib/components/chat/Navbar.svelte`
- `src/lib/stores/index.ts`
- `src/lib/components/hermes/panels/HermesSessionPanel.svelte`
- `src/lib/components/hermes/panels/HermesProfilePanel.svelte`
- `src/lib/components/hermes/panels/HermesSkillsPanel.svelte`
- `src/lib/components/hermes/panels/HermesMemoryPanel.svelte`
- `src/lib/components/hermes/panels/HermesTasksPanel.svelte`
- `src/lib/components/hermes/panels/HermesTodosPanel.svelte`

Current live behavior:

- All these tabs are visible in the right-side panel tab bar in the live app
- `Workspace` is now a first-class tab and can be opened from the panel itself and from the navbar quick-entry button
- Navbar quick-entry mini-cluster is present and visible in the live topbar for:
  - `Workspace`
  - `Session`
  - `Tasks`

### Workspace Surface

Implemented:

- `Workspace` tab is always visible, not only when runtime/terminal is active
- Existing terminal / pyodide file browsers remain in place when available
- Added a fallback workspace stub for chats without active runtime/filesystem sources
- Added workspace header and guide row patterns
- Added filtering in file nav toolbar
- Added explicit `Close` preview controls
- Added `Attach to chat` actions in file surfaces for terminal and pyodide file views

Important files:

- `src/lib/components/chat/ChatControls.svelte`
- `src/lib/components/chat/FileNav.svelte`
- `src/lib/components/chat/FileNav/FileNavToolbar.svelte`
- `src/lib/components/chat/PyodideFileNav.svelte`
- `src/lib/components/hermes/workspace/HermesWorkspaceHeader.svelte`
- `src/lib/components/hermes/workspace/HermesWorkspaceGuideRow.svelte`
- `src/lib/components/hermes/workspace/HermesWorkspaceStub.svelte`

Current live behavior:

- `Workspace` tab is visible and can be activated in the right panel
- In the current QA chat without an active runtime directory, it shows the fallback workspace surface
- The fallback content is visible in live DOM as:
  - workspace header
  - explanatory text
  - current chat files section

### Localization

Relevant keys were added to:

- `src/lib/i18n/locales/en-US/translation.json`
- `src/lib/i18n/locales/ru-RU/translation.json`

This includes translations for:

- approval / activity / tasks / todos / workspace / session / profile / files / guide-row / quick action labels

## Current Live QA Observations

Verified in the live app:

- Transcript operational group works
- Sidebar session metadata works
- Panel tabs visible in the right-side panel:
  - `Управление`
  - `Рабочее пространство`
  - `Обзор`
  - `Сессия`
  - `Профиль`
  - `Навыки`
  - `Воспоминания`
  - `Задачи`
  - `Чеклист`
- Navbar quick-entry buttons visible:
  - `Рабочее пространство`
  - `Сессия`
  - `Задачи`

Important QA caveat:

- The a11y/devtools snapshot sometimes lagged behind actual DOM updates after tab switches.
- Direct DOM checks via `chrome-devtools_evaluate_script` were more reliable than snapshots for confirming panel content.

## Current Known Non-Blocking Issues

### 1. Repo-wide build/check noise

There is a lot of existing baseline frontend debt unrelated to this Hermes-first work:

- self-closing non-void tags
- missing aria labels elsewhere in repo
- old implicit `any` / stale TS issues
- existing warnings in unrelated screens/components

Do not turn this into a repo-wide cleanup pass unless the user explicitly asks.

### 2. Terminal/runtime-specific workspace verification still shallow

Current QA chat mostly exercised the fallback workspace case.

Still worth verifying in a future pass:

- real terminal workspace path
- pyodide-generated files path
- attach-to-chat from selected workspace file in both flows

### 3. Some English seeded QA transcript content still appears in the conversation body

Example seeded strings in the seeded chat messages remain English because they are data, not UI strings.
This is acceptable for now and not a UI bug.

## Immediate Next Steps For The New Agent

Recommended order:

1. Verify the new `Attach to chat` workspace action in both:
   - `FileNav.svelte`
   - `PyodideFileNav.svelte`

2. Strengthen the right-side workspace surface so it feels more like a working directory surface:
   - show clearer current path / source / item counts
   - keep it calm and Open WebUI-native
   - do not redesign panel chrome

3. Continue safe session-model improvements inside the existing shell:
   - session metadata
   - session surfacing
   - transcript operational polish

4. Only after functional coverage feels complete:
   - start a dedicated 21st.dev replacement/polish pass
   - replace local Hermes micro-surfaces gradually using 21st-derived patterns

## Recommended Safe Next Slices

These are the next safest bounded slices consistent with AGENTS.md:

1. Workspace behavior polish
   - strongest ROI right now
   - directly matches user request about file directory / file system surface on the right

2. Session model polish
   - compact session metadata improvements
   - possible session-focused panel/topbar refinement

3. Transcript operational polish
   - further reduce fragmentation between progress/tools/approvals
   - do not redesign message layout

## Files Added In This Hermes Wave

- `src/lib/components/hermes/transcript/HermesApprovalCard.svelte`
- `src/lib/components/hermes/transcript/HermesOperationalBlock.svelte`
- `src/lib/components/hermes/transcript/HermesToolActivityRow.svelte`
- `src/lib/components/hermes/workspace/HermesWorkspaceHeader.svelte`
- `src/lib/components/hermes/workspace/HermesWorkspaceGuideRow.svelte`
- `src/lib/components/hermes/workspace/HermesWorkspaceStub.svelte`
- `src/lib/components/hermes/panels/HermesSkillsPanel.svelte`
- `src/lib/components/hermes/panels/HermesMemoryPanel.svelte`
- `src/lib/components/hermes/panels/HermesTasksPanel.svelte`
- `src/lib/components/hermes/panels/HermesTodosPanel.svelte`
- `src/lib/components/hermes/panels/HermesProfilePanel.svelte`
- `src/lib/components/hermes/panels/HermesSessionPanel.svelte`

## Important Changed Existing Files

- `src/lib/components/chat/Chat.svelte`
- `src/lib/components/chat/ChatControls.svelte`
- `src/lib/components/chat/FileNav.svelte`
- `src/lib/components/chat/FileNav/FileNavToolbar.svelte`
- `src/lib/components/chat/PyodideFileNav.svelte`
- `src/lib/components/chat/Navbar.svelte`
- `src/lib/components/chat/Messages.svelte`
- `src/lib/components/chat/Messages/Message.svelte`
- `src/lib/components/chat/Messages/MultiResponseMessages.svelte`
- `src/lib/components/chat/Messages/CodeExecutions.svelte`
- `src/lib/components/chat/Messages/ResponseMessage.svelte`
- `src/lib/components/chat/Messages/ResponseMessage/StatusHistory.svelte`
- `src/lib/components/chat/Messages/ResponseMessage/StatusHistory/StatusItem.svelte`
- `src/lib/components/layout/Sidebar.svelte`
- `src/lib/components/layout/Sidebar/ChatItem.svelte`
- `src/lib/components/layout/Sidebar/RecursiveFolder.svelte`
- `src/lib/components/chat/Navbar.svelte`
- `src/lib/stores/index.ts`
- `src/lib/i18n/locales/en-US/translation.json`
- `src/lib/i18n/locales/ru-RU/translation.json`

## Unrelated/Do-Not-Touch Notes

- The worktree may contain unrelated changes and untracked files; do not revert anything unrelated.
- `uv.lock` changed because of local packaging/build work; do not assume it is intentional product logic unless reviewed.
- There are untracked docs/spec files in the repo state; do not delete or rewrite them unless the user asks.

## Short Practical Resume Checklist For The Next Agent

1. Read:
   - `AGENTS.md`
   - `/Users/martin/Downloads/open-webui-hermes-ux-spec (1).md`
   - this handoff file

2. Open live app:
   - `http://127.0.0.1:8080/c/b62bb0d2-70e9-44ee-aee9-d3537c5d9713`

3. Log in with:
   - `<redacted-email>`
   - `<redacted-password>`

4. Verify in UI:
   - topbar quick-entry cluster exists
   - right-side tab set exists
   - `Workspace` opens and shows workspace surface
   - `Session/Profile/Skills/Memory/Tasks/Todos` tabs render

5. For code iteration:
   - `./node_modules/.bin/vite build`
   - `uv pip install --python "/Users/martin/open-webui/.venv/bin/python" -e "/Users/martin/open-webui"`
   - restart uvicorn on `:8080`

## Final Intent

The app should remain unmistakably Open WebUI.

Hermes should show up as:

- better operational transcript behavior
- stronger session model
- more useful right-side workspace/panel surface
- calmer, denser operator-facing micro-surfaces

The next agent should continue **coverage first**, **21st.dev replacement second**.
