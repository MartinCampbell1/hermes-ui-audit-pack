# Hermes-First Open WebUI Handoff

## Date

- `2026-04-10`

## Read This First

Use sources of truth in this order:

1. `/Users/martin/open-webui/AGENTS.md`
2. `/Users/martin/Downloads/open-webui-hermes-ux-spec (1).md`
3. `/Users/martin/open-webui/docs/hermes-integration-spec.md`

The core rule has **not changed**:

- This project is **not** a redesign of Open WebUI.
- This project **is** an adaptation of Open WebUI into a Hermes-first interface.
- Preserve Open WebUI shell, visual identity, spacing rhythm, calm sidebar/topbar feel, and restrained styling.
- Pull Hermes logic and behavior forward, not Hermes visual style.
- Use 21st.dev only for bounded micro-surfaces later, not for shell/page replacement.

## Where The Project Actually Is

This is not early-stage anymore.

Already implemented before this handoff:

- Hermes-style inline approval surface in transcript
- Grouped operational assistant block
- Compact tool activity rows
- Strengthened sidebar session metadata treatment
- Right-side first-class panels inside existing Open WebUI controls system
- Workspace tab as a first-class right-side panel
- Navbar quick-entry buttons for important Hermes surfaces
- Workspace fallback stub for chats without runtime file trees

This project is still **mid-implementation**, not polish-only.

The key status change from this session:

- The project now has a **real Hermes session/runtime bridge slice**.
- Open WebUI can now discover real Hermes sessions from local Hermes stores and import/open them from the existing `Session` panel.
- This is the first real backend continuity slice, not just a UI facade.

## What I Implemented In This Slice

### 1. Real Hermes backend bridge

Added a new backend utility module:

- `/Users/martin/open-webui/backend/open_webui/utils/hermes.py`

This module now handles:

- base Hermes home resolution
- active Hermes profile resolution
- active Hermes home resolution
- Hermes agent checkout discovery
- Hermes Python discovery with correct precedence
- Hermes session list loading from:
  - `~/.hermes/state.db`
  - `~/.hermes/sessions/session_*.json`
- merged session list behavior
- single-session load for import
- Open WebUI chat import payload generation

Important behavior details:

- Active Hermes home is resolved **dynamically on every call**, not cached at module import for runtime-sensitive session reads.
- Python discovery order is:
  1. `HERMES_WEBUI_PYTHON`
  2. `HERMES_PYTHON`
  3. `<agent-dir>/venv/bin/python`
  4. `<agent-dir>/.venv/bin/python`
  5. repo `.venv/bin/python`
  6. system `python3` or `python` as last resort, with warning
- Agent dir discovery prefers:
  1. `HERMES_WEBUI_AGENT_DIR`
  2. `${base_hermes_home}/hermes-agent`
  3. repo sibling `../hermes-agent`
  4. parent if it itself looks like an agent checkout
  5. `~/.hermes/hermes-agent`
  6. `~/hermes-agent`

Very important implementation detail:

- I intentionally changed the returned runtime Python path to the **venv-local symlink path** like:
  - `/Users/martin/.hermes/hermes-agent/.venv/bin/python`
- This avoids misleading diagnostics where `.resolve()` would display the underlying uv-managed interpreter path instead of the Hermes agent venv path.

### 2. New Hermes API router

Added:

- `/Users/martin/open-webui/backend/open_webui/routers/hermes.py`

Connected in:

- `/Users/martin/open-webui/backend/open_webui/main.py`

New endpoints:

- `GET /api/v1/hermes/runtime`
- `GET /api/v1/hermes/sessions`
- `POST /api/v1/hermes/sessions/import`

Current contracts:

#### `GET /api/v1/hermes/runtime`

Returns:

- `active_home`
- `active_profile`
- `agent_dir`
- `python_path`
- `state_db_path`
- `session_dir`
- `warnings`

#### `GET /api/v1/hermes/sessions`

Returns:

- `active_home`
- `active_profile`
- `items`

Each item currently includes:

- `session_id`
- `title`
- `model`
- `message_count`
- `created_at`
- `updated_at`
- `profile`
- `source_tag`
- `last_user_content`
- `available_sources`

#### `POST /api/v1/hermes/sessions/import`

Body:

```json
{
  "session_id": "<hermes_session_id>"
}
```

Returns:

- `session_id`
- `chat` as a normal imported Open WebUI `ChatResponse`

### 3. Frontend Hermes API layer

Added:

- `/Users/martin/open-webui/src/lib/apis/hermes/index.ts`

This now exposes:

- `getHermesRuntime`
- `getHermesSessions`
- `importHermesSession`

### 4. Session panel integration

The safe frontend insertion point was confirmed to be the existing `Session` panel, not sidebar architecture.

Files changed:

- `/Users/martin/open-webui/src/lib/components/chat/ChatControls.svelte`
- `/Users/martin/open-webui/src/lib/components/hermes/panels/HermesSessionPanel.svelte`

What the panel now does:

- still shows current-chat stats
- now also shows Hermes runtime info:
  - active profile
  - active home
  - discovered agent path
  - discovered python path
  - runtime warnings if any
- now lazily loads real Hermes session list when the `Session` tab becomes active
- now offers `Import and open`
- after import it uses existing Open WebUI store-refresh patterns:
  - `currentChatPage.set(1)`
  - refresh `chats`
  - refresh `pinnedChats`
  - `goto('/c/<new_chat_id>')`

Design note:

- I did **not** merge Hermes sessions into sidebar list yet.
- I did **not** rewrite sidebar contracts.
- I did **not** create a fake parallel session shell.
- I kept the new behavior inside existing Open WebUI `Session` panel chrome.

### 5. Localization

Updated:

- `/Users/martin/open-webui/src/lib/i18n/locales/en-US/translation.json`
- `/Users/martin/open-webui/src/lib/i18n/locales/ru-RU/translation.json`

Added keys for:

- Hermes runtime
- Hermes sessions
- import/open flow
- refresh/runtime labels
- error/empty states

### 6. Tests

Added utility-level tests here:

- `/Users/martin/open-webui/backend/open_webui/test/hermes/test_utils.py`

These tests cover:

- base Hermes home resolution
- active profile resolution
- active home resolution
- agent dir discovery precedence
- Python discovery precedence
- system Python fallback warning behavior
- merged state.db + JSON session list behavior
- JSON-first session load behavior
- import payload generation including tool messages

Important testing decision:

- I did **not** try to force this into the old router integration harness.
- Existing old router tests depend on missing imports like `test.util.abstract_integration_test`.
- Utility-level tests are the correct reliable path right now.

## Live Machine Assumptions Confirmed

These are real values observed on this machine during this session:

### App

- App URL: `http://127.0.0.1:8080`
- QA chat URL: `http://127.0.0.1:8080/c/b62bb0d2-70e9-44ee-aee9-d3537c5d9713`

### QA credentials

- Email: `qa@example.com`
- Password: `Passw0rd!123`

### Hermes runtime on this machine

Observed:

- `HERMES_WEBUI_AGENT_DIR` is **unset**
- `HERMES_PYTHON` is **unset**
- `HERMES_HOME` is **unset**
- `HERMES_BASE_HOME` is **unset**

Effective discovered runtime:

- Hermes base/active home:
  - `/Users/martin/.hermes`
- No `active_profile` file exists right now
- No `profiles/` directory exists right now
- Therefore effective active profile is:
  - `default`

Real Hermes stores confirmed:

- State DB:
  - `/Users/martin/.hermes/state.db`
- Session transcripts:
  - `/Users/martin/.hermes/sessions/session_*.json`

Real Hermes agent confirmed:

- `/Users/martin/.hermes/hermes-agent`
- agent venv Python:
  - `/Users/martin/.hermes/hermes-agent/.venv/bin/python`

Important nuance:

- That venv Python is a symlink to a uv-managed interpreter.
- The runtime UI now correctly displays the **venv-local path**, not the resolved target path.

## Build / Serve Workflow You Must Respect

This is still the most important practical note.

The backend-served app does **not** reliably reflect local source changes unless you do all of this:

1. Build frontend assets
2. Reinstall editable package
3. Restart backend on `:8080`

Commands that worked in this session:

```bash
./node_modules/.bin/vite build
uv pip install --python "/Users/martin/open-webui/.venv/bin/python" -e "/Users/martin/open-webui"
pkill -f "uvicorn open_webui.main:app"
"/Users/martin/open-webui/.venv/bin/python" -m uvicorn open_webui.main:app --host 127.0.0.1 --port 8080 --forwarded-allow-ips "*"
```

Notes:

- `vite build` is much faster than `npm run build` for repeated loops.
- Frontend changes alone are not enough; `uv pip install -e .` matters.

## Verification Performed In This Session

### Automated / command verification

#### New Hermes utility tests

Command:

```bash
PYTHONPATH=/Users/martin/open-webui/backend /Users/martin/open-webui/.venv/bin/python -m pytest backend/open_webui/test/hermes/test_utils.py -q
```

Result:

- `8 passed`

#### Build

Command:

```bash
./node_modules/.bin/vite build
```

Result:

- build succeeded
- final line included:
  - `✓ built in 1m 21s`
  - `Wrote site to "build"`

#### Editable install

Command:

```bash
uv pip install --python "/Users/martin/open-webui/.venv/bin/python" -e "/Users/martin/open-webui"
```

Result:

- package rebuilt and reinstalled successfully

### Live QA performed

I tested the live app after rebuild/reinstall/restart.

#### Runtime panel validation

In the existing QA chat:

- opened `Session` panel
- confirmed it shows:
  - `default` profile
  - `Home: /Users/martin/.hermes`
  - `Agent: /Users/martin/.hermes/hermes-agent`
  - `Python: /Users/martin/.hermes/hermes-agent/.venv/bin/python`
- confirmed real Hermes sessions are listed in the panel

#### Live import validation

I clicked `Импортировать и открыть` on a real Hermes session.

Result:

- UI navigated to a newly imported Open WebUI chat:
  - `/Users/martin/open-webui` live route observed:
    - `http://127.0.0.1:8080/c/8c22b467-8204-4b16-9331-37de8b3cac64`
- imported transcript content was visible in the chat view
- route changed from the seeded QA chat to the new imported chat as expected

This is the key proof that the bridge is actually working end-to-end.

## Important Architectural Conclusions Already Established

These were confirmed during this session and should guide the next agent.

### 1. The current shell is stable enough

Do **not** redesign shell/sidebar/topbar.

The correct place for the next Hermes continuity work is existing data/behavior layers and bounded panel/row surfaces.

### 2. Session panel was the right first insertion point

The safe path was:

- backend bridge first
- existing `Session` panel second
- sidebar merge later

This avoided breaking:

- chat list contracts
- route assumptions
- existing Open WebUI sidebar pagination

### 3. Do not fake Hermes via `Files` or `terminals`

That was explicitly avoided.

The right backend architecture is:

- dedicated Hermes router
- dedicated Hermes utility bridge

Not:

- Files subsystem abuse
- auth session hacks
- terminal proxy abuse

### 4. Do not rely on old router test harness right now

The existing router integration tests reference helpers that are not present in the worktree.

The right current test strategy is:

- utility-level tests for Hermes discovery/session logic
- add thin API tests only later if needed

## Current Known Limitations / Open Issues

These are the next agent’s real follow-up items.

### 1. No dedupe against previously imported Hermes sessions yet

Current import flow always creates a new Open WebUI chat.

What is missing:

- imported-session lookup by `hermes.session_id`
- existing imported mapping
- “Open existing” behavior if a given Hermes session was already imported

Current state:

- frontend prevents double-click races in-panel during a single import
- backend does **not** yet prevent duplicate imports across separate attempts

### 2. Sidebar is not Hermes-backed yet

Hermes sessions are currently surfaced in the `Session` panel only.

What is still missing:

- sidebar row integration
- optional unified session list strategy
- policy for how imported Hermes sessions should appear/behave in sidebar

This was intentional.

### 3. No profile switching UI/backend loop yet

The bridge reads active home/profile dynamically, which is correct.

But there is no profile switch surface in this adaptation yet.

That means:

- current machine effectively uses `default`
- dynamic resolution is ready for future profile work
- no profile-switch UX path exists yet

### 4. No collapse/dedupe/hygiene logic for Hermes sessions yet

Right now the list is close to raw merged data.

That is safer than hiding legitimate sessions, but it means:

- the list can be noisy
- auxiliary/system-generated sessions are still visible
- no “canonical family session” logic has been ported yet

The spec explicitly says not to hide real sessions silently.

If you add hygiene rules later:

- make them explainable
- make them testable
- prefer explicit toggles over silent disappearance

### 5. Tool message import is acceptable but not polished yet

Current import payload keeps tool messages as:

- `role: "tool"`
- formatted content like:
  - `[Tool: <tool_name>]`
  - followed by content

This works and was visible in the imported chat.

But it is not yet a Hermes-native polished operational transcript replay.

It is functional, not final.

### 6. Repo-wide warning debt still exists

The repo still emits many unrelated Svelte/a11y/self-closing-tag warnings on build.

This is still baseline project debt, not the target of this Hermes slice.

Do not convert the task into a repo-wide cleanup unless explicitly asked.

## What The Next Agent Should Probably Do

Recommended next slice, in order:

### Next best slice

Implement **Hermes import dedupe + reopen behavior**.

Concretely:

1. Store and query imported Hermes session mapping by `hermes.session_id`
2. Prevent duplicate imports of the same Hermes session
3. If already imported, show `Open` instead of always importing again
4. Keep the implementation inside current Open WebUI shell

This is the most logical next bounded behavioral slice.

### After that

Only after dedupe/open policy is stable:

1. surface Hermes-backed continuity more strongly in sidebar rows
2. optionally unify imported/session metadata with sidebar summary logic
3. consider explainable dedupe/collapse for noisy CLI auxiliary sessions

### What not to do next

Do **not**:

- redesign sidebar shell
- replace app layout
- import 21st.dev page-level structures
- build a fake Hermes chat stack
- bypass the backend bridge by browser-direct logic

## Important Files To Read Before Continuing

### Core project guidance

- `/Users/martin/open-webui/AGENTS.md`
- `/Users/martin/Downloads/open-webui-hermes-ux-spec (1).md`
- `/Users/martin/open-webui/docs/hermes-integration-spec.md`

### Current Hermes bridge slice

- `/Users/martin/open-webui/backend/open_webui/utils/hermes.py`
- `/Users/martin/open-webui/backend/open_webui/routers/hermes.py`
- `/Users/martin/open-webui/backend/open_webui/test/hermes/test_utils.py`
- `/Users/martin/open-webui/backend/open_webui/main.py`
- `/Users/martin/open-webui/src/lib/apis/hermes/index.ts`
- `/Users/martin/open-webui/src/lib/components/chat/ChatControls.svelte`
- `/Users/martin/open-webui/src/lib/components/hermes/panels/HermesSessionPanel.svelte`

### Previously implemented Hermes-first UI surfaces

- `/Users/martin/open-webui/src/lib/components/hermes/transcript/*`
- `/Users/martin/open-webui/src/lib/components/hermes/workspace/*`
- `/Users/martin/open-webui/src/lib/components/hermes/panels/*`
- `/Users/martin/open-webui/src/lib/components/layout/Sidebar/ChatItem.svelte`
- `/Users/martin/open-webui/src/lib/components/layout/Sidebar/RecursiveFolder.svelte`
- `/Users/martin/open-webui/src/lib/components/layout/Sidebar.svelte`

### Reference repos / behavior sources

- `/Users/martin/hermes-webui`
- `/Users/martin/.hermes/hermes-agent`

Particularly useful references:

- `/Users/martin/hermes-webui/api/models.py`
- `/Users/martin/hermes-webui/api/profiles.py`
- `/Users/martin/hermes-webui/api/routes.py`
- `/Users/martin/.hermes/hermes-agent/hermes_state.py`

## Dirty Worktree Warning

The worktree is dirty and has **pre-existing unrelated modifications**.

Current `git status --short` includes many modified files outside this slice, including:

- transcript files
- sidebar files
- workspace files
- `uv.lock`
- various Hermes component files and docs as untracked paths

Do **not** reset or clean the tree casually.

Important:

- `/Users/martin/open-webui/src/lib/components/hermes/` is currently untracked as a directory in git status, but it contains important current Hermes work.
- `/Users/martin/open-webui/docs/hermes-integration-spec.md` is also untracked in git status and should be treated as active source material.
- `/Users/martin/open-webui/HANDOFF_HERMES_UI_2026-04-09.md` is still present and untracked.

The correct approach is:

- work carefully around the dirty tree
- do not revert unrelated edits
- only touch files needed for the next bounded Hermes slice

## Current Live Runtime At End Of Session

At the end of this session:

- backend was rebuilt and restarted successfully
- `/api/version` returned `200`
- current server process started normally
- live app was accessible at `http://127.0.0.1:8080`

If the next agent is in a new dialog and wants certainty, simply rerun:

```bash
curl -sf http://127.0.0.1:8080/api/version
```

and if needed, rebuild/reinstall/restart using the commands listed above.

## Short Summary For The Next Agent

Do not redesign the shell.

You now have:

- real Hermes runtime discovery
- real Hermes session discovery from `state.db` + JSON transcripts
- real import/open from the existing `Session` panel
- tests for discovery/session bridge
- live QA proof that import works

The best next move is:

- dedupe imported Hermes sessions
- map `hermes.session_id` to existing imported chats
- support `Open` for already imported sessions
- then only after that consider sidebar surfacing

