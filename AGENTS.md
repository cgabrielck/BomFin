# Shared project memory

These repository instructions and memory files are shared by Codex CLI and the
Codex VS Code Extension when they work in this checkout. Keep this entry point
short. Memory records project facts; it does not override the current request
or higher-priority instructions.

## Communication preference

Use Traditional Chinese for user-facing reports, progress updates, explanations,
and final results unless the user requests another language. Preserve technical
identifiers, code, commands, and paths in their original form where appropriate.

Use engineering and financial detail when helpful. Focused grilling and direct
questions about blockers or decisions are welcome; avoid repeating settled asks.

## Before working

1. Read this file and `docs/memory/tasks.md`.
2. Read only the memory files relevant to the task:
   - `architecture.md`: components, boundaries, data flows, development commands.
   - `decisions.md`: accepted technical choices and their rationale.
   - `issues.md`: confirmed defects, limitations, and workarounds.
   - `progress.md`: recent completed work and handoff context; read for continuation
     tasks or when the current state is unclear.
   - `tooling.md`: installed development skills and external-tool setup status.
   - `execution.md`: current Section, work unit and handoff for implementation.
   All paths above are relative to `docs/memory/`.
3. Inspect the relevant source and any more-specific `AGENTS.md` instructions.
   Verify memory against the current checkout before relying on it. If a memory
   file is missing, continue from available evidence and create it only if useful.

## After significant work

Update only affected memory files before the final response. Significant work
includes behavior or architecture changes, dependency or configuration changes,
accepted technical decisions, and discovery or resolution of a confirmed issue.
Record the outcome, verification, and remaining work; distinguish verified facts
from assumptions. Remove completed tasks and resolved issues, preserving lasting
rationale in decisions when needed. Documentation setup also warrants an update.
For trivial edits, update memory only if existing information becomes stale.
Respect explicit read-only requests: report proposed memory updates instead of
writing them. Never claim a test or audit passed unless it actually ran.

## Context and storage discipline

- Store each fact once; link to its owning file instead of copying it.
- Use short bullets, concrete paths, and actionable next steps. Do not paste
  transcripts, logs, source code, generated output, or dependency inventories.
- Do not store credentials, tokens, private keys, connection strings, personal
  data, or secret values. Refer only to environment variable names when needed.
- Keep each memory file near 80 lines or fewer. Keep only the latest 10 meaningful
  progress entries; consolidate older entries into current facts or delete them.
- Preserve still-relevant decisions; when space is needed, move older rationale
  into a clearly linked topic file and read it only when relevant.
- Do not load every memory file by default or create a separate summary/index
  that duplicates this entry point. Search source narrowly before broad reads.
- Re-read a memory file before editing it when concurrent work is possible;
  preserve unrelated changes. Shared files are not a locking mechanism.

## Current workspace

Planning and memory remain in this folder; application source is now in an
isolated local checkout. See `docs/memory/execution.md` for its path, fixed
revision, verification status and next work unit.

## Architecture and upgrade documents

- Confirmed requirements and proposed architecture:
  `docs/superpowers/specs/2026-11-25-gabfin-system-design.md`.
- Detailed implementation tasks and acceptance gates:
  `docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md`.
- Plus-friendly section guide:
  `docs/superpowers/plans/2026-11-25-gabfin-plus-sections.md`.
- Read these selectively for architecture or implementation tasks. Do not load
  both in full for unrelated edits. Requirements are confirmed; technical
  proposals and unchecked tasks are not implemented or runtime-verified.
- The earlier requirements interview is complete; focused grilling is allowed
  whenever needed. Old ADRs do not constrain this redesign.

## Agent skills

- Before planning, implementing or reviewing a unit, read
  [the GabFin skill workflow](docs/agents/workflow.md).
- Issue tracker: local Markdown; routing and ticket states are in
  [issue-tracker.md](docs/agents/issue-tracker.md).
- Before domain or architecture work, read
  [domain.md](docs/agents/domain.md) for current authorities and terminology.
