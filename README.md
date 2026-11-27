# GabFin

GabFin is an AI-assisted stock analysis and paper-trading desk. This repository
holds the current architecture: a versioned domain layer, isolated market and
analysis services, and a React desk front end.

The previous implementation (Streamlit lab plus a FastAPI static desk) has been
retired. Its history is preserved in the `legacy-full` branch of
[cgabrielck/BomFin](https://github.com/cgabrielck/BomFin); its design notes and
audit reports are kept under `docs/audit/` as evidence of what was verified and
when.

## Layout

| Path | Contents |
|---|---|
| `services/gabfin/` | The domain layer: contracts, market engine, analysis planes, providers, storage, HTTP/WebSocket API |
| `apps/desk-web/` | The React + Vite desk front end |
| `schemas/gabfin-1.0.json` | The canonical JSON Schema every contract is generated from |
| `tests/gabfin/` | Python unit and integration tests for the domain layer |
| `tests/providers/` | Provider adapter tests |
| `tests/e2e/` | Playwright browser tests against a real TLS fixture server |
| `docs/memory/` | Agent checkpoint: architecture, decisions, issues, execution state |
| `docs/superpowers/` | Confirmed design and implementation plans |
| `docs/audit/` | Verification reports and captured evidence |
| `docs/handover/` | Front-end/back-end handover contract for multi-model work |

## Getting started

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[web,tape]"
npm.cmd install
```

Optional extras: `calendar` for exchange trading calendars, `tape` for the
Parquet market-data tape, `web` for the HTTP and WebSocket server.

### Run the domain tests

```powershell
.venv\Scripts\python.exe -m pytest tests/gabfin tests/providers
```

### Run the browser tests

```powershell
npm.cmd run build
npx.cmd playwright test
```

Playwright uses the already-installed Microsoft Edge (`channel: 'msedge'`), so
no separate browser download is needed.

### Run the front end

```powershell
npm.cmd run dev
```

The desk expects a market API at the same origin. `tests/e2e/fixtures/market-server.py`
starts a complete local fixture for browser testing.

## Configuration

Copy `.env.example` to `.env` and fill in only the keys you actually use.
Never commit real credentials. Provider keys are read by the backend only; they
never reach the browser bundle.

## Authority

Requirements and architecture live in
[`docs/superpowers/specs/2026-11-25-gabfin-system-design.md`](docs/superpowers/specs/2026-11-25-gabfin-system-design.md).
Implementation tasks and acceptance gates live in
[`docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md`](docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md).

Documents under `docs/audit/` record what was actually executed and verified.
They are evidence, not requirements.
