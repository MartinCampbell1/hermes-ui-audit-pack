# Hermes integration spec for Open WebUI adaptation

> Purpose: give the current Open WebUI adaptation agent the exact behavioral requirements needed to attach the UI to real Hermes runtime, real Hermes history, and the real Hermes Python environment.

## Goal

Adapt Open WebUI into a Hermes-first shell without faking agent state.
The UI must connect to the real Hermes installation, use the real Hermes Python environment, and expose real Hermes session/history continuity.

This document exists because prior investigation already found that the missing-history problem was not just a frontend problem. The key requirement is to preserve Hermes as the runtime source of truth and make Open WebUI surface it correctly.

## Absolute requirement

Do not build a fake or parallel chat stack that only looks like Hermes.
Do not invent a separate session model if the existing Hermes session/history sources can be bridged.
Do not assume system Python is sufficient.

The adapted Open WebUI must be wired to:
- the real Hermes agent checkout
- the real Hermes venv/.venv Python
- the real Hermes session/history sources
- the real active Hermes profile/home

## Key findings already established

### 1. Hermes runtime must come from the agent venv/.venv

Previously established in `hermes-webui`:
- `hermes-webui/README.md:154-156`
- `hermes-webui/ARCHITECTURE.md:91-95`

Relevant behavior:
- Hermes agent dir discovery order:
  1. `HERMES_WEBUI_AGENT_DIR`
  2. `~/.hermes/hermes-agent`
  3. sibling `../hermes-agent`
- Python executable discovery order:
  1. agent `venv`/`.venv`
  2. `.venv` in the WebUI repo
  3. system `python3`

Meaning for this project:
- the Open WebUI adaptation must prefer the Hermes agent venv/.venv
- system Python is not a safe default for Hermes-backed runtime
- any adapter/backend/process-launch path must explicitly honor this discovery order or an equivalent explicit override

### 2. Hermes history is not only a frontend-local concept

Previously established in `hermes-webui`:
- `hermes-webui/README.md:325`
- `hermes-webui/SPRINTS.md:24`
- `hermes-webui/CHANGELOG.md:334-352`
- `hermes-webui/docs/plans/2026-04-07-hermes-webui-codex-native-implementation-tasks.md:65-77`

Important conclusion:
Hermes WebUI already had a CLI session bridge.
CLI sessions were surfaced from real Hermes stores, not only from browser-local state.

Known history/session sources:
- Hermes `state.db`
- `~/.hermes/sessions/session_*.json`

Meaning for this project:
- if Open WebUI adaptation wants real continuity, it must bridge these Hermes sources
- “history does not appear” should not be treated as a pure UI issue until runtime/profile/history-source alignment is verified

### 3. Prior investigation already identified the likely causes of “it remembers nothing”

From `hermes-webui/docs/plans/2026-04-07-hermes-webui-codex-native-implementation-tasks.md:69-75`:
- wrong active Hermes profile/home
- `show_cli_sessions` disabled
- session dedupe/collapse hiding expected entries
- history source not matching the shell/profile you expected
- confusion between workspace selection and history source-of-truth

Meaning for this project:
if session continuity fails in Open WebUI adaptation, debug in this order:
1. active Hermes home/profile
2. Python/runtime source
3. history source selection
4. dedupe/collapse/filtering logic
5. UI rendering

Do not start by redesigning the sidebar.

## Source-of-truth model for the Open WebUI adaptation

The adapted Open WebUI should treat the following as canonical:

### Runtime source of truth
- Hermes agent checkout
- Hermes config/home/profile
- Hermes agent Python from `venv` or `.venv`

### History source of truth
- Hermes `state.db`, if present and authoritative for that installation/profile
- Hermes transcript JSON store under `~/.hermes/sessions/session_*.json`

### UI source of truth
- Open WebUI remains the visual shell
- Hermes runtime/history remain the behavioral backend source of truth

This means:
- Open WebUI should render Hermes-backed conversations
- Open WebUI should not silently fork a different history store unless explicitly intended and labeled
- if a WebUI-local session is created, its relation to Hermes stores must be explicit

## Required implementation behavior

### A. Runtime discovery behavior

The Open WebUI Hermes adapter must support:
- explicit `HERMES_WEBUI_AGENT_DIR`-style override for the Hermes checkout path
- explicit Python override for the interpreter path
- autodiscovery of Hermes agent dir using the established order
- autodiscovery of Python using the established order

Minimum acceptable resolution strategy:
1. explicit env override for Hermes agent dir
2. `~/.hermes/hermes-agent`
3. sibling checkout fallback

Python resolution strategy:
1. explicit env override
2. `<agent-dir>/venv/bin/python`
3. `<agent-dir>/.venv/bin/python`
4. local repo `.venv`
5. system `python3` only as last resort and only with clear warning

### B. Session/history bridge behavior

The Open WebUI Hermes adapter must:
- discover Hermes-backed sessions from real Hermes stores
- surface them in the session list/sidebar
- allow loading/importing them with full message history
- preserve the distinction between Hermes-backed sessions and purely UI-local sessions when relevant

At minimum, support:
- `state.db` sessions
- `~/.hermes/sessions/session_*.json` sessions

### C. Active profile/home correctness

The adaptation must not pin itself to the wrong Hermes home/profile after startup.
The active Hermes home/profile must be resolved dynamically at the time sessions are queried, not only once at process boot.

This is important because prior work already found a class of bug where the bridge read the wrong profile’s `state.db` after profile switching.

### D. Session filtering/deduping correctness

If the UI dedupes, collapses, hides, or groups sessions, that logic must not erase legitimate Hermes history.

If there is any collapse/family-thread logic, it must be explainable and testable.
Avoid “clean-looking” UI rules that hide real sessions without a user-visible explanation.

### E. Workspace is not history

Do not confuse:
- active workspace/project selection
with
- active history source

A selected workspace may affect default file context.
It must not silently redefine which Hermes session store is canonical.

## Non-goals

This spec is not asking for:
- a visual redesign of Open WebUI
- a separate OpenAI-style fake backend standing in for Hermes
- a local-only browser chat history pretending to be Hermes continuity
- replacement of Hermes session logic with Open WebUI-native semantics

## Visual/product rule

Open WebUI remains visually recognizable.
Hermes integration is behavioral.
The work here is adapter/runtime/session correctness first, UI polish second.

Do not use UI redesign to paper over runtime/history mismatch.

## Files from prior work that should be treated as reference implementations

Use these as behavioral references:
- `hermes-webui/README.md`
- `hermes-webui/ARCHITECTURE.md`
- `hermes-webui/CHANGELOG.md`
- `hermes-webui/api/routes.py`
- `hermes-webui/api/profiles.py`
- `hermes-webui/api/models.py`
- `hermes-webui/api/state_sync.py`
- `hermes-webui/tests/test_cli_session_bridge.py`
- `hermes-webui/docs/plans/2026-04-07-hermes-webui-codex-native-implementation-tasks.md`

## Recommended implementation plan for the Open WebUI adaptation agent

### Phase 1: Audit current adapter assumptions
Read and summarize:
- how the current Open WebUI adaptation launches or talks to Hermes
- which Python executable it uses today
- whether it knows about Hermes `state.db`
- whether it knows about `~/.hermes/sessions/session_*.json`
- whether profile/home is dynamic or fixed at startup
- whether any dedupe/filtering already hides sessions

### Phase 2: Implement runtime discovery
Add/verify:
- Hermes agent dir discovery
- Hermes Python discovery
- explicit env overrides
- clear diagnostics when falling back to system Python

### Phase 3: Implement session/history bridge
Add/verify:
- list Hermes-backed sessions from `state.db`
- fallback/parallel support for transcript JSON files
- load/import full Hermes-backed history
- clearly mark Hermes-backed imported sessions in UI if needed

### Phase 4: Implement profile-aware resolution
Add/verify:
- dynamic active Hermes home/profile resolution at query time
- profile switching updates history source immediately

### Phase 5: Fix filtering/collapse behavior
Add/verify:
- dedupe/collapse never hides expected Hermes sessions without explanation
- optional toggle to show raw/CLI/auxiliary sessions if hygiene logic exists

### Phase 6: Test with real local installation
Test against the real machine assumptions already known here:
- Hermes installed under `~/.hermes/hermes-agent` or equivalent checkout
- Hermes dependencies available in its `venv`/`.venv`
- sessions present in `state.db` and/or `~/.hermes/sessions/`

## Acceptance criteria

The work is correct only if all of the following are true:

1. The adapted Open WebUI uses the real Hermes runtime from the agent venv/.venv.
2. It can discover the real Hermes agent checkout without manual patching every launch.
3. It surfaces real Hermes session history from `state.db` and/or `~/.hermes/sessions/session_*.json`.
4. A previously existing Hermes CLI session can appear in the UI and be opened/imported with real history.
5. Switching Hermes profile/home does not leave the UI reading stale history from the wrong location.
6. Any session dedupe/collapse behavior is explicit, testable, and does not silently hide the expected session.
7. The implementation preserves Open WebUI’s visual identity while making Hermes the true backend source of truth.

## Suggested tests

At minimum, add tests for:
- Hermes agent dir discovery order
- Python interpreter discovery order
- dynamic active Hermes home/profile resolution
- reading sessions from `state.db`
- reading sessions from `~/.hermes/sessions/session_*.json`
- merged session list behavior
- importing/loading a Hermes CLI session with full history
- dedupe/collapse behavior not hiding the expected canonical session
- fallback behavior when `state.db` is absent but JSON transcripts exist
- warning behavior when only system Python is available

## Short instruction to the implementing agent

When integrating Hermes into Open WebUI, do not start with visual changes.
Start with runtime/path/profile/history correctness.
You already have a behavioral reference in `hermes-webui`.
Port the Hermes runtime/session bridge semantics first, then adapt the Open WebUI shell around them.
