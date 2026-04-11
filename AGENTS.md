# AGENTS.md

Project agent instructions for `/Users/martin/open-webui`.

## Core mission

This project is NOT a redesign of Open WebUI.
This project IS an adaptation of Open WebUI into a Hermes-first interface.

Source of truth:
- Open WebUI = visual base / shell / styling language
- Hermes WebUI = UX logic and interaction model
- 21st.dev Magic MCP = source of point solutions, component patterns, and UI building blocks for NEW or ADAPTED surfaces

## Absolute rules

- Preserve the recognizable visual identity of Open WebUI.
- Preserve the polished, elegant, light Open WebUI feel.
- Do NOT invent a new visual system for the product.
- Do NOT redesign the app shell from scratch.
- Do NOT drift into a dashboard-like, over-carded, over-decorated UI direction.
- Do NOT copy Hermes WebUI styling.
- Do NOT use 21st.dev to generate the whole app or full-page replacements.
- Do NOT use 21st.dev as product architecture; use it only as a component/pattern source.

## What must stay close to Open WebUI

Unless explicitly approved otherwise, preserve:
- overall shell perception
- light visual feel
- typography hierarchy
- spacing rhythm
- topbar/sidebar calmness
- existing Open WebUI layout DNA
- polished but restrained styling
- existing app information architecture where possible

## What may be adapted

Bring in Hermes-first UX primitives WITHOUT replacing Open WebUI's visual identity:
- left agent rail
- stronger session model
- richer transcript behavior
- tool activity surfaces
- approval cards
- right workspace surface
- first-class panels for skills, memory, todos, workspaces, profiles, jobs/tasks

## Correct role of 21st.dev

21st.dev is a Lego box of components/patterns for specific new UI pieces.
It is NOT permission to redesign the whole app.

Use 21st.dev for:
- rail items
- compact metadata chips
- section headers
- workspace file rows
- empty states
- approval cards
- action strips
- side panel headers
- operational cards
- session rows
- small drawers
- toolbar clusters

Do NOT use 21st.dev to:
- generate the entire shell
- replace Open WebUI page structure wholesale
- define routing / IA / product semantics
- justify a new visual language

## Implementation rule: preserve first, replace second

For every UI task:
1. Start from the existing Open WebUI surface.
2. Keep as much of the native shell/layout as possible.
3. Only add or adapt the minimum necessary Hermes-first pieces.
4. For each NEW UI element, prefer borrowing a pattern/component idea from 21st.dev instead of inventing from scratch.
5. Port/adapt the result to local project conventions instead of pasting foreign generated code blindly.

## Required planning format before coding

Before making meaningful UI changes, explicitly state:
- what existing Open WebUI surfaces will remain unchanged
- what Hermes UX primitive is being added or adapted
- which exact new UI pieces will borrow from 21st.dev
- why the result will still look and feel like Open WebUI
- what visual directions are being intentionally avoided

If the plan sounds like a redesign, stop and narrow the scope.

## Safe execution style

Work in bounded slices, not wholesale rewrites.
Preferred slices:
- one transcript improvement
- one rail improvement
- one approval surface
- one workspace panel improvement
- one session row/list improvement

## Local machine constraints

This repo is actively developed on a Mac with **16 GB RAM** and limited headroom.

Required operating mode for agents:
- Treat memory pressure as a hard constraint, not a nice-to-have.
- Prefer lightweight reads, targeted compiles, and narrow tests.
- Do NOT run multiple heavy build/test/dev tasks in parallel.
- Do NOT run broad project-wide checks unless the user explicitly approves the memory cost.
- Close background processes, subagents, and temporary tooling as soon as they are no longer needed.

Testing policy:
- Browser/visual/manual testing through Chrome DevTools, emulation, or live UI inspection must be performed **only by the primary agent**.
- Subagents may inspect code and write patches, but they must **not** be used for ChromeDev, browser automation, or other live UI/runtime testing.
- Prefer single-file or helper-level verification over full app rebuilds.
- If a verification step risks high RAM usage, skip it and choose the cheapest reliable alternative.

## Anti-drift checklist

If a change introduces any of the following, reconsider it:
- too many cards
- too many decorative surfaces
- too much padding
- too many badges/chips/pills
- too much contrast or accent color
- a UI that no longer feels like Open WebUI
- a custom component that could have been borrowed from 21st.dev
- a generated section that changes the app's overall identity

## Summary rule

The correct outcome is:
Open WebUI remains visually recognizable.
Hermes UX becomes much stronger.
21st.dev supplies point components/patterns for new pieces.
The agent assembles and adapts, not reinvents.
