# Development tooling

- User skills are installed in `C:/Users/001/.agents/skills` using
  the bundled skill-installer; application source was not modified.
- Sources: `vercel-labs/agent-skills` (React best practices, composition patterns),
  `openai/skills` (Playwright), `blader/humanizer`, and `obra/superpowers/skills`
  (planning, brainstorming, execution and supporting workflows).
- Matt Pocock workflow installation, pinned revision, renamed skill and hash
  verification: [installation report](../audit/skills-workflow-2026-11-25.md).
- Before planning, implementing or reviewing, follow [workflow](../agents/workflow.md);
  tracker/domain routing is configured there. Keep existing supporting skills.
- Skills are selected when relevant, not all loaded into each task. `grill-me`
  explicitly disables implicit invocation. Use `$grill-me` when wanted.
- CLI and VS Code must run as the same local user and discover this skill path.
  Remote, WSL, container, or other-machine sessions require separate setup.
- Agent-Reach 1.6.1 installed through uv from the author's GitHub release.
  Executable: `C:/Users/001/.local/bin/agent-reach.exe`; user PATH updated.
  Setup completed: 5/5 default-channel preparations succeeded; network actions
  remain unverified. Its setup also copied the skill to Claude/Cursor/Copilot.
- Claude-Mem: user explicitly canceled adoption. Do not use or finish setup.
  A v16.1.3 runtime/worker was previously installed; cleanup has not been
  verified and Codex hooks were not confirmed active. Do not claim uninstalled.
- REA `morluto/rea`, ECC `affaan-m/ECC`, ORCA `stablyai/orca` are confirmed
  evaluation sources, not installed/adopted product runtime dependencies.
- Codex-local pointer: `C:/Users/001/.codex/project-memory/GabFin-ai-trade.md`.
  Root project AGENTS remains the automatic project entry point; the pointer
  does not automatically inject project context into unrelated chats.
- Installing the Playwright skill does not verify browser dependencies or an
  application's browser tests. Superpowers scripts may have platform needs.
- S01/01b added project-local `.tools/uv-bootstrap`, `.tools/python` and a
  checkout-specific `.venv`; no global PATH or Python registry change.
  Exact versions, replay script, dependency snapshots and frontend lockfile
  state are owned by [baseline](../audit/baseline-2026-11-25.md).
- 2026-11-27: worktree moved to `Downloads/GabFin-ai-trade/.worktrees/gabfin-s01`
  and its `.venv` rebuilt locally. The previous venv pointed at the Desktop
  checkout (`pyvenv.cfg` home + editable `.pth`), so it was deleted and recreated
  from `.tools/python/cpython-3.12.16-windows-x86_64-none`.
  Steps, versions and verification: [env setup record](../audit/local-env-setup-2026-11-27.md).
  `pip install -r requirements.txt` takes ~3.7 min; `httpx2` is required by
  starlette's TestClient. Playwright uses the already-installed Microsoft Edge
  (`channel: 'msedge'`), so no separate browser download is needed.

- Optional SDK environment: workspace `.tools/futu-sdk` (Python 3.12), isolated
  from app venv. Exact pinned dependencies/import evidence and recreation steps:
  [03b report](../audit/s03-03b-runner-2026-11-25.md), [runbook](../runbooks/opend-quote-smoke.md).
- Windows app timezone dependency and clean wheel environment
  `.tools/s03-03d-wheel-check` verified without SDK/pandas; versions, build
  failure/recovery and evidence: [03d report](../audit/s03-03d-options-2026-11-25.md).
- `.tools/s03-03e-wheel-check` verifies the history wheel without SDK/pandas;
  pinned private SDK transport hooks require protocol tests/smoke before upgrades:
  [03e report](../audit/s03-03e-history-2026-11-25.md).
- `.tools/s03-03f-wheel-check` runs the synthetic planner demonstration without
  futu/pandas or provider I/O; [03f report](../audit/s03-03f-planner-2026-11-25.md).
- `.tools/s03-rest-wheel-check` verifies the final market wheel without SDK/pandas;
  `.tools/s03-calendar` adds pinned optional calendar export separately.
  Evidence and scripts: [S03 report](../audit/s03-completion-2026-11-26.md).
