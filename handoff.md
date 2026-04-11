# Hermes-First Open WebUI Handoff

## Date

- `2026-04-11`

## Read First

Use sources of truth in this order:

1. `/Users/martin/open-webui/AGENTS.md`
2. `/Users/martin/Downloads/open-webui-hermes-ux-spec (1).md`
3. `/Users/martin/open-webui/docs/hermes-integration-spec.md`
4. `/Users/martin/open-webui/HANDOFF_HERMES_UI_2026-04-10.md`
5. This file

Core rule remains unchanged:

- This is **not** a redesign of Open WebUI.
- This **is** a Hermes-first adaptation on top of Open WebUI’s shell and visual identity.
- Preserve the recognizable Open WebUI shell, spacing rhythm, calm sidebar/topbar feel, and restrained styling.
- Strengthen Hermes UX logic, not Hermes styling.

## Current Status

Project status is late-mid implementation, not polish-only and not finished.

What is already working in the current worktree:

- Hermes-first sidebar/session/workspace surfaces are integrated into the existing Open WebUI shell.
- Transcript has Hermes approval cards and operational activity blocks.
- Right panel has first-class Hermes `Workspace`, `Session`, `Tasks`, `Profile`, `Skills`, `Memory` surfaces.
- Real Hermes runtime/session backend bridge exists.
- Hermes sessions on disk are treated as the continuity source for import/open flows.
- Composer Hermes attach path no longer falsely blocks uploads because of browser model gating.
- Main chat shell no longer lies about Hermes chats as primary `gpt-5.4`.
- Sidebar/session/header surfaces are now much closer to a single Hermes truth.

## What Was Completed In The Latest Slice

### 1. Composer-level Hermes attach hardening

Files:

- `/Users/martin/open-webui/src/lib/components/chat/MessageInput.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/MessageInput/InputMenu.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/MessageInput/IntegrationsMenu.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/Chat.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/Placeholder.svelte`

What changed:

- Replaced implicit Hermes-only attachment behavior with explicit `hermesMode` plumbing.
- Hermes composer now bypasses false browser-model capability gating for file/image attachments.
- False “selected models do not support image inputs/file upload” seams were removed for Hermes mode.
- Non-Hermes behavior stays opt-in safe because the new prop defaults to `false`.

### 2. Workspace continuity cleanup

File:

- `/Users/martin/open-webui/src/lib/components/hermes/workspace/HermesWorkspaceStub.svelte`

What changed:

- Kept the main active workspace browser/preview surface.
- Removed the lower duplicate full lists for `Generated files` and `Current chat files`.
- Replaced them with a calmer summary/launcher row:
  - `Open latest output`
  - `Open latest attachment`

Why:

- The old lower lists duplicated browser-like behavior and made the right panel feel heavier than Open WebUI.
- This keeps the panel aligned with AGENTS.md: preserve shell, reduce duplication, no dashboard drift.

### 3. Unified Hermes session context normalization

Files:

- `/Users/martin/open-webui/src/lib/utils/hermesSessions.ts`
- `/Users/martin/open-webui/src/lib/utils/hermesSessions.test.ts`
- `/Users/martin/open-webui/src/lib/components/chat/Chat.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/Navbar.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/ChatControls.svelte`
- `/Users/martin/open-webui/src/lib/components/hermes/panels/HermesSessionPanel.svelte`
- `/Users/martin/open-webui/src/lib/components/layout/Sidebar/ChatItem.svelte`

What changed:

- Added a canonical normalized resolver:
  - `getResolvedHermesSessionContext(...)`
- This merges `session`, `meta`, `chatPayload`, and `runtime` instead of the old “whole object wins” behavior.
- `Chat.svelte` now computes one normalized current Hermes context and passes it into the main surfaces.
- Navbar, right session panel, and sidebar row now resolve Hermes context from the same precedence model.
- Right session panel now enriches itself from the matched disk session item so source labels line up with the sidebar row.

Why this mattered:

- Before this fix, different surfaces could show different Hermes truths depending on whether they read raw `chat.hermesSession`, `meta.hermes`, runtime fallback, or imported-session map.
- That created visible trust seams.

### 4. Follow-through on helper lists and modal surfaces

Files:

- `/Users/martin/open-webui/src/lib/components/layout/SearchModal.svelte`
- `/Users/martin/open-webui/src/lib/components/layout/ChatsModal.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/Placeholder/ChatList.svelte`

What changed:

- These surfaces now use the same normalized Hermes resolver for meta lines instead of older `resolveHermesChatMeta(...)`-only paths.

Why:

- The continuity fix should not stop at the main chat page.
- Search/chat list/helper surfaces are also part of what the user perceives as “Hermes session truth”.

## What Was Verified

Utility/test/build verification:

- `./node_modules/.bin/vitest run src/lib/utils/hermesSessions.test.ts`
  - `40/40` passing
- `./node_modules/.bin/vite build`
  - passes
- `git diff --check`
  - clean
- `curl -fsS http://127.0.0.1:8080/health`
  - returns `{"status":true}`

Live verification done on the running UI:

- Existing Hermes chat opens successfully.
- Composer can attach files/images in Hermes mode without false model-gating toasts.
- Top strip shows consistent Hermes context, e.g.:
  - `Рабочее пространство: sessions`
  - `Профиль Hermes: default`
  - `Сессия: Активен`
- Sidebar row for the active chat shows Hermes badges/meta without reverting to primary `gpt-5.4`.
- Right session panel now shows source lines aligned with the sidebar row, e.g.:
  - `State DB · JSON · open_webui`

## Important Files In Current Continuity Slice

Primary logic files:

- `/Users/martin/open-webui/src/lib/utils/hermesSessions.ts`
- `/Users/martin/open-webui/src/lib/utils/hermesSessions.test.ts`
- `/Users/martin/open-webui/src/lib/components/chat/Chat.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/MessageInput.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/MessageInput/InputMenu.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/MessageInput/IntegrationsMenu.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/Navbar.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/ChatControls.svelte`
- `/Users/martin/open-webui/src/lib/components/hermes/panels/HermesSessionPanel.svelte`
- `/Users/martin/open-webui/src/lib/components/hermes/workspace/HermesWorkspaceStub.svelte`
- `/Users/martin/open-webui/src/lib/components/layout/Sidebar/ChatItem.svelte`
- `/Users/martin/open-webui/src/lib/components/layout/SearchModal.svelte`
- `/Users/martin/open-webui/src/lib/components/layout/ChatsModal.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/Placeholder/ChatList.svelte`
- `/Users/martin/open-webui/src/lib/components/chat/Placeholder.svelte`
- `/Users/martin/open-webui/src/lib/i18n/locales/en-US/translation.json`
- `/Users/martin/open-webui/src/lib/i18n/locales/ru-RU/translation.json`

## Worktree Reality

Do **not** assume a clean repo.

The repo has broader in-progress Hermes changes outside this slice. Do not revert unrelated files.

Current touched continuity files in this latest slice are mostly:

- modified:
  - `src/lib/components/chat/Chat.svelte`
  - `src/lib/components/chat/ChatControls.svelte`
  - `src/lib/components/chat/MessageInput.svelte`
  - `src/lib/components/chat/MessageInput/InputMenu.svelte`
  - `src/lib/components/chat/MessageInput/IntegrationsMenu.svelte`
  - `src/lib/components/chat/Navbar.svelte`
  - `src/lib/components/chat/Placeholder.svelte`
  - `src/lib/components/chat/Placeholder/ChatList.svelte`
  - `src/lib/components/layout/ChatsModal.svelte`
  - `src/lib/components/layout/SearchModal.svelte`
  - `src/lib/components/layout/Sidebar/ChatItem.svelte`
  - `src/lib/i18n/locales/en-US/translation.json`
  - `src/lib/i18n/locales/ru-RU/translation.json`
- untracked but intentional feature files:
  - `src/lib/components/hermes/panels/HermesSessionPanel.svelte`
  - `src/lib/components/hermes/workspace/HermesWorkspaceStub.svelte`
  - `src/lib/utils/hermesSessions.ts`
  - `src/lib/utils/hermesSessions.test.ts`

Do not misinterpret those untracked files as disposable junk. They are part of the Hermes feature layer already being built.

## Where The Project Stopped

The last bounded step completed was:

- normalize Hermes session context across chat shell + helper list surfaces

This means:

- main chat shell is materially more consistent now
- sidebar row and right session panel agree much better
- helper/modals are no longer on the old resolver path

## Next Correct Step

Do **not** restart the architecture.

The next correct bounded step is:

### End-to-end UX pass on open/import/search/composer continuity

Specifically:

1. Verify that `SearchModal`, `ChatsModal`, sidebar open state, and session import/open all surface the same Hermes identity/meta after navigation.
2. Check for remaining places where browser fallback model text appears too prominently relative to Hermes identity.
3. Tighten any remaining seams around:
   - open/imported Hermes session rows
   - current/open state badges
   - helper list meta lines
   - profile/workspace/session surfacing after reload or navigation
4. Only after that, move to the next functional block.

## What Should Not Be Done Next

- Do not redesign the shell.
- Do not replace panels with a new dashboard-like layout.
- Do not introduce a new visual system.
- Do not duplicate session browsers in multiple places.
- Do not rip out Open WebUI list/table/modal patterns unless there is a real Hermes continuity bug.

## Short Summary For The Next Agent

You are continuing from a real Hermes continuity slice, not from scratch.

Most recent progress:

- composer attach path hardened for Hermes
- workspace right-panel duplication reduced
- Hermes session truth normalized across shell + list surfaces

Immediate mission:

- finish the remaining user-facing continuity seams around open/import/search/navigation behavior
- keep Open WebUI visually recognizable
- do not drift into redesign
