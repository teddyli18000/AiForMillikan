# AGENTS.md

## Repository Context

This repository contains two standalone desktop applications for the Millikan
oil-drop experiment. They are separate products that happen to share one Git
repository, one media folder, and one CI configuration directory.

- `normal/` — the mainline human-in-the-loop measurement app. See
  `normal/AGENTS.md` before changing anything there.
- `experimental/` — the research app for automatic multi-drop / multi-platform
  analysis. See `experimental/AGENTS.md` before changing anything there.
- `media/` — shared raw videos, screenshots, and diagrams. It is data, not code.
- `.github/workflows/` — two independent CI pipelines and two independent
  release pipelines.

## Hard Separation Rules

- The apps must not import each other, share a business Python package, share
  worker operations, or share mutable runtime state.
- Each app owns its own `pyproject.toml`, `apps/desktop/package.json`, tests,
  configs, and documentation.
- Identical low-level code is duplicated on purpose. Do not create a shared
  business package to remove the duplication.
- There is no runtime mode switch. The Normal app opens the Normal workspace and
  the Experimental app opens the Experimental workspace.
- A Normal worker exposes only `normal.*` operations. An Experimental worker
  exposes only `video.*`, `platform.*`, `analysis.*`, `downstream.*`, and
  `report.*` operations.
- Packaging inputs must stay inside the app directory. The only shared input is
  the read-only `media/` folder used by tests and documentation.

## Shared Engineering Rules

- Desktop worker IPC is newline-delimited JSON encoded as UTF-8 without BOM.
  Python workers configure UTF-8 standard streams; Electron launches them with
  `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`; Node decodes stdout/stderr with a
  streaming UTF-8 decoder.
- User-visible text, exported Markdown, JSON, CSV, source files, and
  documentation must not contain Unicode replacement characters or known
  UTF-8/legacy-codepage mojibake. Each app keeps an encoding regression test.
- Machine JSON/CSV values stay numeric SI values. User-visible scientific
  notation uses readable typography such as `1.602 × 10⁻¹⁹ C`.
- Every app must pass its Python suite, frontend suite, TypeScript build, worker
  build, and Electron packaging before a release tag is created.

## Commands

Commands are per app. There is no repository-root Python or npm environment.

```powershell
cd normal
.venv\Scripts\python -m pytest tests -q
cd apps\desktop
npm test
npm run build
```

```powershell
cd experimental
.venv\Scripts\python -m pytest tests -q
cd apps\desktop
npm test
npm run build
```

## Release Naming

- Normal tags: `normal-vX.Y.Z`
- Experimental tags: `experimental-vX.Y.Z`
- The historical `v1.0.0` tag and Release belong to the pre-split combined app
  and must not be rewritten.
